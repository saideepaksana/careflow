CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE conversations
  ADD COLUMN summary TEXT NOT NULL DEFAULT '',
  ADD COLUMN summarized_through BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN ended_at TIMESTAMPTZ;
CREATE TABLE memories (
  id BIGSERIAL PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  type TEXT NOT NULL CHECK (type IN ('episodic', 'semantic')),
  key TEXT,
  content TEXT NOT NULL,
  source_conversation_id TEXT NOT NULL REFERENCES conversations(id),
  embedding vector(384) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  superseded_by BIGINT REFERENCES memories(id),
  CHECK ((type = 'semantic') = (key IS NOT NULL)));
CREATE UNIQUE INDEX one_active_semantic_key
  ON memories (patient_id, key) WHERE type = 'semantic' AND superseded_by IS NULL;
CREATE INDEX memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
