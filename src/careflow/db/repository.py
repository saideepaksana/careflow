import psycopg


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
