import { FormEvent, useCallback, useEffect, useState } from "react";
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

const CHAT_POLL_MS = 10000;

type ChatLine = { role: "patient" | "assistant" | "coordinator"; text: string };
type Session = { token: string; patientName: string };

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
      onSignedIn({ token: result.token, patientName: result.patient_name });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
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
      <button type="submit" disabled={!patientId}>
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
    <form className="card" onSubmit={submit}>
      <h2>Coordinator sign-in</h2>
      <label>
        Coordinator token
        <input type="password" value={token} onChange={(event) => setToken(event.target.value)} />
      </label>
      <button type="submit" disabled={!token.trim()}>
        Open console
      </button>
    </form>
  );
}

function Chat({ session }: { session: Session }) {
  const [conversationId, setConversationId] = useState("");
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [text, setText] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(
    async (id: string) => {
      const messages = await listMessages(session.token, id);
      setLines(messages.map((message) => ({ role: message.role as ChatLine["role"], text: message.content })));
    },
    [session.token],
  );

  useEffect(() => {
    if (!conversationId || waiting) return;
    const timer = window.setInterval(() => reload(conversationId).catch(() => undefined), CHAT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [conversationId, waiting, reload]);

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
      setError((err as Error).message);
    } finally {
      setWaiting(false);
    }
  }

  return (
    <div className="card chat">
      <header>
        <strong>{session.patientName}</strong>
        <button type="button" onClick={startNew} disabled={waiting}>
          New conversation
        </button>
      </header>
      <ul className="messages">
        {lines.map((line, index) => (
          <li key={index} className={line.role}>
            {line.text}
          </li>
        ))}
      </ul>
      {pending && (
        <div className="confirm">
          <button type="button" onClick={() => answer(true)} disabled={waiting}>
            Yes
          </button>
          <button type="button" onClick={() => answer(false)} disabled={waiting}>
            No
          </button>
        </div>
      )}
      <form onSubmit={send}>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type a message"
          maxLength={2000}
          disabled={pending}
        />
        <button type="submit" disabled={waiting || pending}>
          {waiting ? "Thinking..." : "Send"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [coordinatorToken, setCoordinatorToken] = useState("");
  if (session) return <Chat session={session} />;
  if (coordinatorToken) return <Coordinator token={coordinatorToken} />;
  return (
    <div className="stack">
      <h1>CareFlow</h1>
      <SignIn onSignedIn={setSession} />
      <CoordinatorSignIn onSignedIn={setCoordinatorToken} />
    </div>
  );
}
