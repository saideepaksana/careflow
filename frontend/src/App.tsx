import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  confirmChange,
  createConversation,
  endConversation,
  listMessages,
  listPatients,
  login,
  Patient,
  Reply,
  sendMessage,
} from "./api";
import Coordinator from "./Coordinator";
import { formatTime } from "./format";
import { Row, Section, Shell } from "./Shell";

const CHAT_POLL_MS = 10000;

type ChatLine = { role: "patient" | "assistant" | "coordinator"; text: string; at?: string };
type Session = { token: string; patientId: string; patientName: string };

function EmergencyNote() {
  return (
    <p className="emergency">
      In an emergency, call <strong>112</strong>.
    </p>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (session: Session) => void }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listPatients()
      .then((rows) => {
        setPatients(rows);
        setPatientId(rows[0]?.id ?? "");
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await login(patientId);
      onSignedIn({ token: result.token, patientId, patientName: result.patient_name });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Patient sign-in</h2>
      <label>
        Patient
        <select value={patientId} onChange={(event) => setPatientId(event.target.value)}>
          {patients.map((patient) => (
            <option key={patient.id} value={patient.id}>
              {patient.name} ({patient.id})
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="primary" disabled={!patientId}>
        Sign in
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function CoordinatorSignIn({ onSignedIn }: { onSignedIn: (token: string) => void }) {
  const [token, setToken] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (token.trim()) onSignedIn(token.trim());
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Coordinator sign-in</h2>
      <label>
        Coordinator token
        <input type="password" value={token} onChange={(event) => setToken(event.target.value)} />
      </label>
      <button type="submit" className="primary" disabled={!token.trim()}>
        Open console
      </button>
    </form>
  );
}

function Welcome({
  onPatient,
  onCoordinator,
}: {
  onPatient: (session: Session) => void;
  onCoordinator: (token: string) => void;
}) {
  const sidebar = (
    <Section title="About">
      <p className="text">
        Patients book and move follow-up visits and ask about their discharge plan. Anything clinical goes to a nurse
        coordinator.
      </p>
      <EmergencyNote />
    </Section>
  );
  return (
    <Shell sidebar={sidebar}>
      <div className="sign-in">
        <SignIn onSignedIn={onPatient} />
        <CoordinatorSignIn onSignedIn={onCoordinator} />
      </div>
    </Shell>
  );
}

function Chat({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [conversationId, setConversationId] = useState("");
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const list = useRef<HTMLUListElement>(null);

  const reload = useCallback(
    async (id: string) => {
      const messages = await listMessages(session.token, id);
      setLines(
        messages.map((message) => ({
          role: message.role as ChatLine["role"],
          text: message.content,
          at: message.created_at,
        })),
      );
    },
    [session.token],
  );

  useEffect(() => {
    if (!conversationId || waiting) return;
    const timer = window.setInterval(() => reload(conversationId).catch(() => undefined), CHAT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [conversationId, waiting, reload]);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [lines, waiting, pending]);

  async function showReply(id: string, result: Reply) {
    setPending(result.confirmation !== null);
    await reload(id);
  }

  async function startNew() {
    if (conversationId) {
      setWaiting(true);
      await endConversation(session.token, conversationId).catch(() => undefined);
      setWaiting(false);
    }
    setConversationId("");
    setLines([]);
    setPending(false);
    setError("");
  }

  async function answer(approved: boolean) {
    setWaiting(true);
    setError("");
    setLines((current) => [...current, { role: "patient", text: approved ? "Yes" : "No" }]);
    try {
      await showReply(conversationId, await confirmChange(session.token, conversationId, approved));
    } catch (err) {
      setLines((current) => current.slice(0, -1));
      setError((err as Error).message);
    } finally {
      setWaiting(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message) return;
    setWaiting(true);
    setError("");
    setLines((current) => [...current, { role: "patient", text: message }]);
    setText("");
    try {
      const id = conversationId || (await createConversation(session.token)).conversation_id;
      setConversationId(id);
      await showReply(id, await sendMessage(session.token, id, message));
    } catch (err) {
      setLines((current) => current.slice(0, -1));
      setText(message);
      setError((err as Error).message);
    } finally {
      setWaiting(false);
    }
  }

  const sidebar = (
    <>
      <Section title="Patient">
        <h1>{session.patientName}</h1>
        <div className="rows">
          <Row label="Patient ID" value={session.patientId} />
          <Row label="Conversation" value={conversationId ? "Active" : "Not started"} />
        </div>
        <div className="actions">
          <button type="button" onClick={startNew} disabled={waiting}>
            New conversation
          </button>
          <button type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </Section>
      <Section title="Help">
        <p className="text">Ask to book or move a follow-up visit, or ask about your discharge plan.</p>
        <EmergencyNote />
      </Section>
    </>
  );

  return (
    <Shell sidebar={sidebar}>
      <div className="chat">
        <ul className="messages" ref={list}>
          {lines.length === 0 && !waiting && <li className="empty">No messages yet.</li>}
          {lines.map((line, index) => (
            <li key={index} className={line.role}>
              {line.text}
              {line.at && <span className="time">{formatTime(line.at)}</span>}
            </li>
          ))}
          {waiting && (
            <li className="assistant typing" aria-label="CareFlow is replying">
              <span />
              <span />
              <span />
            </li>
          )}
        </ul>
        {pending && (
          <div className="confirm-bar">
            <span>Confirm this change?</span>
            <div className="actions">
              <button type="button" onClick={() => answer(false)} disabled={waiting}>
                No
              </button>
              <button type="button" className="primary" onClick={() => answer(true)} disabled={waiting}>
                Yes
              </button>
            </div>
          </div>
        )}
        <form className="composer" onSubmit={send}>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={pending ? "Answer the question above first" : "Type a message"}
            maxLength={2000}
            disabled={pending}
          />
          <button type="submit" className="primary" disabled={waiting || pending}>
            Send
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    </Shell>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [coordinatorToken, setCoordinatorToken] = useState("");
  if (session) return <Chat session={session} onSignOut={() => setSession(null)} />;
  if (coordinatorToken) return <Coordinator token={coordinatorToken} onSignOut={() => setCoordinatorToken("")} />;
  return <Welcome onPatient={setSession} onCoordinator={setCoordinatorToken} />;
}
