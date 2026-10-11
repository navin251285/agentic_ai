"""Scout v2: a production-ready research assistant over local notes (agentic-ai-1, lesson 55)."""
from .budget import DailyBudget, RunBudget
from .config import LIMITS, MODEL, check_config, cost_usd
from .guard import Guard
from .loop import run_scout, serve
from .tools import NOTES, SCHEMAS, make_tools, run_tool
from .tracing import Tracer, redact

__version__ = "2.0.0"
