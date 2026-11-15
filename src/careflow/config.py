import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_REPAIRS = 2
REPAIR_ERROR_MAX_CHARS = 500
INTAKE_RECENT_TURNS = 6
INTAKE_MAX_ITEMS = 5
SUMMARY_MAX_CHARS = 200
LLM_TIMEOUT_SECONDS = 60
CLINIC_TIMEZONE = "Asia/Kolkata"
SLOT_DAYS_AHEAD = 21
SLOT_TIMES = ("09:00", "10:00", "11:00", "14:00")
SLOT_MINUTES = 30
AGENT_MAX_STEPS = 8
THOUGHT_MAX_CHARS = 300
FREE_SLOTS_LIMIT = 10
TASK_TITLE_MAX_CHARS = 120
TOOL_ERROR_MAX_CHARS = 300
IDEMPOTENCY_HASH_CHARS = 16
LLM_MAX_ATTEMPTS = 4
RETRY_BASE_SECONDS = 1
RETRY_MAX_SECONDS = 20
BREAKER_FAILURES = 5
BREAKER_WINDOW_SECONDS = 60
BREAKER_COOLDOWN_SECONDS = 30
MESSAGE_MAX_CHARS = 2000
SESSION_TOKEN_BYTES = 32
EVAL_CASE_INTERVAL_SECONDS = 10
MEMORY_EVAL_CASE_INTERVAL_SECONDS = 35
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
MODEL_CACHE_DIR = PROJECT_ROOT / "data" / "models"
CHARS_PER_TOKEN = 4
WORKING_TOKEN_BUDGET = 1500
WORKING_KEEP_TURNS = 4
SESSION_SUMMARY_MAX_CHARS = 1200
KEY_FACTS_MAX = 12
EPISODE_MAX_CHARS = 400
MEMORY_VALUE_MAX_CHARS = 200
RECALL_EPISODES = 3
CORPUS_DIR = PROJECT_ROOT / "corpus"
RERANKER_MODEL = "BAAI/bge-reranker-base"
CHUNK_MAX_CHARS = 1200
RECALL_CANDIDATES = 20
RRF_K = 60
CONTEXT_CHUNKS = 4
EVAL_TOP_K = 5
ANSWER_SENTENCES_MAX = 6
ANSWER_SENTENCE_MAX_CHARS = 300
RETRIEVAL_RESULT_MAX_CHARS = 600
SUPERVISOR_MAX_STEPS = 8
MAX_REPLANS = 2
SLOT_SCAN_LIMIT = 200
MORNING_END_HOUR = 12
TIMELINE_LIMIT = 200
RED_FLAG_TERMS = (
    "chest pain",
    "chest tightness",
    "can't breathe",
    "cannot breathe",
    "severe breathlessness",
    "struggling to breathe",
    "fainted",
    "passed out",
    "unconscious",
    "blue lips",
    "new confusion",
    "suddenly confused",
    "seizure",
    "stroke",
    "face drooping",
    "coughing blood",
    "coughing up blood",
    "vomiting blood",
    "suicid",
    "kill myself",
)
CLINICAL_TERMS = (
    "mg",
    "dose",
    "dosage",
    "tablet",
    "pill",
    "medic",
    "drug",
    "insulin",
    "inhaler",
    "allerg",
    "diagnos",
    "symptom",
    "pain",
    "fever",
    "temperature",
    "swell",
    "breath",
    "weight",
    "glucose",
    "sugar",
    "blood pressure",
    "oxygen",
    "heart rate",
    "wound",
    "bleed",
    "dizz",
    "faint",
    "nause",
    "vomit",
    "surgery",
)


@dataclass(frozen=True)
class Settings:
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_fallback_model: str = ""
    llm_temperature: float = 0
    database_url: str = ""
    test_database_url: str = ""
    coordinator_token: str = ""


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_fallback_model=os.getenv("LLM_FALLBACK_MODEL", ""),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE") or 0),
        database_url=os.getenv("DATABASE_URL", ""),
        test_database_url=os.getenv("TEST_DATABASE_URL", ""),
        coordinator_token=os.getenv("COORDINATOR_TOKEN", ""),
    )
