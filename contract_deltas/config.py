"""Configuration in one place: region, model, limits, timeouts, rule thresholds, paths."""

import re
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"

REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"

MAX_TOKENS = 2048
MAX_TOKENS_FACTOR = 2
TEMPERATURE = 0
MAX_APP_RETRIES = 2  # calls per deal = 1 + MAX_APP_RETRIES

TOTAL_MAX_ATTEMPTS = 4  # botocore transport tries per call
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 120

# Failure table: what each stopReason means for the retry loop.
RETRY_FROM_ORIGINAL_STOP_REASONS = frozenset({"malformed_tool_use", "malformed_model_output"})
NOT_RETRYABLE_STOP_REASONS = frozenset({"content_filtered", "guardrail_intervened", "model_context_window_exceeded"})
TEXT_ONLY_STOP_REASONS = frozenset({"end_turn", "stop_sequence"})

# Suggestion rule thresholds (compared with Fraction, never floats).
R1_MIN_BUYER_SHARE = Fraction(3, 4)
R2_MIN_DEALS_WITH = 3
R2_MIN_DEALS_WITHOUT = 3
R2_MIN_WIN_RATE_GAP = Fraction(3, 10)
R3_MAX_WIN_RATE_GAP = Fraction(-3, 10)
R3_MIN_EXTRA_DAYS = 20
R4_MIN_DEALS_ADDED = 3


def slug(model_id: str) -> str:
    """Model id as a path segment that is legal on every OS (inference profile ids can end in ':0')."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", model_id)
