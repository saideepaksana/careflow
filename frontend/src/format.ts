import { TimelineEvent } from "./api";

const CLINIC_TIME_ZONE = "Asia/Kolkata";

const dateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: CLINIC_TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const time = new Intl.DateTimeFormat("en-GB", { timeZone: CLINIC_TIME_ZONE, hour: "2-digit", minute: "2-digit" });
const dateOnly = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

const SPEAKERS: Record<string, string> = { patient: "Patient", assistant: "CareFlow", coordinator: "Coordinator" };

export const formatDateTime = (value: string) => dateTime.format(new Date(value));
export const formatTime = (value: string) => time.format(new Date(value));
export const formatDay = (value: string) => dateOnly.format(new Date(`${value}T00:00:00Z`));

const humanize = (text: string) => text.replaceAll("_", " ");

export function timelineLabel(event: TimelineEvent): string {
  switch (event.kind) {
    case "message":
      return SPEAKERS[String(event.detail.role)] ?? "Message";
    case "task_created":
      return `Task opened (${String(event.detail.priority)})`;
    case "task_resolved":
      return "Task resolved";
    case "action":
      return "Action";
    case "memory":
      return "Remembered";
    case "workflow":
      return "Request";
    default:
      return humanize(event.kind);
  }
}

const CODED_TEXT_KINDS = new Set(["action", "workflow"]);

const CODE_TEXT: Record<string, string> = {
  done: "Request finished",
  awaiting_confirmation: "Waiting for the patient to confirm",
  awaiting_coordinator: "Waiting for care-team approval",
  failed: "Request failed",
  running: "In progress",
  book_appointment: "Appointment booked",
  reschedule_appointment: "Appointment moved",
  cancel_appointment: "Appointment cancelled",
};

function codeText(code: string): string {
  const words = humanize(code);
  return CODE_TEXT[code] ?? words.charAt(0).toUpperCase() + words.slice(1);
}

export const timelineText = (event: TimelineEvent) =>
  CODED_TEXT_KINDS.has(event.kind) ? codeText(event.text) : event.text;
