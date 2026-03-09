"""Central configuration for E2E benchmark."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
SCENARIOS_DIR = BASE_DIR / "scenarios"

# Models - CRITICAL: do NOT use gpt-4o-mini
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Benchmark settings
MAX_RETRIES = 3
REQUEST_TIMEOUT = 120
SELF_IMPROVEMENT_ROUNDS = 3

# Agent system labels
SYSTEM_A = "openclaw_cokac_amp"   # Our tri-agent system
SYSTEM_B = "claude_standalone"     # Claude Code multi-agent
SYSTEM_C = "codex_standalone"      # Codex standalone

RESULTS_DIR.mkdir(exist_ok=True)
