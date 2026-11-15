from collections.abc import Callable
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from careflow.config import CLINIC_TIMEZONE, FREE_SLOTS_LIMIT


class ActionRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def get_current_care_plan(conn: psycopg.Connection, patient_id: str) -> dict | None:
    plan = conn.execute(
        "SELECT * FROM care_plans WHERE patient_id = %s AND status = 'published'",
        (patient_id,),
    ).fetchone()
    if plan is None:
        return None
    items = conn.execute(
        "SELECT * FROM care_plan_items WHERE care_plan_id = %s ORDER BY id",
        (plan["id"],),
    ).fetchall()
    return {**plan, "items": items}


def list_appointments(conn: psycopg.Connection, patient_id: str) -> list[dict]:
    return conn.execute(
        "SELECT a.id, a.slot_id, s.starts_at, c.name AS clinician_name, c.specialty,"
        " a.care_plan_item_id FROM appointments a"
        " JOIN slots s ON s.id = a.slot_id JOIN clinicians c ON c.id = s.clinician_id"
        " WHERE a.patient_id = %s AND a.status = 'booked' ORDER BY s.starts_at",
        (patient_id,),
    ).fetchall()


def find_free_slots(
    conn: psycopg.Connection,
    specialty: str,
    start_date: date,
    end_date: date,
    limit: int = FREE_SLOTS_LIMIT,
) -> list[dict]:
    return conn.execute(
        "SELECT s.id, s.starts_at, c.name AS clinician_name FROM slots s"
        " JOIN clinicians c ON c.id = s.clinician_id"
        " WHERE c.specialty = %s AND (s.starts_at AT TIME ZONE %s)::date BETWEEN %s AND %s"
        " AND NOT EXISTS (SELECT 1 FROM appointments a"
        " WHERE a.slot_id = s.id AND a.status = 'booked')"
        " ORDER BY s.starts_at, s.id LIMIT %s",
        (specialty, CLINIC_TIMEZONE, start_date, end_date, limit),
    ).fetchall()


def run_action(
    conn: psycopg.Connection,
    patient_id: str,
    action: str,
    idempotency_key: str,
    work: Callable[[], dict],
) -> dict:
    stored = conn.execute(
        "SELECT result FROM action_results WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    if stored is not None:
        return {**stored["result"], "replayed": True}
    try:
        with conn.transaction():
            result = {"ok": True, **work(), "replayed": False}
            conn.execute(
                "INSERT INTO action_results (idempotency_key, patient_id, action, result)"
                " VALUES (%s, %s, %s, %s)",
                (idempotency_key, patient_id, action, Jsonb(result)),
            )
    except ActionRejected as rejection:
        return {"ok": False, "error": rejection.code}
    return result


def next_appointment_id(conn: psycopg.Connection) -> str:
    row = conn.execute(
        "SELECT coalesce(max(substring(id FROM 2)::int), 0) + 1 AS n FROM appointments"
    ).fetchone()
    return f"A{row['n']:03d}"


def is_current_plan_item(conn: psycopg.Connection, patient_id: str, item_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM care_plan_items i JOIN care_plans p ON p.id = i.care_plan_id"
        " WHERE i.id = %s AND p.patient_id = %s AND p.status = 'published'",
        (item_id, patient_id),
    ).fetchone()
    return row is not None


def insert_booking(
    conn: psycopg.Connection,
    patient_id: str,
    slot_id: str,
    care_plan_item_id: str | None,
    idempotency_key: str,
) -> dict:
    slot = conn.execute("SELECT starts_at FROM slots WHERE id = %s", (slot_id,)).fetchone()
    if slot is None:
        raise ActionRejected("slot_not_found")
    if care_plan_item_id and not is_current_plan_item(conn, patient_id, care_plan_item_id):
        raise ActionRejected("item_not_found")
    appointment_id = next_appointment_id(conn)
    try:
        with conn.transaction():
            conn.execute(
                "INSERT INTO appointments (id, patient_id, slot_id, care_plan_item_id, status,"
                " idempotency_key) VALUES (%s, %s, %s, %s, 'booked', %s)",
                (appointment_id, patient_id, slot_id, care_plan_item_id, idempotency_key),
            )
    except psycopg.errors.UniqueViolation as violation:
        if violation.diag.constraint_name != "one_booking_per_slot":
            raise
        raise ActionRejected("slot_taken") from violation
    return {"appointment_id": appointment_id, "starts_at": slot["starts_at"].isoformat()}


def cancel_booking(conn: psycopg.Connection, patient_id: str, appointment_id: str) -> dict:
    row = conn.execute(
        "SELECT status, care_plan_item_id FROM appointments WHERE id = %s AND patient_id = %s",
        (appointment_id, patient_id),
    ).fetchone()
    if row is None:
        raise ActionRejected("not_found")
    if row["status"] != "booked":
        raise ActionRejected("invalid_state")
    conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,))
    return row


def book_appointment(
    conn: psycopg.Connection,
    patient_id: str,
    slot_id: str,
    care_plan_item_id: str | None,
    idempotency_key: str,
) -> dict:
    def work() -> dict:
        booking = insert_booking(conn, patient_id, slot_id, care_plan_item_id, idempotency_key)
        return {**booking, "slot_id": slot_id}

    return run_action(conn, patient_id, "book_appointment", idempotency_key, work)


def cancel_appointment(
    conn: psycopg.Connection, patient_id: str, appointment_id: str, idempotency_key: str
) -> dict:
    def work() -> dict:
        cancel_booking(conn, patient_id, appointment_id)
        return {"appointment_id": appointment_id, "status": "cancelled"}

    return run_action(conn, patient_id, "cancel_appointment", idempotency_key, work)


def reschedule_appointment(
    conn: psycopg.Connection,
    patient_id: str,
    appointment_id: str,
    new_slot_id: str,
    idempotency_key: str,
) -> dict:
    def work() -> dict:
        old = cancel_booking(conn, patient_id, appointment_id)
        item_id = old["care_plan_item_id"]
        booking = insert_booking(conn, patient_id, new_slot_id, item_id, idempotency_key)
        return {**booking, "old_appointment_id": appointment_id}

    return run_action(conn, patient_id, "reschedule_appointment", idempotency_key, work)


def create_coordinator_task(
    conn: psycopg.Connection,
    patient_id: str,
    priority: str,
    title: str,
    detail: str,
    idempotency_key: str,
    kind: str = "handoff",
    thread_id: str | None = None,
) -> dict:
    def work() -> dict:
        row = conn.execute(
            "INSERT INTO coordinator_tasks (patient_id, priority, status, title, detail,"
            " idempotency_key, kind, thread_id) VALUES (%s, %s, 'open', %s, %s, %s, %s, %s)"
            " RETURNING id",
            (
                patient_id,
                priority,
                title,
                Jsonb({"text": detail}),
                idempotency_key,
                kind,
                thread_id,
            ),
        ).fetchone()
        return {"task_id": row["id"]}

    return run_action(conn, patient_id, "create_coordinator_task", idempotency_key, work)


def insert_audit_event(
    conn: psycopg.Connection,
    patient_id: str,
    actor: str,
    event: str,
    detail: dict,
    trace_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_events (patient_id, actor, event, detail, trace_id)"
        " VALUES (%s, %s, %s, %s, %s)",
        (patient_id, actor, event, Jsonb(detail), trace_id),
    )


def list_patients(conn: psycopg.Connection) -> list[dict]:
    return conn.execute("SELECT id, name FROM patients ORDER BY id").fetchall()


def get_patient(conn: psycopg.Connection, patient_id: str) -> dict | None:
    return conn.execute("SELECT id, name FROM patients WHERE id = %s", (patient_id,)).fetchone()


def create_conversation(conn: psycopg.Connection, conversation_id: str, patient_id: str) -> None:
    conn.execute(
        "INSERT INTO conversations (id, patient_id) VALUES (%s, %s)",
        (conversation_id, patient_id),
    )


def owns_conversation(conn: psycopg.Connection, conversation_id: str, patient_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id = %s AND patient_id = %s",
        (conversation_id, patient_id),
    ).fetchone()
    return row is not None


def list_messages(conn: psycopg.Connection, conversation_id: str) -> list[dict]:
    return conn.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id = %s ORDER BY id",
        (conversation_id,),
    ).fetchall()


def insert_message(
    conn: psycopg.Connection,
    conversation_id: str,
    role: str,
    content: str,
    idempotency_key: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, idempotency_key)"
        " VALUES (%s, %s, %s, %s) ON CONFLICT (idempotency_key) DO NOTHING",
        (conversation_id, role, content, idempotency_key),
    )


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"


def get_conversation_state(conn: psycopg.Connection, conversation_id: str) -> dict:
    return conn.execute(
        "SELECT summary, summarized_through, ended_at FROM conversations WHERE id = %s",
        (conversation_id,),
    ).fetchone()


def list_messages_after(
    conn: psycopg.Connection, conversation_id: str, message_id: int
) -> list[dict]:
    return conn.execute(
        "SELECT id, role, content FROM messages WHERE conversation_id = %s AND id > %s ORDER BY id",
        (conversation_id, message_id),
    ).fetchall()


def save_summary(
    conn: psycopg.Connection, conversation_id: str, summary: str, summarized_through: int
) -> None:
    conn.execute(
        "UPDATE conversations SET summary = %s, summarized_through = %s WHERE id = %s",
        (summary, summarized_through, conversation_id),
    )


def end_conversation(conn: psycopg.Connection, conversation_id: str) -> bool:
    row = conn.execute(
        "UPDATE conversations SET ended_at = now() WHERE id = %s AND ended_at IS NULL RETURNING id",
        (conversation_id,),
    ).fetchone()
    return row is not None


def insert_memory(
    conn: psycopg.Connection,
    patient_id: str,
    memory_type: str,
    key: str | None,
    content: str,
    conversation_id: str,
    embedding: list[float],
) -> int:
    row = conn.execute(
        "INSERT INTO memories (patient_id, type, key, content, source_conversation_id,"
        " embedding) VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
        (patient_id, memory_type, key, content, conversation_id, to_vector_literal(embedding)),
    ).fetchone()
    return row["id"]


def active_semantic_memories(conn: psycopg.Connection, patient_id: str) -> list[dict]:
    return conn.execute(
        "SELECT id, key, content FROM memories WHERE patient_id = %s AND type = 'semantic'"
        " AND superseded_by IS NULL ORDER BY key",
        (patient_id,),
    ).fetchall()


def supersede_memory(conn: psycopg.Connection, old_id: int, new_id: int) -> None:
    conn.execute("UPDATE memories SET superseded_by = %s WHERE id = %s", (new_id, old_id))


def nearest_episodes(
    conn: psycopg.Connection, patient_id: str, embedding: list[float], limit: int
) -> list[dict]:
    return conn.execute(
        "SELECT content, created_at FROM memories WHERE patient_id = %s AND type = 'episodic'"
        " ORDER BY embedding <=> %s::vector LIMIT %s",
        (patient_id, to_vector_literal(embedding), limit),
    ).fetchall()


def replace_corpus(conn: psycopg.Connection, documents: list[dict], chunks: list[dict]) -> None:
    conn.execute("DELETE FROM documents")
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO documents (id, title, owner_patient_id, condition, version, status,"
            " effective_from) VALUES (%(id)s, %(title)s, %(owner_patient_id)s, %(condition)s,"
            " %(version)s, %(status)s, %(effective_from)s)",
            documents,
        )
        cursor.executemany(
            "INSERT INTO chunks (id, document_id, heading, content, embedding)"
            " VALUES (%(id)s, %(document_id)s, %(heading)s, %(content)s, %(embedding)s::vector)",
            [{**chunk, "embedding": to_vector_literal(chunk["embedding"])} for chunk in chunks],
        )


VISIBLE_CHUNKS = """
    chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'current' AND (
      d.owner_patient_id = %(patient_id)s
      OR (d.owner_patient_id IS NULL AND (d.condition = 'any' OR d.condition IN (
        SELECT condition FROM documents
        WHERE owner_patient_id = %(patient_id)s AND status = 'current'))))
"""


def keyword_search(conn: psycopg.Connection, patient_id: str, query: str, limit: int) -> list[str]:
    rows = conn.execute(
        "WITH q AS (SELECT replace(plainto_tsquery('english', %(query)s)::text, '&', '|')"
        "::tsquery AS terms)"
        f" SELECT c.id FROM q, {VISIBLE_CHUNKS} AND c.search_text @@ q.terms"
        " ORDER BY ts_rank_cd(c.search_text, q.terms) DESC, c.id LIMIT %(limit)s",
        {"patient_id": patient_id, "query": query, "limit": limit},
    ).fetchall()
    return [row["id"] for row in rows]


def dense_search(
    conn: psycopg.Connection, patient_id: str, embedding: list[float], limit: int
) -> list[str]:
    rows = conn.execute(
        f"SELECT c.id FROM {VISIBLE_CHUNKS}"
        " ORDER BY c.embedding <=> %(embedding)s::vector, c.id LIMIT %(limit)s",
        {"patient_id": patient_id, "embedding": to_vector_literal(embedding), "limit": limit},
    ).fetchall()
    return [row["id"] for row in rows]


def get_chunks(conn: psycopg.Connection, chunk_ids: list[str]) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id, c.document_id, d.title, c.heading, c.content"
        " FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(%s)",
        (chunk_ids,),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


def chunk_status(conn: psycopg.Connection, chunk_ids: list[str]) -> dict[str, str]:
    rows = conn.execute(
        "SELECT c.id, d.status FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE c.id = ANY(%s)",
        (chunk_ids,),
    ).fetchall()
    return {row["id"]: row["status"] for row in rows}


def create_workflow_run(conn: psycopg.Connection, thread_id: str, conversation_id: str) -> None:
    conn.execute(
        "INSERT INTO workflow_runs (thread_id, conversation_id, status) VALUES (%s, %s, 'running')",
        (thread_id, conversation_id),
    )


def set_run_status(conn: psycopg.Connection, thread_id: str, status: str) -> None:
    conn.execute(
        "UPDATE workflow_runs SET status = %s, updated_at = now() WHERE thread_id = %s",
        (status, thread_id),
    )


def get_run(conn: psycopg.Connection, thread_id: str) -> dict | None:
    return conn.execute(
        "SELECT thread_id, conversation_id, status FROM workflow_runs WHERE thread_id = %s",
        (thread_id,),
    ).fetchone()


def pending_confirmation(conn: psycopg.Connection, conversation_id: str) -> str | None:
    row = conn.execute(
        "SELECT thread_id FROM workflow_runs"
        " WHERE conversation_id = %s AND status = 'awaiting_confirmation'",
        (conversation_id,),
    ).fetchone()
    return row["thread_id"] if row else None


def runs_with_status(conn: psycopg.Connection, status: str) -> list[str]:
    rows = conn.execute(
        "SELECT thread_id FROM workflow_runs WHERE status = %s ORDER BY created_at", (status,)
    ).fetchall()
    return [row["thread_id"] for row in rows]


def last_message_id(conn: psycopg.Connection, conversation_id: str) -> int:
    row = conn.execute(
        "SELECT coalesce(max(id), 0) AS id FROM messages WHERE conversation_id = %s",
        (conversation_id,),
    ).fetchone()
    return row["id"]


def assistant_messages_after(
    conn: psycopg.Connection, conversation_id: str, message_id: int
) -> list[str]:
    rows = conn.execute(
        "SELECT content FROM messages WHERE conversation_id = %s AND id > %s"
        " AND role = 'assistant' ORDER BY id",
        (conversation_id, message_id),
    ).fetchall()
    return [row["content"] for row in rows]


def get_action_result(conn: psycopg.Connection, idempotency_key: str) -> dict | None:
    row = conn.execute(
        "SELECT result FROM action_results WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    return {**row["result"], "replayed": True} if row else None


def get_appointment(conn: psycopg.Connection, patient_id: str, appointment_id: str) -> dict | None:
    return conn.execute(
        "SELECT a.id, a.status, a.slot_id, a.care_plan_item_id, s.starts_at, c.specialty"
        " FROM appointments a JOIN slots s ON s.id = a.slot_id"
        " JOIN clinicians c ON c.id = s.clinician_id"
        " WHERE a.id = %s AND a.patient_id = %s",
        (appointment_id, patient_id),
    ).fetchone()


def get_slot(conn: psycopg.Connection, slot_id: str) -> dict | None:
    return conn.execute(
        "SELECT s.id, s.starts_at, c.name AS clinician_name, c.specialty,"
        " EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id AND a.status = 'booked')"
        " AS booked FROM slots s JOIN clinicians c ON c.id = s.clinician_id WHERE s.id = %s",
        (slot_id,),
    ).fetchone()


def get_plan_item(conn: psycopg.Connection, patient_id: str, item_id: str) -> dict | None:
    return conn.execute(
        "SELECT i.id, i.kind, i.description, i.specialty,"
        " p.published_on + i.due_within_days AS due_date"
        " FROM care_plan_items i JOIN care_plans p ON p.id = i.care_plan_id"
        " WHERE i.id = %s AND p.patient_id = %s AND p.status = 'published'",
        (item_id, patient_id),
    ).fetchone()


def booked_appointment_for_item(
    conn: psycopg.Connection, patient_id: str, item_id: str
) -> str | None:
    row = conn.execute(
        "SELECT id FROM appointments"
        " WHERE patient_id = %s AND care_plan_item_id = %s AND status = 'booked'",
        (patient_id, item_id),
    ).fetchone()
    return row["id"] if row else None


def list_open_tasks(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT t.id, t.patient_id, p.name AS patient_name, t.kind, t.priority, t.title,"
        " t.detail, t.thread_id, t.created_at,"
        " (SELECT e.trace_id FROM audit_events e WHERE e.event = 'workflow_invocation'"
        "  AND e.detail->>'thread_id' = t.thread_id ORDER BY e.id LIMIT 1) AS trace_id"
        " FROM coordinator_tasks t JOIN patients p ON p.id = t.patient_id WHERE t.status = 'open'"
        " ORDER BY array_position(ARRAY['emergency', 'urgent', 'routine'], t.priority),"
        " t.created_at, t.id"
    ).fetchall()


def get_task(conn: psycopg.Connection, task_id: int) -> dict | None:
    return conn.execute(
        "SELECT t.id, t.patient_id, t.kind, t.status, t.thread_id, r.conversation_id"
        " FROM coordinator_tasks t LEFT JOIN workflow_runs r ON r.thread_id = t.thread_id"
        " WHERE t.id = %s",
        (task_id,),
    ).fetchone()


def resolve_task(conn: psycopg.Connection, task_id: int, note: str) -> None:
    conn.execute(
        "UPDATE coordinator_tasks SET status = 'resolved', resolved_at = now(),"
        " detail = detail || jsonb_build_object('resolution', %s::text)"
        " WHERE id = %s AND status = 'open'",
        (note, task_id),
    )


def get_warning_signs(conn: psycopg.Connection, patient_id: str) -> list[dict]:
    return conn.execute(
        "SELECT i.id, i.description, i.severity, i.rule FROM care_plan_items i"
        " JOIN care_plans p ON p.id = i.care_plan_id"
        " WHERE p.patient_id = %s AND p.status = 'published' AND i.kind = 'warning_sign'"
        " ORDER BY i.id",
        (patient_id,),
    ).fetchall()


def thread_patient(conn: psycopg.Connection, thread_id: str) -> str | None:
    row = conn.execute(
        "SELECT c.patient_id FROM workflow_runs r JOIN conversations c ON c.id = r.conversation_id"
        " WHERE r.thread_id = %s",
        (thread_id,),
    ).fetchone()
    return row["patient_id"] if row else None


def list_patient_overview(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT p.id, p.name, e.primary_diagnosis AS diagnosis,"
        " (SELECT count(*) FROM coordinator_tasks t"
        "  WHERE t.patient_id = p.id AND t.status = 'open') AS open_tasks"
        " FROM patients p LEFT JOIN encounters e ON e.patient_id = p.id ORDER BY p.id"
    ).fetchall()


TIMELINE_QUERY = """
SELECT * FROM (
  SELECT m.created_at AS at, 'message' AS kind, m.content AS text,
         jsonb_build_object('role', m.role) AS detail, m.id AS seq
  FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE c.patient_id = %(p)s
  UNION ALL
  SELECT t.created_at, 'task_created', t.title,
         jsonb_build_object('priority', t.priority, 'task_kind', t.kind, 'task_id', t.id), t.id
  FROM coordinator_tasks t WHERE t.patient_id = %(p)s
  UNION ALL
  SELECT t.resolved_at, 'task_resolved', t.title,
         jsonb_build_object('note', t.detail->>'resolution', 'task_id', t.id), t.id
  FROM coordinator_tasks t WHERE t.patient_id = %(p)s AND t.resolved_at IS NOT NULL
  UNION ALL
  SELECT a.created_at, 'action', a.action, a.result, 0
  FROM action_results a WHERE a.patient_id = %(p)s AND a.action <> 'create_coordinator_task'
  UNION ALL
  SELECT mem.created_at, 'memory', mem.content,
         jsonb_build_object('type', mem.type, 'key', mem.key,
                            'superseded', mem.superseded_by IS NOT NULL), mem.id
  FROM memories mem WHERE mem.patient_id = %(p)s
  UNION ALL
  SELECT e.ts, 'workflow', e.detail->>'status',
         jsonb_build_object('trace_id', e.trace_id, 'usage', e.detail->'usage',
                            'invocation', e.detail->>'invocation'), e.id
  FROM audit_events e WHERE e.patient_id = %(p)s AND e.event = 'workflow_invocation'
) events ORDER BY at DESC, kind, seq DESC LIMIT %(limit)s
"""


def patient_timeline(conn: psycopg.Connection, patient_id: str, limit: int) -> list[dict]:
    rows = conn.execute(TIMELINE_QUERY, {"p": patient_id, "limit": limit}).fetchall()
    return [{key: row[key] for key in ("at", "kind", "text", "detail")} for row in rows]


def plan_progress_rows(conn: psycopg.Connection, patient_id: str) -> list[dict]:
    return conn.execute(
        "SELECT i.id, i.kind, i.description, i.specialty,"
        " p.published_on + i.due_within_days AS due_date,"
        " (SELECT a.id FROM appointments a JOIN slots s ON s.id = a.slot_id"
        "  WHERE a.care_plan_item_id = i.id AND a.status = 'booked'"
        "  ORDER BY s.starts_at LIMIT 1) AS appointment_id,"
        " (SELECT s.starts_at FROM appointments a JOIN slots s ON s.id = a.slot_id"
        "  WHERE a.care_plan_item_id = i.id AND a.status = 'booked'"
        "  ORDER BY s.starts_at LIMIT 1) AS starts_at"
        " FROM care_plan_items i JOIN care_plans p ON p.id = i.care_plan_id"
        " WHERE p.patient_id = %s AND p.status = 'published' AND i.kind IN ('follow_up', 'lab')"
        " ORDER BY i.id",
        (patient_id,),
    ).fetchall()
