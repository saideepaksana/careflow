# CareFlow frontend

React + TypeScript (Vite) desktop app. The Vite dev server proxies `/api` to the FastAPI backend on port 8000.

- Patient portal: chat that waits for each reply and refreshes every 10 seconds to show care-team messages, with Yes/No confirmation for appointment changes.
- Coordinator console: priority queue, approve / deny / resolve with a note to the patient, patient timeline and care-plan progress.

Times are shown in the clinic time zone (Asia/Kolkata, as in `src/careflow/config.py`).

The app was built in Milestone 2 (chat) and extended in Milestone 6 (console).
