export type Patient = { id: string; name: string };
export type Message = { role: string; content: string; created_at: string };
export type Reply = { reply: string; stop_reason: string };

async function request<T>(path: string, init: RequestInit = {}, token = ""): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
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

export const sendMessage = (token: string, conversationId: string, text: string) =>
  request<Reply>(
    `/conversations/${conversationId}/messages`,
    { method: "POST", body: JSON.stringify({ text }) },
    token,
  );
