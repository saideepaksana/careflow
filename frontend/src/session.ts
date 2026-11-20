export type PatientSession = {
  role: "patient";
  token: string;
  patientId: string;
  patientName: string;
  conversationId: string;
  pending: boolean;
};
export type CoordinatorSession = { role: "coordinator"; token: string };
export type Session = PatientSession | CoordinatorSession;

const STORAGE_KEY = "careflow.session";

export function loadSession(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session | null): void {
  try {
    if (session) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    return;
  }
}
