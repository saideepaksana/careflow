import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  confirmChange,
  createConversation,
  endConversation,
  hasDetail,
  hasStatus,
  listMessages,
  listPatients,
  listTasks,
  login,
  Patient,
  Reply,
  sendMessage,
} from "./api";
import Coordinator from "./Coordinator";
import { formatTime } from "./format";
import { CoordinatorSession, loadSession, PatientSession, saveSession, Session } from "./session";
import { Row, Section, Shell } from "./Shell";

const CHAT_POLL_MS = 10000;
const PENDING_CONFIRMATION = "please answer the pending confirmation";
const CONVERSATION_ENDED = "conversation has ended";
const NOTHING_TO_CONFIRM = "nothing to confirm";
const CONVERSATION_GONE = "That conversation is no longer available. Your next message starts a new one.";
const CONVERSATION_CLOSED = "That conversation has ended. Your next message starts a new one.";

type ChatLine = { role: "patient" | "assistant" | "coordinator"; text: string; at?: string };

function EmergencyNote() {
  return (
    <p className="emergency">
      In an emergency, call <strong>112</strong>.
    </p>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (session: PatientSession) => void }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [signingIn, setSigningIn] = useState(false);
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
    if (signingIn) return;
    setSigningIn(true);
    setError("");
    try {
      const result = await login(patientId);
      onSignedIn({
        role: "patient",
        token: result.token,
        patientId,
        patientName: result.patient_name,
        conversationId: "",
        pending: false,
      });
    } catch (err) {
      setError((err as Error).message);
      setSigningIn(false);
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
      <button type="submit" className="primary" disabled={!patientId || signingIn}>
        Sign in
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function CoordinatorSignIn({ onSignedIn }: { onSignedIn: (session: CoordinatorSession) => void }) {
  const [token, setToken] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = token.trim();
    if (!value) return;
    setChecking(true);
    setError("");
    try {
      await listTasks(value);
      onSignedIn({ role: "coordinator", token: value });
    } catch (err) {
      setError((err as Error).message);
      setChecking(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Coordinator sign-in</h2>
      <label>
        Coordinator token
        <input
          type="password"
          autoComplete="current-password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
        />
      </label>
      <button type="submit" className="primary" disabled={!token.trim() || checking}>
        Open console
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function Welcome({ notice, onSignedIn }: { notice: string; onSignedIn: (session: Session) => void }) {
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
        {notice && (
          <p className="error notice" role="alert">
            {notice}
          </p>
        )}
        <SignIn onSignedIn={onSignedIn} />
        <CoordinatorSignIn onSignedIn={onSignedIn} />
      </div>
    </Shell>
  );
}

function Chat({
  session,
  onUpdate,
  onSignOut,
}: {
  session: PatientSession;
  onUpdate: (patch: Partial<PatientSession>) => void;
  onSignOut: (notice: string) => void;
}) {
  const { conversationId, pending } = session;
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [endFailed, setEndFailed] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const list = useRef<HTMLUListElement>(null);
  const restoredId = useRef(conversationId);
  const loadTicket = useRef(0);

  const reload = useCallback(
    async (id: string) => {
      const ticket = ++loadTicket.current;
      const messages = await listMessages(session.token, id);
      if (ticket !== loadTicket.current) return;
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

  const clearMessages = useCallback(() => {
    setError("");
    setNotice("");
    setEndFailed(false);
  }, []);

  const resetConversation = useCallback(
    (message: string) => {
      loadTicket.current += 1;
      onUpdate({ conversationId: "", pending: false });
      setLines([]);
      clearMessages();
      setNotice(message);
    },
    [onUpdate, clearMessages],
  );

  const handleGone = useCallback(
    (err: unknown): boolean => {
      if (hasStatus(err, 401)) onSignOut((err as Error).message);
      else if (hasStatus(err, 404)) resetConversation(CONVERSATION_GONE);
      else if (hasDetail(err, CONVERSATION_ENDED)) resetConversation(CONVERSATION_CLOSED);
      else return false;
      return true;
    },
    [onSignOut, resetConversation],
  );

  const fail = useCallback(
    (err: unknown) => {
      if (handleGone(err)) return;
      if (hasDetail(err, PENDING_CONFIRMATION)) {
        onUpdate({ pending: true });
        setError("Please tap Yes or No above first. If this is an emergency, call 112.");
        return;
      }
      if (hasDetail(err, NOTHING_TO_CONFIRM)) onUpdate({ pending: false });
      setError((err as Error).message);
    },
    [handleGone, onUpdate],
  );

  useEffect(() => {
    if (restoredId.current) reload(restoredId.current).catch(fail);
  }, [reload, fail]);

  useEffect(() => {
    if (!conversationId || waiting || ending) return;
    const timer = window.setInterval(() => reload(conversationId).catch(handleGone), CHAT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [conversationId, waiting, ending, reload, handleGone]);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [lines, waiting, pending]);

  function beginRequest(line: string) {
    loadTicket.current += 1;
    setWaiting(true);
    clearMessages();
    setLines((current) => [...current, { role: "patient", text: line }]);
  }

  async function showReply(id: string, result: Reply) {
    onUpdate({ pending: result.confirmation !== null });
    await reload(id);
  }

  async function endCurrent(): Promise<boolean> {
    setEnding(true);
    try {
      await endConversation(session.token, conversationId);
      return true;
    } catch (err) {
      if (hasStatus(err, 404) || hasStatus(err, 409)) return true;
      fail(err);
      setEndFailed(hasStatus(err, 503));
      return false;
    } finally {
      setEnding(false);
    }
  }

  async function startNew() {
    clearMessages();
    if (conversationId && !(await endCurrent())) return;
    resetConversation("");
  }

  async function answer(approved: boolean) {
    beginRequest(approved ? "Yes" : "No");
    try {
      await showReply(conversationId, await confirmChange(session.token, conversationId, approved));
    } catch (err) {
      setLines((current) => current.slice(0, -1));
      fail(err);
    } finally {
      setWaiting(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message) return;
    beginRequest(message);
    setText("");
    try {
      const id = conversationId || (await createConversation(session.token)).conversation_id;
      onUpdate({ conversationId: id });
      await showReply(id, await sendMessage(session.token, id, message));
    } catch (err) {
      setLines((current) => current.slice(0, -1));
      setText(message);
      fail(err);
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
          <button type="button" onClick={startNew} disabled={waiting || ending}>
            {ending ? "Saving..." : "New conversation"}
          </button>
          <button type="button" onClick={() => onSignOut("")}>
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
        <ul className="messages" ref={list} aria-live="polite">
          {lines.length === 0 && !waiting && <li className="empty">No messages yet.</li>}
          {lines.map((line, index) => (
            <li key={index} className={line.role}>
              {line.role === "coordinator" && <span className="speaker">Care team</span>}
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
              <button type="button" onClick={() => answer(false)} disabled={waiting || ending}>
                No
              </button>
              <button type="button" className="primary" onClick={() => answer(true)} disabled={waiting || ending}>
                Yes
              </button>
            </div>
          </div>
        )}
        <form className="composer" onSubmit={send}>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={pending ? "Tap Yes or No above, or tell us about an urgent problem" : "Type a message"}
            maxLength={2000}
          />
          <button type="submit" className="primary" disabled={waiting || ending}>
            Send
          </button>
        </form>
        {notice && (
          <p className="muted" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
            {endFailed && (
              <button type="button" onClick={() => resetConversation("")}>
                Start anyway
              </button>
            )}
          </p>
        )}
      </div>
    </Shell>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const [notice, setNotice] = useState("");

  useEffect(() => saveSession(session), [session]);

  const signIn = useCallback((next: Session) => {
    setNotice("");
    setSession(next);
  }, []);

  const signOut = useCallback((message: string) => {
    setNotice(message);
    setSession(null);
  }, []);

  const updatePatient = useCallback((patch: Partial<PatientSession>) => {
    setSession((current) => (current?.role === "patient" ? { ...current, ...patch } : current));
  }, []);

  if (session?.role === "patient") return <Chat session={session} onUpdate={updatePatient} onSignOut={signOut} />;
  if (session?.role === "coordinator") return <Coordinator token={session.token} onSignOut={signOut} />;
  return <Welcome notice={notice} onSignedIn={signIn} />;
}
