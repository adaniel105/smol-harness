from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv(override=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WORKDIR = Path.cwd()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

MODEL = os.environ["MODEL_ID"]
PRIMARY_MODEL = MODEL
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")

DEFAULT_MAX_TOKENS = 8000
ESCALATED_MAX_TOKENS = 16000
MAX_RETRIES = 3
MAX_CONSECUTIVE_529 = 2
MAX_RECOVERY_RETRIES = 2
BASE_DELAY_MS = 500

CONTEXT_LIMIT = 50000
PERSIST_THRESHOLD = 30000
KEEP_RECENT_TOOL_RESULTS = 3
IDLE_POLL_INTERVAL = 5
IDLE_TIMEOUT = 60
