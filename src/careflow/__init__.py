import os

# Use the cost map pinned with litellm instead of downloading one at import time.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
