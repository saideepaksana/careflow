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

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(errorText(status, detail));
    this.status = status;
    this.detail = detail;
  }
}

export const hasStatus = (error: unknown, status: number) => error instanceof ApiError && error.status === status;

export const hasDetail = (error: unknown, detail: string) => error instanceof ApiError && error.detail === detail;

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
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  return response.json() as Promise<T>;
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    return typeof detail === "string" ? detail : "";
  } catch {
    return "";
  }
}

function errorText(status: number, detail: string): string {
  if (status === 401) return "Your session has ended. Please sign in again.";
  if (status === 403) return "That token was not accepted.";
  if (status === 404 && detail === "conversation not found") return "That conversation is no longer available.";
  if (status === 404) return "That item could not be found. Please refresh and try again.";
  if (status === 409 && detail === "the request is still in progress")
    return "This request is still being processed. Please try again in a few minutes.";
  if (status === 409) return "That request is no longer waiting for an answer.";
  if (status === 422) return "That message could not be sent. Please check it and try again.";
  if (status === 423) return "This conversation is busy. Please try again in a moment.";
  if (status === 503 && detail === "memory could not be written") return "This conversation could not be saved.";
  if (status >= 500) return "Something went wrong on our side. Please try again in a moment.";
  return "The request could not be completed. Please try again.";
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
