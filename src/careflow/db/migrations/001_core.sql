CREATE TABLE patients (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, date_of_birth DATE NOT NULL, phone TEXT NOT NULL);
CREATE TABLE encounters (
  id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
  admitted_on DATE NOT NULL, discharged_on DATE NOT NULL, primary_diagnosis TEXT NOT NULL);
CREATE TABLE care_plans (
  id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
  encounter_id TEXT NOT NULL REFERENCES encounters(id), version INT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('published', 'superseded')),
  published_on DATE NOT NULL, UNIQUE (patient_id, version));
CREATE UNIQUE INDEX one_published_plan ON care_plans (patient_id) WHERE status = 'published';
CREATE TABLE care_plan_items (
  id TEXT PRIMARY KEY, care_plan_id TEXT NOT NULL REFERENCES care_plans(id),
  kind TEXT NOT NULL CHECK (kind IN ('follow_up', 'lab', 'medication', 'warning_sign', 'activity_rule')),
  description TEXT NOT NULL, specialty TEXT, due_within_days INT,
  severity TEXT CHECK (severity IN ('emergency', 'urgent')),
  rule JSONB);
CREATE TABLE clinicians (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, specialty TEXT NOT NULL);
CREATE TABLE slots (
  id TEXT PRIMARY KEY, clinician_id TEXT NOT NULL REFERENCES clinicians(id),
  starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL);
CREATE TABLE appointments (
  id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
  slot_id TEXT NOT NULL REFERENCES slots(id),
  care_plan_item_id TEXT REFERENCES care_plan_items(id),
  status TEXT NOT NULL CHECK (status IN ('booked', 'cancelled')),
  idempotency_key TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE UNIQUE INDEX one_booking_per_slot ON appointments (slot_id) WHERE status = 'booked';
CREATE TABLE conversations (
  id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE messages (
  id BIGSERIAL PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL CHECK (role IN ('patient', 'assistant', 'coordinator')),
  content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE coordinator_tasks (
  id BIGSERIAL PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
  priority TEXT NOT NULL CHECK (priority IN ('emergency', 'urgent', 'routine')),
  status TEXT NOT NULL CHECK (status IN ('open', 'resolved')),
  title TEXT NOT NULL, detail JSONB NOT NULL DEFAULT '{}',
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), resolved_at TIMESTAMPTZ);
CREATE TABLE audit_events (
  id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  patient_id TEXT REFERENCES patients(id), actor TEXT NOT NULL, event TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}', trace_id TEXT);
