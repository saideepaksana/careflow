CREATE TABLE workflow_runs (
  thread_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  status TEXT NOT NULL CHECK (status IN
    ('running', 'awaiting_confirmation', 'awaiting_coordinator', 'done', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE UNIQUE INDEX one_pending_confirmation
  ON workflow_runs (conversation_id) WHERE status = 'awaiting_confirmation';
ALTER TABLE coordinator_tasks
  ADD COLUMN kind TEXT NOT NULL DEFAULT 'handoff'
    CHECK (kind IN ('escalation', 'approval', 'handoff')),
  ADD COLUMN thread_id TEXT REFERENCES workflow_runs(thread_id);
ALTER TABLE messages ADD COLUMN idempotency_key TEXT UNIQUE;
