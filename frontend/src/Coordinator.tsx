import { useCallback, useEffect, useRef, useState } from "react";
import {
  decideTask,
  hasStatus,
  listPatientOverview,
  listTasks,
  patientProgress,
  patientTimeline,
  PatientOverview,
  ProgressItem,
  Task,
  TimelineEvent,
} from "./api";
import { formatDateTime, formatDay, timelineLabel, timelineText } from "./format";
import { Dot, Row, Section, Shell } from "./Shell";

const QUEUE_REFRESH_MS = 15000;
const STATUS_CLEAR_MS = 4000;
const TOKEN_REJECTED = "The coordinator token is no longer accepted. Please sign in again.";

function age(createdAt: string): string {
  const minutes = Math.round((Date.now() - new Date(createdAt).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / (60 * 24))} d ago`;
}

type TaskItemProps = {
  task: Task;
  token: string;
  onDone: (taskId: number, text: string) => void;
  onFail: (err: unknown) => void;
};

function TaskItem({ task, token, onDone, onFail }: TaskItemProps) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      await decideTask(token, task.id, approved, note);
      const outcome = task.kind === "approval" ? (approved ? "approved" : "denied") : "resolved";
      onDone(task.id, `Task for ${task.patient_name} ${outcome}.`);
    } catch (err) {
      onFail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="task">
      <div className="task-head">
        <Dot tone={task.priority} />
        <span className="task-priority">{task.priority}</span>
        <span className="muted">·</span>
        <span>{task.patient_name}</span>
        <span className="muted push">{age(task.created_at)}</span>
      </div>
      <div className="task-title" title={task.trace_id ? `Trace ${task.trace_id}` : undefined}>
        {task.title}
      </div>
      {task.detail.text && <div className="muted">{task.detail.text}</div>}
      <div className="task-actions">
        <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note to the patient (optional)" />
        {task.kind === "approval" ? (
          <>
            <button type="button" disabled={busy} onClick={() => decide(false)}>
              Deny
            </button>
            <button type="button" className="primary" disabled={busy} onClick={() => decide(true)}>
              Approve
            </button>
          </>
        ) : (
          <button type="button" className="primary" disabled={busy} onClick={() => decide(true)}>
            Resolve
          </button>
        )}
      </div>
    </li>
  );
}

type DetailProps = {
  token: string;
  patient: PatientOverview;
  stamp: number;
  onFail: (err: unknown, show: (text: string) => void) => void;
};

type DetailData = { progress: ProgressItem[]; timeline: TimelineEvent[] };

function ProgressTable({ progress }: { progress: ProgressItem[] }) {
  return (
    <table className="table progress">
      <thead>
        <tr>
          <th>Item</th>
          <th>Due</th>
          <th>Appointment</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {progress.length === 0 && (
          <tr>
            <td colSpan={4} className="muted">
              No care-plan items.
            </td>
          </tr>
        )}
        {progress.map((item) => (
          <tr key={item.id}>
            <td>{item.description}</td>
            <td className="muted">{item.due_date ? formatDay(item.due_date) : "No due date"}</td>
            <td className="muted">{item.starts_at ? formatDateTime(item.starts_at) : "Not booked"}</td>
            <td className="status-cell">
              <Dot tone={item.status} />
              {item.status}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TimelineTable({ timeline }: { timeline: TimelineEvent[] }) {
  if (timeline.length === 0) return <p className="muted">No activity yet.</p>;
  return (
    <table className="table timeline">
      <tbody>
        {timeline.map((event, index) => (
          <tr key={index}>
            <td className="muted">{formatDateTime(event.at)}</td>
            <td>{timelineLabel(event)}</td>
            <td>{timelineText(event)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PatientDetail({ token, patient, stamp, onFail }: DetailProps) {
  const [data, setData] = useState<DetailData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stale = false;
    Promise.all([patientProgress(token, patient.id), patientTimeline(token, patient.id)])
      .then(([progress, timeline]) => {
        if (stale) return;
        setData({ progress, timeline });
        setError("");
      })
      .catch((err: unknown) => {
        if (!stale) onFail(err, setError);
      });
    return () => {
      stale = true;
    };
  }, [token, patient.id, stamp, onFail]);

  return (
    <div className="detail">
      <div className="panel">
        <div className="panel-head">
          <h2>{patient.name}</h2>
          <span className="muted">{patient.diagnosis}</span>
        </div>
        {error && <p className="error">{error}</p>}
        {!data && !error && <p className="muted">Loading...</p>}
        {data && (
          <>
            <div className="label">Care-plan progress</div>
            <ProgressTable progress={data.progress} />
          </>
        )}
      </div>
      {data && (
        <div className="panel">
          <div className="label">Timeline</div>
          <TimelineTable timeline={data.timeline} />
        </div>
      )}
    </div>
  );
}

function count(tasks: Task[], test: (task: Task) => boolean): number {
  return tasks.filter(test).length;
}

export default function Coordinator({ token, onSignOut }: { token: string; onSignOut: (notice: string) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [patients, setPatients] = useState<PatientOverview[]>([]);
  const [patientId, setPatientId] = useState("");
  const [status, setStatus] = useState("");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [stamp, setStamp] = useState(0);
  const refreshTicket = useRef(0);

  const fail = useCallback(
    (err: unknown, show: (text: string) => void) => {
      if (hasStatus(err, 403)) onSignOut(TOKEN_REJECTED);
      else show((err as Error).message);
    },
    [onSignOut],
  );

  const refresh = useCallback(() => {
    const ticket = ++refreshTicket.current;
    setStamp((current) => current + 1);
    Promise.all([listTasks(token), listPatientOverview(token)])
      .then(([nextTasks, nextPatients]) => {
        if (ticket !== refreshTicket.current) return;
        setTasks(nextTasks);
        setPatients(nextPatients);
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (ticket === refreshTicket.current) fail(err, setLoadError);
      });
  }, [token, fail]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, QUEUE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!status) return;
    const timer = window.setTimeout(() => setStatus(""), STATUS_CLEAR_MS);
    return () => window.clearTimeout(timer);
  }, [status]);

  function done(taskId: number, text: string) {
    setTasks((current) => current.filter((task) => task.id !== taskId));
    setActionError("");
    setStatus(text);
    refresh();
  }

  function decisionFailed(err: unknown) {
    setStatus("");
    fail(err, setActionError);
    if (!hasStatus(err, 403)) refresh();
  }

  const selected = patients.find((patient) => patient.id === patientId);
  const sidebar = (
    <>
      <Section title="Open tasks" aside={<span className="muted small">refreshes every 15 s</span>}>
        <div className="rows">
          <Row label={<><Dot tone="emergency" />Emergency</>} value={count(tasks, (t) => t.priority === "emergency")} />
          <Row label={<><Dot tone="urgent" />Urgent</>} value={count(tasks, (t) => t.priority === "urgent")} />
          <Row label={<><Dot tone="routine" />Routine</>} value={count(tasks, (t) => t.priority === "routine")} />
          <Row label={<><Dot tone="blank" />Waiting for approval</>} value={count(tasks, (t) => t.kind === "approval")} />
        </div>
      </Section>
      <Section title="Patients">
        <ul className="patients">
          {patients.map((patient) => (
            <li key={patient.id}>
              <button
                type="button"
                className={patient.id === patientId ? "selected" : ""}
                aria-current={patient.id === patientId ? "true" : undefined}
                onClick={() => setPatientId(patient.id)}
              >
                <span>
                  <span className="patient-name">{patient.name}</span>
                  <span className="muted small">{patient.diagnosis}</span>
                </span>
                <span className="muted small">{patient.open_tasks > 0 ? `${patient.open_tasks} open` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Session">
        <div className="actions">
          <button type="button" onClick={refresh}>
            Refresh
          </button>
          <button type="button" onClick={() => onSignOut("")}>
            Sign out
          </button>
        </div>
      </Section>
    </>
  );

  return (
    <Shell sidebar={sidebar}>
      <div className="console">
        <div className="panel">
          <div className="panel-head">
            <h2>Queue</h2>
            <span className="muted">{tasks.length} open</span>
          </div>
          {status && (
            <p className="muted" role="status">
              {status}
            </p>
          )}
          {loadError && <p className="error">{loadError}</p>}
          {actionError && (
            <p className="error" role="alert">
              {actionError}
            </p>
          )}
          {tasks.length === 0 && <p className="muted">No open tasks.</p>}
          <ul className="queue">
            {tasks.map((task) => (
              <TaskItem key={task.id} task={task} token={token} onDone={done} onFail={decisionFailed} />
            ))}
          </ul>
        </div>
        {selected ? (
          <PatientDetail key={selected.id} token={token} patient={selected} stamp={stamp} onFail={fail} />
        ) : (
          <p className="muted center">Select a patient to see their care plan and timeline.</p>
        )}
      </div>
    </Shell>
  );
}
