import os

FORKD_ENABLED = os.getenv("FORKD_ENABLED", "false").lower() == "true"
FORKD_CONTROLLER_URL = os.getenv("FORKD_CONTROLLER_URL", "http://127.0.0.1:8889")
FORKD_SNAPSHOT_TAG = os.getenv("FORKD_SNAPSHOT_TAG", "agent-harness-base")
FORKD_DEFAULT_MEMORY_MB = int(os.getenv("FORKD_DEFAULT_MEMORY_MB", "512"))
FORKD_DEFAULT_TIMEOUT = int(os.getenv("FORKD_DEFAULT_TIMEOUT", "120"))
FORKD_SANDBOX_POOL_SIZE = int(os.getenv("FORKD_SANDBOX_POOL_SIZE", "4"))
