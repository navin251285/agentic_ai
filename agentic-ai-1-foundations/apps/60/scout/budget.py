"""Run and daily budgets, checked before each model call with its worst case (lesson 54)."""
from collections import defaultdict
from datetime import datetime, timezone
from .config import cost_usd

class RunBudget:
    def __init__(self, max_usd: float, max_tokens: int = 50_000, first_input: int = 600, margin: int = 200):
        self.max_usd, self.max_tokens, self.margin = max_usd, max_tokens, margin
        self.spent_usd, self.tokens, self.last_in = 0.0, 0, first_input - margin

    def can_afford(self, model: str, max_out: int) -> bool:
        est_in = self.last_in + self.margin
        return (self.spent_usd + cost_usd(model, est_in, max_out) <= self.max_usd
                and self.tokens + est_in + max_out <= self.max_tokens)

    def charge(self, model: str, tokens_in: int, tokens_out: int) -> None:
        self.spent_usd += cost_usd(model, tokens_in, tokens_out)
        self.tokens += tokens_in + tokens_out
        self.last_in = tokens_in

class DailyBudget:
    """Spend per user per UTC day. In production this lives in a shared store, not a dict."""
    def __init__(self, max_usd: float, today=lambda: datetime.now(timezone.utc).date()):
        self.max_usd, self.today, self.spent = max_usd, today, defaultdict(float)

    def left(self, user: str) -> float:
        return self.max_usd - self.spent[(user, self.today())]

    def add(self, user: str, usd: float) -> None:
        self.spent[(user, self.today())] += usd
