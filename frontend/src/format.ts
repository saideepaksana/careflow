import { TimelineEvent } from "./api";

const dateTime = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const dateOnly = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

const SPEAKERS: Record<string, string> = { patient: "Patient", assistant: "CareFlow", coordinator: "Coordinator" };

export const formatDateTime = (value: string) => dateTime.format(new Date(value));
export const formatTime = (value: string) => time.format(new Date(value));
export const formatDay = (value: string) => dateOnly.format(new Date(`${value}T00:00:00Z`));

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
      return event.kind;
  }
}

export const humanize = (text: string) => text.replaceAll("_", " ");
