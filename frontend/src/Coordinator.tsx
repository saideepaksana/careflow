import { useCallback, useEffect, useState } from "react";
import {
  decideTask,
  listPatientOverview,
  listTasks,
  patientProgress,
  patientTimeline,
  PatientOverview,
  ProgressItem,
  Task,
  TimelineEvent,
} from "./api";
import { formatDateTime, formatDay, humanize, timelineLabel } from "./format";
import { Dot, Row, Section, Shell } from "./Shell";

const QUEUE_REFRESH_MS = 15000;

function age(createdAt: string): string {
  const minutes = Math.round((Date.now() - new Date(createdAt).getTime()) / 60000);
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / (60 * 24))} d ago`;
}

function TaskItem({ task, token, onDone }: { task: Task; token: string; onDone: (text: string) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      await decideTask(token, task.id, approved, note);
      const outcome = task.kind === "approval" ? (approved ? "approved" : "denied") : "resolved";
      onDone(`Task for ${task.patient_name} ${outcome}.`);
    } catch (err) {
      onDone((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="task">
      <div className="task-head">
        <Dot tone={task.priority} />
        <span className="task-priority">{task.priority}</span>
        <span className="muted">{humanize(task.kind)}</span>
        <span className="muted">·</span>
        <span>{task.patient_name}</span>
        <span className="muted push">{age(task.created_at)}</span>
      </div>
      <div className="task-title">{task.title}</div>
      {task.detail.text && <div className="muted">{task.detail.text}</div>}
      {task.trace_id && <div className="muted small mono">Trace {task.trace_id}</div>}
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

function PatientDetail({ token, patient, stamp }: { token: string; patient: PatientOverview; stamp: number }) {
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    patientProgress(token, patient.id).then(setProgress).catch(() => setProgress([]));
    patientTimeline(token, patient.id).then(setTimeline).catch(() => setTimeline([]));
  }, [token, patient.id, stamp]);

  return (
    <>
      <div className="panel">
        <div className="panel-head">
          <h2>{patient.name}</h2>
          <span className="muted">{patient.diagnosis}</span>
        </div>
        <div className="label">Care-plan progress</div>
        <table className="table">
          <tbody>
            {progress.map((item) => (
              <tr key={item.id}>
                <td>{item.description}</td>
                <td className="muted">{item.due_date ? `Due ${formatDay(item.due_date)}` : "No due date"}</td>
                <td className="muted">{item.starts_at ? formatDateTime(item.starts_at) : "Not booked"}</td>
                <td className="status-cell">
                  <Dot tone={item.status} />
                  {item.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <div className="label">Timeline</div>
        {timeline.length === 0 && <p className="muted">No activity yet.</p>}
        <table className="table timeline">
          <tbody>
            {timeline.map((event, index) => (
              <tr key={index}>
                <td className="muted nowrap">{formatDateTime(event.at)}</td>
                <td className="nowrap">{timelineLabel(event)}</td>
                <td>{humanize(event.text)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function count(tasks: Task[], test: (task: Task) => boolean): number {
  return tasks.filter(test).length;
}

export default function Coordinator({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [patients, setPatients] = useState<PatientOverview[]>([]);
  const [patientId, setPatientId] = useState("");
  const [status, setStatus] = useState("");
  const [stamp, setStamp] = useState(0);

  const refresh = useCallback(() => {
    setStamp((current) => current + 1);
    listTasks(token).then(setTasks).catch((err: Error) => setStatus(err.message));
    listPatientOverview(token).then(setPatients).catch(() => undefined);
  }, [token]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, QUEUE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  function done(text: string) {
    setStatus(text);
    refresh();
  }

  const selected = patients.find((patient) => patient.id === patientId);
  const sidebar = (
    <>
      <Section title="Open tasks" aside={<span className="muted small">refreshes every 15 s</span>}>
        <div className="rows">
          <Row label={<><Dot tone="emergency" />Emergency</>} value={count(tasks, (t) => t.priority === "emergency")} />
          <Row label={<><Dot tone="urgent" />Urgent</>} value={count(tasks, (t) => t.priority === "urgent")} />
          <Row label={<><Dot tone="routine" />Routine</>} value={count(tasks, (t) => t.priority === "routine")} />
          <Row label="Waiting for approval" value={count(tasks, (t) => t.kind === "approval")} />
        </div>
      </Section>
      <Section title="Patients">
        <ul className="patients">
          {patients.map((patient) => (
            <li key={patient.id}>
              <button
                type="button"
                className={patient.id === patientId ? "selected" : ""}
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
          <button type="button" onClick={onSignOut}>
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
          {status && <p className="muted">{status}</p>}
          {tasks.length === 0 && <p className="muted">No open tasks.</p>}
          <ul className="queue">
            {tasks.map((task) => (
              <TaskItem key={task.id} task={task} token={token} onDone={done} />
            ))}
          </ul>
        </div>
        {selected ? (
          <PatientDetail token={token} patient={selected} stamp={stamp} />
        ) : (
          <p className="muted center">Select a patient to see their care plan and timeline.</p>
        )}
      </div>
    </Shell>
  );
}
