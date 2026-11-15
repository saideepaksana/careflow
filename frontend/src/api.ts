export type Patient = { id: string; name: string };
export type Message = { role: string; content: string; created_at: string };
export type Reply = { reply: string; status: string; confirmation: string | null };
export type Task = {
  id: number;
  patient_id: string;
  patient_name: string;
  created_at: string;
  kind: string;
  priority: string;
  title: string;
  detail: { text?: string };
  thread_id: string | null;
  trace_id: string | null;
};
export type PatientOverview = { id: string; name: string; diagnosis: string | null; open_tasks: number };
export type TimelineEvent = { at: string; kind: string; text: string; detail: Record<string, unknown> };
export type ProgressItem = {
  id: string;
  kind: string;
  description: string;
  due_date: string | null;
  appointment_id: string | null;
  starts_at: string | null;
  status: "booked" | "late" | "overdue" | "open";
};
export type Decision = { task_id: number; run_status: string | null };

async function request<T>(
  path: string,
  init: RequestInit = {},
  token = "",
  coordinatorToken = "",
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (coordinatorToken) headers["X-Coordinator-Token"] = coordinatorToken;
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const listPatients = () => request<Patient[]>("/patients");

export const login = (patientId: string) =>
  request<{ token: string; patient_name: string }>("/login", {
    method: "POST",
    body: JSON.stringify({ patient_id: patientId }),
  });

export const createConversation = (token: string) =>
  request<{ conversation_id: string }>("/conversations", { method: "POST" }, token);

export const listMessages = (token: string, conversationId: string) =>
  request<Message[]>(`/conversations/${conversationId}/messages`, {}, token);

export const sendMessage = (token: string, conversationId: string, text: string) =>
  request<Reply>(
    `/conversations/${conversationId}/messages`,
    { method: "POST", body: JSON.stringify({ text }) },
    token,
  );

export const endConversation = (token: string, conversationId: string) =>
  request<unknown>(`/conversations/${conversationId}/end`, { method: "POST" }, token);

export const confirmChange = (token: string, conversationId: string, approved: boolean) =>
  request<Reply>(
    `/conversations/${conversationId}/confirm`,
    { method: "POST", body: JSON.stringify({ approved }) },
    token,
  );

export const listTasks = (coordinatorToken: string) =>
  request<Task[]>("/coordinator/tasks", {}, "", coordinatorToken);

export const decideTask = (coordinatorToken: string, taskId: number, approved: boolean, note: string) =>
  request<Decision>(
    `/coordinator/tasks/${taskId}/decision`,
    { method: "POST", body: JSON.stringify({ approved, note }) },
    "",
    coordinatorToken,
  );

export const listPatientOverview = (coordinatorToken: string) =>
  request<PatientOverview[]>("/coordinator/patients", {}, "", coordinatorToken);

export const patientTimeline = (coordinatorToken: string, patientId: string) =>
  request<TimelineEvent[]>(`/coordinator/patients/${patientId}/timeline`, {}, "", coordinatorToken);

export const patientProgress = (coordinatorToken: string, patientId: string) =>
  request<ProgressItem[]>(`/coordinator/patients/${patientId}/progress`, {}, "", coordinatorToken);
