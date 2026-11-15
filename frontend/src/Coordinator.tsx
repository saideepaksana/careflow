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

const QUEUE_REFRESH_MS = 15000;

function age(createdAt: string): string {
  const minutes = Math.round((Date.now() - new Date(createdAt).getTime()) / 60000);
  return minutes < 60 ? `${minutes} min ago` : `${Math.round(minutes / 60)} h ago`;
}

function TaskCard({ task, token, onDone }: { task: Task; token: string; onDone: (text: string) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      const result = await decideTask(token, task.id, approved, note);
      onDone(`Task ${task.id}: ${approved ? "approved" : "done"} (run ${result.run_status ?? "none"})`);
    } catch (err) {
      onDone((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`task ${task.priority}`}>
      <div className="task-head">
        <strong>{task.priority.toUpperCase()}</strong> {task.kind} · {task.patient_name} · {age(task.created_at)}
      </div>
      <div>{task.title}</div>
      <div className="task-detail">{task.detail.text}</div>
      {task.trace_id && <div className="task-detail">Trace {task.trace_id}</div>}
      <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note to patient" />
      <div className="confirm">
        {task.kind === "approval" ? (
          <>
            <button type="button" disabled={busy} onClick={() => decide(true)}>
              Approve
            </button>
            <button type="button" disabled={busy} onClick={() => decide(false)}>
              Deny
            </button>
          </>
        ) : (
          <button type="button" disabled={busy} onClick={() => decide(true)}>
            Resolve
          </button>
        )}
      </div>
    </li>
  );
}

function PatientPanel({ token, patientId, stamp }: { token: string; patientId: string; stamp: number }) {
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    patientProgress(token, patientId).then(setProgress).catch(() => setProgress([]));
    patientTimeline(token, patientId).then(setTimeline).catch(() => setTimeline([]));
  }, [token, patientId, stamp]);

  return (
    <div className="panel">
      <h3>Care-plan progress</h3>
      <ul className="progress">
        {progress.map((item) => (
          <li key={item.id} className={item.status}>
            {item.description} · due {item.due_date ?? "-"} · {item.status}
            {item.starts_at && ` · ${new Date(item.starts_at).toLocaleString()}`}
          </li>
        ))}
      </ul>
      <h3>Timeline</h3>
      <ul className="timeline">
        {timeline.map((event, index) => (
          <li key={index}>
            <span className="when">{new Date(event.at).toLocaleString()}</span> <em>{event.kind}</em>{" "}
            {String(event.detail.role ?? "")} {event.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Coordinator({ token }: { token: string }) {
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

  return (
    <div className="card console">
      <header>
        <strong>Coordinator console</strong>
        <button type="button" onClick={refresh}>
          Refresh
        </button>
      </header>
      {status && <p className="status">{status}</p>}
      <h3>Queue ({tasks.length})</h3>
      <ul className="queue">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} token={token} onDone={done} />
        ))}
      </ul>
      <label>
        Patient
        <select value={patientId} onChange={(event) => setPatientId(event.target.value)}>
          <option value="">Choose a patient</option>
          {patients.map((patient) => (
            <option key={patient.id} value={patient.id}>
              {patient.name} ({patient.diagnosis}) · {patient.open_tasks} open
            </option>
          ))}
        </select>
      </label>
      {patientId && <PatientPanel token={token} patientId={patientId} stamp={stamp} />}
    </div>
  );
}
