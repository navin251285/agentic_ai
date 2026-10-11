# %% [markdown]
# # Solutions · Part 7: Organisation scale and what's next
# Answers to the "Try it" exercises. Try each one yourself first.

# %% [markdown]
# ## Lesson 56
# Scout for 20,000 users on `gemini-3.8-flash` after the promo. This notebook runs on its own, so it
# rebuilds lesson 56's production run from the same recorded files and keeps the same demand guesses and
# burst factor (1.51x, from lesson 56's seeded simulation).

# %%
import json, math, statistics
from pathlib import Path

runs = json.loads(Path("../data/recorded/55.json").read_text())["eval"]     # recorded output, lesson 55
chat = json.loads(Path("../data/recorded/41.json").read_text())["fixed"]    # recorded output, lesson 41
calls = statistics.mean(len(r["calls"]) for r in runs)
RUN = {"in": calls * statistics.mean(c["prompt"] for c in chat),
       "out": statistics.mean(sum(c["out"] for c in r["calls"]) for r in runs)}
hit = sum(c["cached"] for c in chat) / sum(c["prompt"] for c in chat)
DEMAND = {"users": 20_000, "daily_active": 0.60, "questions_per_day": 6, "workdays_per_month": 22,
          "peak_hour_share": 0.15}
BURST = 68 / 45                                  # lesson 56: busiest minute / average peak minute

# %% [markdown]
# The new price table is a copy; lesson 56's is untouched. Vertex Flash tiers have the same TPM as
# Flash-Lite.

# %%
PRICES_AFTER_PROMO = {"gemini-3.8-flash": {"input": 1.50, "cached": 0.15, "output": 7.50}}
TIERS = [("Tier 1", 250, 2_000_000), ("Tier 2", 2_000, 4_000_000),
         ("Tier 3", 50_000, 10_000_000), ("Tier 4", math.inf, 50_000_000)]   # (name, spend up to, TPM)

p = PRICES_AFTER_PROMO["gemini-3.8-flash"]
per_day = DEMAND["users"] * DEMAND["daily_active"] * DEMAND["questions_per_day"]
busiest = per_day * DEMAND["peak_hour_share"] / 60 * BURST
need_tpm = busiest * (RUN["in"] + RUN["out"])
cost_run = (RUN["in"] * ((1 - hit) * p["input"] + hit * p["cached"]) + RUN["out"] * p["output"]) / 1e6
bill = cost_run * per_day * DEMAND["workdays_per_month"]
name, _, cap = next(t for t in TIERS if bill <= t[1])
print(f"busiest minute {busiest:.0f} runs -> {need_tpm:,.0f} TPM")
print(f"${cost_run:.5f}/run -> ${bill:,.0f} a month -> earns {name} ({cap / 1e6:.0f}M TPM)")
print(f"busiest minute uses {need_tpm / cap:.0%} of it:", "fits with headroom" if need_tpm <= 0.7 * cap else "does not fit")

# %% [markdown]
# The dearer model earns a bigger tier: the bill moves Scout into Tier 3 (10M TPM), and the busiest
# minute (~6.2M TPM) uses about 62% of it, inside the 70% plan.

# %% [markdown]
# ## Lesson 57
# A rate-based breaker for a flapping provider. This cell is self-contained: it repeats lesson 57's
# `FakeClock` and `CircuitBreaker` so the two can be compared.

# %%
from collections import deque

class FakeClock:
    def __init__(self): self.now = 0.0
    def __call__(self) -> float: return self.now

class CircuitBreaker:                                  # lesson 57, unchanged
    def __init__(self, clock, threshold=3, cooldown=60.0):
        self.clock, self.threshold, self.cooldown = clock, threshold, cooldown
        self.state, self.failures, self.opened_at, self.events = "closed", 0, 0.0, []
    def _move(self, state):
        if state != self.state:
            self.state = state
            self.events.append((self.clock(), state))
    def allow(self):
        if self.state == "open" and self.clock() - self.opened_at >= self.cooldown:
            self._move("half_open")
        return self.state != "open"
    def record_success(self):
        self.failures = 0
        self._move("closed")
    def record_failure(self):
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.threshold:
            self.opened_at = self.clock()
            self._move("open")

# %% [markdown]
# `RateBreaker` keeps the last `window` outcomes. It opens when at least `max_error_rate` of them
# failed (given at least `min_calls`), and clears the window when it closes again.

# %%
class RateBreaker(CircuitBreaker):
    def __init__(self, clock, window=10, max_error_rate=0.5, min_calls=6, cooldown=60.0):
        super().__init__(clock, threshold=None, cooldown=cooldown)
        self.recent, self.max_error_rate, self.min_calls = deque(maxlen=window), max_error_rate, min_calls

    def record_success(self):
        self.recent.append(True)
        if self.state == "half_open":
            self.recent.clear()
            self._move("closed")

    def record_failure(self):
        self.recent.append(False)
        rate = self.recent.count(False) / len(self.recent)
        if self.state == "half_open" or (len(self.recent) >= self.min_calls and rate >= self.max_error_rate):
            self.opened_at = self.clock()
            self._move("open")

# %% [markdown]
# Feed both the flapping outcomes, one call every 5 s, and only while `allow()` says the primary may be tried.

# %%
for breaker in (CircuitBreaker(FakeClock()), RateBreaker(FakeClock())):
    tried = 0
    for i, ok in enumerate([True, False] * 10):
        breaker.clock.now = i * 5.0
        if breaker.allow():
            tried += 1
            breaker.record_success() if ok else breaker.record_failure()
    print(f"{type(breaker).__name__:15} primary tried {tried:2}/20 | events {breaker.events}")

# %% [markdown]
# The consecutive-failure breaker never opens: no two failures are in a row, so all 20 calls hit the
# flapping primary. The rate breaker opens at t=25 (3 of 6 failed), skips calls during the cooldown, and
# its half-open trial at t=85 fails, so it reopens: 7 of 20 calls reached the primary.

# %% [markdown]
# ## Lesson 58
# A break hitting p = 0.02 of requests, caught within 3 hours with 95% confidence. This notebook runs on
# its own, so it rebuilds the small pieces of lesson 58 it needs (cost per run from lesson 55's recorded
# runs, `detect_prob`, a `Decision`). Three hours of n cases is 3n draws, so find the smallest n with
# `1 - (1 - p) ** (3 * n) >= 0.95`.

# %%
import json, math, statistics
from dataclasses import dataclass
from pathlib import Path

EVAL = json.loads(Path("../data/recorded/55.json").read_text())["eval"]     # recorded output, lesson 55
COST_PER_RUN = statistics.mean(r["cost_usd"] for r in EVAL)

def detect_prob(p: float, n: int) -> float:
    return 1 - (1 - p) ** n

def cases_per_hour(p: float, hours: int, confidence: float = 0.95) -> int:
    return math.ceil(math.ceil(math.log(1 - confidence) / math.log(1 - p)) / hours)

n = cases_per_hour(0.02, 3)
print(f"{n} cases an hour -> caught within 3 h {detect_prob(0.02, 3 * n):.1%} | within 1 h {detect_prob(0.02, n):.1%}")
print(f"cost: ${n * 24 * 30 * COST_PER_RUN:.2f} a month")

# %% [markdown]
# Decision D, with a check that holds for that canary size (and fails for one case fewer).

# %%
@dataclass
class Decision:
    case: str
    change: str
    check: callable

CANARY_D = {"cases_per_hour": n, "target_p": 0.02, "within_hours": 3}
def check_d(cfg: dict = CANARY_D) -> bool:
    return detect_prob(cfg["target_p"], cfg["within_hours"] * cfg["cases_per_hour"]) >= 0.95

DESIGN_NOTE = [Decision("A postmortem of three recent issues (Anthropic)",
                        f"Canary of {n} golden cases an hour, so a 1-in-50 break is caught within 3 hours.", check_d)]
for d in DESIGN_NOTE:
    print(d.change, "->", "holds" if d.check() else "BROKEN")
print("one case fewer holds?", check_d({**CANARY_D, "cases_per_hour": n - 1}))

# %% [markdown]
# ## Lesson 59
# `behind` compares tuples of integers (never strings). Minors only count inside the same major: after a
# major bump the minor numbers restart, so "minors behind" means nothing across majors. Runs on the
# recorded fetch from lesson 59 (recorded output, fetched 2026-10-11).

# %%
import json
from importlib.metadata import version
from pathlib import Path

RECORDED = json.loads(Path("../data/recorded/59.json").read_text())
INSTALLED = {p: version(p) for p in RECORDED["packages"]}

def as_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".")[:3])

def behind(installed: str, latest: str) -> tuple[int, int]:
    have, new = as_tuple(installed), as_tuple(latest)
    majors = max(new[0] - have[0], 0)
    minors = max(new[1] - have[1], 0) if majors == 0 else 0
    return majors, minors

# %% [markdown]
# Unit checks first, then the to-do lines for the watch list.

# %%
assert behind("1.11.0", "1.13.0") == (0, 2)
assert behind("2.54.0", "3.2.0") == (1, 0)
assert behind("1.9.0", "1.13.0") == (0, 4)          # the string-compare trap from the lesson
todo = []
for pkg, d in RECORDED["packages"].items():
    majors, minors = behind(INSTALLED[pkg], d["latest"])
    if majors or minors >= 2:
        todo.append(f"[upgrade] {pkg} {INSTALLED[pkg]} -> {d['latest']} ({majors} major, {minors} minor behind)")
print("\n".join(todo) or "nothing to upgrade")

# %% [markdown]
# ## Lesson 60
# 1. A new tool, `word_count`, on a copy of Scout v3. Lesson 60 wrote the package to `../apps/60/`;
#    run that notebook first. The copy keeps lesson 60's own package untouched.

# %%
import hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

SRC, TRY = Path("../apps/60"), Path("../apps/60_try")
shutil.rmtree(TRY, ignore_errors=True)
shutil.copytree(SRC, TRY, ignore=shutil.ignore_patterns("__pycache__", "DESIGN.md"))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:12]
LOOP_BEFORE = sha(TRY / "scout" / "loop.py")
print("copied v3; loop.py", LOOP_BEFORE)

# %% [markdown]
# The tool closes over the user's folder, like `write_file`, so it is added inside a wrapped `make_tools`.
# It uses the same confinement check: the resolved file must sit directly in the folder.

# %%
%%writefile -a ../apps/60_try/scout/tools.py

# ---- Try it (lesson 60): word_count, a new tool added outside the loop ----
_make_v3_tools = make_tools

def make_tools(notes: list[dict], folder: Path) -> dict:
    folder = Path(folder).resolve()
    def word_count(filename: str) -> int:
        target = (folder / filename).resolve()
        if target.parent != folder:
            raise ValueError(f"'{filename}' is outside Scout's folder. Use a plain file name, e.g. filename='plan.txt'.")
        if not target.is_file():
            raise FileNotFoundError(f"'{filename}' is not in Scout's folder. Use the name of a saved file.")
        return len(target.read_text().split())
    return {**_make_v3_tools(notes, folder), "word_count": word_count}

SCHEMAS.append(_schema("word_count", "Count the words in one file saved in Scout's folder.", filename="string"))

# %% [markdown]
# It only reads, so it is granted as read-only in both tasks.

# %%
%%writefile -a ../apps/60_try/scout/guard.py

# ---- Try it (lesson 60): grant word_count ----
READ_ONLY.add("word_count")
for allowed in PERMISSIONS.values():
    allowed.add("word_count")

# %% [markdown]
# Two tests with a scripted model (no real model, no recording): in a `save` task Ana approves the write,
# then the model counts the new file's words; and a path outside the folder comes back as an error.

# %%
%%writefile ../apps/60_try/tests/test_word_count.py
from scout.fake import ScriptedModel
from helpers import run

WRITE = {"tool_calls": [{"name": "write_file", "args": {"filename": "habitat.txt", "text": "Keep the habitat clean."}}]}
COUNT = {"tool_calls": [{"name": "word_count", "args": {"filename": "habitat.txt"}}]}
ESCAPE = {"tool_calls": [{"name": "word_count", "args": {"filename": "../secret.txt"}}]}
approve = lambda call: {"action": "approve", "reviewer": "ana", "reason": ""}

def test_word_count_after_a_write(tmp_path):
    out = run(tmp_path, ScriptedModel([WRITE, COUNT, {"text": "habitat.txt has 4 words."}]), task="save", approver=approve)
    assert (out["stop"], out["errors"], out["denied"]) == ("end_of_turn", 0, 0)
    assert out["messages"][4]["content"] == "4"

def test_word_count_stays_in_the_folder(tmp_path):
    out = run(tmp_path, ScriptedModel([ESCAPE, {"text": "I can only read files in my folder."}]))
    assert out["errors"] == 1 and "outside Scout's folder" in out["messages"][2]["content"]

# %% [markdown]
# All tests in a fresh Python, then the loop's hash.

# %%
out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no", "tests"],
                     cwd=TRY, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
summary = re.sub(r" in \d+\.\d+s", "", out.stdout.strip().splitlines()[-1])
print(summary)
assert out.returncode == 0, out.stdout[-2000:]
print("loop.py unchanged:", sha(TRY / "scout" / "loop.py") == LOOP_BEFORE == sha(SRC / "scout" / "loop.py"))

# %% [markdown]
# 2. The eval's search queries, from the recorded file alone, run against the same substring search
#    (re-implemented here in two lines so nothing needs importing).

# %%
import json
NOTES = ["Mars has two small moons, Phobos and Deimos.", "Venus spins backwards compared with most planets.",
         "A day on Mars lasts about 24 hours and 39 minutes.", "Jupiter is the largest planet in the solar system.",
         "The rover Perseverance landed on Mars in February 2021.", "Saturn's rings are mostly made of ice."]
rows = json.load(open("../data/recorded/60.json"))["eval"]
for r in rows:
    for name, args in r["asked"]:
        if name == "search_notes":
            hits = [n for n in NOTES if args["query"].strip().lower() in n.lower()][:5]
            print(f"{r['id']:13} query {args['query']!r:18} -> {len(hits)} notes")

# %% [markdown]
# Every query found something, but six of the ten were just "Mars", and each returned all three Mars
# notes, so the model had to pick the right one itself. Those questions (moons, moon names, day length,
# minutes, seconds, hours) gain most from a retriever that ranks by meaning and returns the best note first: track 2.
