CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  owner_patient_id TEXT REFERENCES patients(id),
  condition TEXT NOT NULL,
  version INT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('current', 'superseded')),
  effective_from DATE NOT NULL);
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  heading TEXT NOT NULL,
  content TEXT NOT NULL,
  search_text tsvector GENERATED ALWAYS AS (to_tsvector('english', heading || ' ' || content)) STORED,
  embedding vector(384) NOT NULL);
CREATE INDEX chunks_search_text ON chunks USING gin (search_text);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
