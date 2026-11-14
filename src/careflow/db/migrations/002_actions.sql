CREATE TABLE action_results (
  idempotency_key TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  action TEXT NOT NULL, result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
