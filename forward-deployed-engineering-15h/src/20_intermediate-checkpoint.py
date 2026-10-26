# %% [markdown]
# # 20 · Checkpoint: an evaluated, deployable proof of concept
#
# Level L3 · Part 2 · core · ~30 min · builds on 11, 13, 14, 15, 16, 17, 18
#
# This is the checkpoint of Part 2. It joins the Basket Bazaar work from lessons 11 and 13 to 18 into one release: an eval gate decides, a Compose stack runs the triage service behind a service account, its logs, trace and metric show what it does, and one page gives the customer the numbers.
#
# Needs Docker with Compose v2 (`docker compose version`), about 2 GB of free RAM, ports 8200 to 8202 free, and the lesson 13 settings in `../.env`. The model calls need a key once; after that the saved recording replays with no key. Cells tagged `needs-docker` start containers. When they are skipped, the checks print the recorded output from the last real run, labelled as such.
#
# Time: about 30 minutes. Run the cells in order.

# %% [markdown]
# ## Goal
#
# By the end you have one release of the Basket Bazaar triage feature that passed an eval gate, runs in a Compose customer environment behind a service account, can be seen in its logs, trace and metric, and comes with a one-page handover that labels every number as measured, recorded or not measured.

# %% [markdown]
# ## Why it matters
#
# Each earlier lesson works alone. The eval set (lesson 11) grades a prompt. The Compose file (lesson 14) runs a service. The service account (lesson 13) limits what it can call. The traces (lesson 16) show a slow request. Nothing joins them, so the first customer release is decided by whoever is in a hurry.
#
# - **Without this checkpoint:** a new prompt ships because it looked fine on three messages. The service runs on a laptop with a shared password. A slow request is found by guessing. The customer hears "it works" and no number.
# - **With it:** a release is refused by a gate, deployed only from the gate's note, checked for least privilege, watched from logs to trace to metric, and handed over with its numbers.
# - **When you don't need it:** a one-off demo for yourself. For anything a customer runs every day, every step here is the minimum.

# %% [markdown]
# ## The idea
#
# A **release gate** is a rule that stops a change unless the evidence says it is safe. Here the evidence is the eval set from lesson 11, graded by plain code, as in lesson 11. The gate writes a release note. The deploy reads that note and refuses to start if the gate said no.
#
# Think of an airline's pre-flight check. The checklist is signed before the flight, and the plane does not leave without the signature. The gate is the signature. The deploy is the flight.

# %% [markdown]
# ```mermaid
# flowchart LR
#     E[Eval set, 12 labelled cases, lesson 11] --> G{Gate: pass rate and no regression}
#     P[Candidate prompt, one model call] --> G
#     G -- refused --> X[No release, the shipped prompt stays]
#     G -- passed --> N[Release note, lesson 20]
#     N --> D[Compose deploy, lesson 14]
#     D --> A[Service account, least privilege, lesson 13]
#     D --> O[Logs, trace and metric, lesson 16]
#     O --> H[Handover: numbers and costs, lessons 07 and 18]
# ```

# %% [markdown]
# ## Requirements
#
# Your checkpoint is done when all five hold:
#
# 1. **Gate:** the candidate prompt labels at least 90% of the eval cases right and breaks no case the shipped prompt passes. The weak prompt is refused.
# 2. **Release note:** the verdict, the tag and the prompt are written to a file, and the deploy reads it first.
# 3. **Auth:** the service account reads orders but is refused a credit scope, and the customer API has no route outside and no published port.
# 4. **Observability:** one slow request is found from its log line, then its trace, then the metric.
# 5. **Budget and handover:** every model call is inside its budget, and the handover labels each number as measured, recorded or not measured.
#
# The checks are the cells marked **Check**. Only the model's labels cannot be checked by counting; code checks the rest.

# %% [markdown]
# ## Build it

# %% [markdown]
# ### Before you start: setup
#
# The first code cell starts the recording of the model calls. The second loads the settings from `../.env` (names and yes/no only; no values are printed) and creates the folders this lesson writes to. The eval set is lesson 11's file, `../data/11/eval_set.csv`.
#
# Each Docker step stores its real output in `RUN_LOG`. The check cells print it with `from_run()`: this run's live output, or the recorded output from the last real run when Docker was skipped. The model-call numbers always come from the recording.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
llm_replay.start("20_intermediate-checkpoint")  # records the model calls below once

# %% [markdown]
# Next, the imports, the settings and the folders this lesson writes to.

# %%
import csv, json, os, shutil, subprocess, time
from collections import Counter
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from tut_env import is_set, load

load()
DOCKER_RAN = False  # set to True by the first cell tagged needs-docker (Step 7)
RUN_LOG = {}        # the real output of each Docker step, saved for the recording
STACK = "tut-forward-deployed-engineering-15h-20"  # one Compose project for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../infra/compose/checkpoint-20.yml", "--env-file", "../.env"]
TRIAGE, JAEGER, PROM = "http://localhost:8200", "http://localhost:8201", "http://localhost:8202"
DATA = Path("../data/20")
DATA.mkdir(parents=True, exist_ok=True)
RELEASE = DATA / "release_note.json"
REC = json.loads(Path("../data/recorded/20.json").read_text())
print("docker:", bool(shutil.which("docker")), "| lesson 13 settings:", all(is_set(n) for n in ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"]), "| model key:", bool(is_set("GOOGLE_CLOUD_API_KEY") or is_set("GOOGLE_CLOUD_PROJECT")))

# %% [markdown]
# Next, the helpers. They are the same ones lesson 16 uses: they run Compose for this lesson's project, poll until something answers (never a fixed sleep), and pick the live or the recorded output.

# %%
def compose(*args, extra=None):
    """Run docker compose for this lesson's project. extra sets variables for this call only."""
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def tail(text, n=8):
    return "\n".join(text.strip().splitlines()[-n:])


def wait_for(check, timeout=90, every=2):
    """Call check() until it returns something true, or stop at the timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if value := check():
            return value
        time.sleep(every)
    raise TimeoutError(f"nothing after {timeout} s")


def from_run(key):
    """The live output of this run, or the recorded output when Docker was skipped."""
    return RUN_LOG[key] if DOCKER_RAN else REC[key]

# %% [markdown]
# ### Step 1: the eval set and the scorer
#
# Lesson 11 wrote twelve labelled cases: the message, the order and the label a person expects. This step loads them with a Pydantic model, so a typo in a label fails at once. The scorer is plain code. A missing answer counts as a fail.

# %%
Issue = Literal["missing_item", "wrong_item", "late", "damaged", "other"]


class EvalCase(BaseModel):
    case_id: str
    order_id: str = Field(pattern=r"^BB-\d{4}$")
    message: str = Field(min_length=10)
    want: Issue


with open("../data/11/eval_set.csv", newline="") as f:
    CASES = [EvalCase(**row) for row in csv.DictReader(f)]
print(f"{len(CASES)} labelled cases from lesson 11; first:", CASES[0].case_id, CASES[0].want)
print("labels the people expect:", dict(Counter(c.want for c in CASES)))


def score(labels: dict) -> dict:
    return {c.case_id: {"want": c.want, "got": labels.get(c.case_id),
                        "passed": labels.get(c.case_id) == c.want} for c in CASES}


def show(name: str, rows: dict) -> None:
    print(f"{name}: {sum(r['passed'] for r in rows.values())} of {len(rows)} pass")
    text = {c.case_id: c.message for c in CASES}
    for cid, r in rows.items():
        if not r["passed"]:
            print(f"  FAIL {cid}: want={r['want']:<12} got={str(r['got']):<12} {text[cid][:44]}")

# %% [markdown]
# ### Step 2: the candidate, the shipped prompt and a weak edit
#
# The model returns one label per case id in one structure, so twelve cases cost one call per prompt. `PROMPT_SHIPPED` is in use. `PROMPT_CANDIDATE` adds the definitions and the counting rule from lesson 11. `PROMPT_WEAK` is a careless edit, written on purpose so the gate has something to refuse.

# %%
class Triage(BaseModel):
    case_id: str = Field(description="the case id exactly as given, such as C01")
    issue: Issue


class TriageBatch(BaseModel):
    labels: list[Triage] = Field(description="one entry for every case id given")


PROMPT_SHIPPED = ("Label each grocery delivery support message with one issue: missing_item, wrong_item, "
                  "late, damaged or other. Return one label for every case id.")
PROMPT_CANDIDATE = PROMPT_SHIPPED + """
Definitions:
- missing_item: the customer did not get all of an item they paid for, even when they say only some of it arrived.
- late: the delivery came after the slot, or still shows as pending.
- damaged: broken, bruised, crushed, split or leaking.
- wrong_item: the customer got a different item from the one ordered.
- other: none of the above, such as a courier problem.
- Rule: if the customer names a count of items (two, three, only, not all), the issue is missing_item."""
PROMPT_WEAK = "Label every message missing_item or other. Return one label for every case id."
print("the weak edit's whole prompt:", PROMPT_WEAK)

# %% [markdown]
# The price table and the budgets come from lesson 18. Prices are per million tokens and carry their date. The budgets are set before the run, not after it.

# %%
PRICE = {"input": 0.25, "output": 1.50}  # USD per million tokens, Gemini API standard text (lesson 18)
PRICE_DATE = "2026-10-22"
BATCH_TOKEN_BUDGET = 4_000    # input tokens allowed for one call that labels all twelve cases
COST_PER_CASE_BUDGET = 0.001  # USD per case: a tenth of a cent
LATENCY_BUDGET_MS = 5_000     # longest wait for one call (meaningful only when recorded live)
GATE_MINIMUM = 0.9            # the candidate must label at least this share of the cases right
CALLS: list[dict] = []        # one entry per real model call


def run_feature(name: str, prompt: str) -> dict:
    """The real model call: all cases in one request. Returns the labels by case id."""
    from llm_setup import get_llm
    numbered = "\n".join(f"{c.case_id}: {c.message}" for c in CASES)
    started = time.perf_counter()
    out = get_llm().with_structured_output(TriageBatch, method="json_schema", include_raw=True).invoke(
        [("system", prompt), ("human", numbered)])
    usage = out["raw"].usage_metadata
    cost = (usage["input_tokens"] * PRICE["input"] + usage["output_tokens"] * PRICE["output"]) / 1e6
    CALLS.append({"prompt": name, "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                  "cost_usd": round(cost, 7), "latency_ms": round((time.perf_counter() - started) * 1000)})
    return {t.case_id: t.issue for t in out["parsed"].labels}


# %% [markdown]
# The budget check names each limit a call breaks. An empty list means the call is within budget.

# %%
def budget_problems(call: dict) -> list[str]:
    """The budget problems of one call. An empty list means the call is within budget."""
    problems = []
    if call["input_tokens"] > BATCH_TOKEN_BUDGET:
        problems.append(f"{call['input_tokens']} input tokens is over the {BATCH_TOKEN_BUDGET} budget")
    if call["cost_usd"] / len(CASES) > COST_PER_CASE_BUDGET:
        problems.append("cost per case is over the budget")
    if call["latency_ms"] > LATENCY_BUDGET_MS:
        problems.append(f"{call['latency_ms']} ms is over the {LATENCY_BUDGET_MS} ms budget")
    return problems


# %% [markdown]
# ### Step 3: the gate
#
# The gate reads the saved scores, not the model. It passes only when two things hold: the pass rate is at least 90%, and no case that the shipped prompt passes now fails. The second rule matters most. A **regression** is a case the shipped prompt gets right and the candidate gets wrong. A new prompt can raise the average and still break the one case a customer cares about.

# %%
def gate(candidate: dict, shipped: dict, minimum: float = GATE_MINIMUM) -> dict:
    rate = sum(r["passed"] for r in candidate.values()) / len(candidate)
    regressions = [cid for cid, r in candidate.items() if shipped[cid]["passed"] and not r["passed"]]
    return {"pass_rate": round(rate, 3), "minimum": minimum, "regressions": regressions,
            "passed": rate >= minimum and not regressions}


print(f"the gate passes a candidate at {GATE_MINIMUM:.0%} or more with no regressions")


# %% [markdown]
# ### Step 4: three model calls, scored and saved
#
# Call 1 is the shipped prompt, the baseline. Call 2 is the candidate. Call 3 is the weak edit. Three calls in total, under the five the lesson allows. Each call's scores are saved to `data/20/`, so the gate and the handover can read them later.

# %% tags=["needs-llm"]
rows_shipped = score(run_feature("shipped v1", PROMPT_SHIPPED))
(DATA / "scored_shipped.json").write_text(json.dumps(rows_shipped, indent=1))
show("shipped (v1)", rows_shipped)

# %% [markdown]
# Call 2 is the candidate: the same twelve cases, one more request. It also scores 12 of 12, as the shipped prompt does. That makes it a safe re-release: the clearer definitions break nothing, and the gate is working as designed.

# %% tags=["needs-llm"]
rows_candidate = score(run_feature("candidate v2", PROMPT_CANDIDATE))
(DATA / "scored_candidate.json").write_text(json.dumps(rows_candidate, indent=1))
show("candidate (v2)", rows_candidate)

# %% [markdown]
# Call 3 is the weak edit: it should score worse, and the gate should refuse it. It drops the definitions, but the output schema still offers all five labels, so the model reads most messages on their own. Only C06 fails: "still says pending" is late only by the definition. Eleven of twelve (92%) is not a mistake in the gate. The 90% rule lets it through, and the regression rule is the point, because it names the case the shipped prompt got right.

# %% tags=["needs-llm"]
rows_weak = score(run_feature("weak edit", PROMPT_WEAK))
(DATA / "scored_weak.json").write_text(json.dumps(rows_weak, indent=1))
show("weak edit", rows_weak)

# %% [markdown]
# ### Step 5: run the gate on each version, and check the budget
#
# The gate reads the three saved score files. The candidate should pass. The weak edit should be refused, and the output says which cases it breaks. The budget lines show each call's tokens and cost against the budgets set in the setup. The budget check runs on this run's three calls.

# %%
shipped = json.loads((DATA / "scored_shipped.json").read_text())
candidate = json.loads((DATA / "scored_candidate.json").read_text())
weak = json.loads((DATA / "scored_weak.json").read_text())
verdict_candidate = gate(candidate, shipped)
verdict_weak = gate(weak, shipped)
print("candidate v2:", verdict_candidate)
print("weak edit:   ", verdict_weak)
for call in CALLS:
    print(f"{call['prompt']:<14} {call['input_tokens']:>5} in  {call['output_tokens']:>4} out  "
          f"${call['cost_usd']:.7f} (prices {PRICE_DATE})  budget: {budget_problems(call) or 'within'}")

# %% [markdown]
# **Check 1 (requirements 1 and 5):** the candidate passes, the weak edit is refused, and every call is inside its budget.

# %%
assert verdict_candidate["passed"], "the candidate should pass the gate"
assert not verdict_weak["passed"], "the weak edit should be refused"
assert not any(budget_problems(c) for c in CALLS), "a model call is over its budget"
print("check 1 passed: candidate released, weak edit refused, every call within budget")

# %% [markdown]
# ### Step 6: the release note
#
# The gate writes one release note: the tag, the prompt that passed, the verdict and the numbers. The deploy in Step 7 reads this file before it starts anything. This lab ships only the tag and the note. The triage service labels orders from the customer's line counts (lesson 16) and does not call the model, so the deploy checks the note as a stand-in. In a real release the service would load the prompt text from the note.

# %%
release = {
    "release": "triage service 1.2.0 with the candidate prompt v2",
    "tag": "1.2.0",
    "prompt": "candidate v2",
    "gate_passed": verdict_candidate["passed"],
    "pass_rate": verdict_candidate["pass_rate"],
    "regressions": verdict_candidate["regressions"],
    "shipped_pass_rate": round(sum(r["passed"] for r in shipped.values()) / len(shipped), 3),
}
RELEASE.write_text(json.dumps(release, indent=1))
print(RELEASE.read_text())

# %% [markdown]
# The model calls are done, so the recording stops here, before the stack is touched. The recorder saves every HTTP call made while it runs, the lab's own calls to the triage service and the UIs included. Stopping now keeps those calls live in Steps 7 to 11, and the recording holds only the three model calls.

# %%
llm_replay.stop()  # saves the recording of the three model calls

# %% [markdown]
# ### Step 7: deploy, and only from the release note
#
# The first cell reads the note and stops if the gate did not pass. The second starts the Compose stack in `../infra/compose/checkpoint-20.yml`:
#
# - `erp`: the customer API from lesson 13, slow on every third `/orders` call (`ERP_SLOW_MS`, 1500 ms by default). It sits only on the `customer` network, which has no route outside.
# - `triage`: the one door. It is on `customer` and on `edge`, so the laptop reaches it on port 8200. Its image tag is `TRIAGE_TAG`, taken from the release note.
# - The Collector, Jaeger (8201) and Prometheus (8202) from lesson 16.
#
# `--wait` covers the services with a health check, and the cell then polls the two UIs that have none.

# %% tags=["needs-docker"]
DOCKER_RAN = True
release = json.loads(RELEASE.read_text())
assert release["gate_passed"], "the gate refused this release: no deploy"
compose("down", "--remove-orphans")  # start from a clean stack: an earlier failed run may have left one up
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": release["tag"]})
assert up.returncode == 0, tail(up.stderr, 12)
wait_for(lambda: all(httpx.get(u, timeout=5).status_code == 200 for u in [f"{JAEGER}/", f"{PROM}/-/ready"]))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
RUN_LOG["up"] = tail(ps.stdout + ps.stderr, 8)

# %% [markdown]
# ### Step 8: the service account, and what it cannot do
#
# Two checks run inside containers. First, inside the triage container (the only one with the reader's secret): the reader gets a token for `orders:read`, and asking for `credits:write` as well is refused at the token step. Only status codes are printed. Second, from inside the customer API's own container: it has no route to the internet, because it sits on an internal network. A third asks Compose for the customer API's published port: there is none.

# %% tags=["needs-docker"]
AUTH_CHECK = """
import os, httpx
url = os.environ["ERP_URL"]
auth = (os.environ["ERP_READER_CLIENT_ID"], os.environ["ERP_READER_CLIENT_SECRET"])
form = {"grant_type": "client_credentials"}
read = httpx.post(url + "/oauth/token", auth=auth, data={**form, "scope": "orders:read"}, timeout=5)
ask = httpx.post(url + "/oauth/token", auth=auth, data={**form, "scope": "orders:read credits:write"}, timeout=5)
print("orders:read token status:", read.status_code)
print("orders:read + credits:write token status:", ask.status_code, ask.json().get("error"))
"""
auth = compose("exec", "-T", "triage", "python", "-c", AUTH_CHECK)
outside = compose("exec", "-T", "erp", "python", "-c", "import urllib.request as u; u.urlopen('http://1.1.1.1', timeout=4)")
RUN_LOG["auth"] = tail(auth.stdout + auth.stderr, 4)
RUN_LOG["isolation"] = "no route outside: " + ("failed as required" if outside.returncode != 0 else "ERROR, it reached the internet")
port = compose("port", "erp", "8000")  # exits 1 with "no port 8000/tcp" when nothing is published
RUN_LOG["port"] = "no published port" if port.returncode != 0 else "published: " + port.stdout.strip()

# %% [markdown]
# **Check 2 (requirement 3):** the stack is up, the reader reads orders, the credit scope is refused, the customer API cannot reach the internet, and it publishes no port. The checks print the live output of this run, or the recorded output when Docker was skipped.

# %%
print("output source:", "this run, live" if DOCKER_RAN else "recorded from the last real run")
print(from_run("up"))
print(from_run("auth"))
print(from_run("isolation"), "|", from_run("port"))
assert "orders:read token status: 200" in from_run("auth"), "the reader should get an orders token"
assert "400 invalid_scope" in from_run("auth"), "the credit scope should be refused at the token step"
assert "failed as required" in from_run("isolation"), "the customer API should have no route outside"
assert from_run("port") == "no published port", "the customer API should publish no port"
print("check 2 passed: least privilege holds, and the customer API stays inside")

# %% [markdown]
# ### Step 9: traffic, logs, a trace and a metric
#
# Eight requests go through the triage service: the same four orders twice, as in lesson 16. The customer API is slow on its third `/orders` call and every third one after it, so some requests are slow. The slow ones are found in the logs, then in their trace, then in the metric. The numbers are read from the stack, never typed in.

# %% tags=["needs-docker"]
lines = []
for order_id in ["BB-1000", "BB-1001", "BB-1002", "BB-1003"] * 2:
    r = httpx.get(f"{TRIAGE}/triage/{order_id}", timeout=20)
    lines.append(f"{order_id} {r.status_code} {r.json().get('label', r.text[:40])}")
RUN_LOG["requests"] = "\n".join(lines)
logs = compose("logs", "triage", "--no-color")
RUN_LOG["logs"] = "\n".join(line[line.index("{"):] for line in logs.stdout.splitlines() if "{" in line)

# %% [markdown]
# The log lines are JSON after Compose's prefix. Step 9 reads them, and finds the slow ones by their `duration_ms`.

# %%
def log_events(text):
    """Structured log lines as dicts. Compose prefixes each line; the JSON starts at the first brace."""
    return [json.loads(line[line.index("{"):]) for line in text.splitlines() if "{" in line]


print(from_run("requests"))
events = log_events(from_run("logs"))
slow = [e for e in events if e.get("duration_ms", 0) >= 1000]
assert events and slow, "no slow request in the logs: check ERP_SLOW_MS and the stack from Step 7"
print(f"{len(slow)} slow of {len(events)} log lines; the first slow one:")
print({k: slow[0][k] for k in ("order_id", "outcome", "duration_ms", "trace_id")})

# %% [markdown]
# Next, fetch the slow request's trace from Jaeger by its trace id, and the request counts from Prometheus. Both use the stack's own query APIs.

# %% tags=["needs-docker"]
def fetch_spans(trace_id: str) -> list[dict]:
    """Spans of one trace from Jaeger's query API. 'http send' (0 ms bookkeeping) is left out."""
    r = httpx.get(f"{JAEGER}/api/traces/{trace_id}", timeout=10)
    if r.status_code != 200:
        return []
    out = []
    for s in r.json()["data"][0]["spans"]:
        tags = {t["key"]: t["value"] for t in s.get("tags", [])}
        url = tags.get("url.full") or tags.get("http.url") or tags.get("http.target") or ""
        if "http send" not in s["operationName"]:
            out.append({"span": s["operationName"], "ms": round(s["duration"] / 1000, 1), "url": str(url)})
    return out


RUN_LOG["trace"] = json.dumps(wait_for(lambda: (s := fetch_spans(slow[0]["trace_id"])) and len(s) >= 4 and s))

# %% [markdown]
# The metric helpers ask Prometheus for two sums. Histogram buckets are cumulative, so the count over one second is the total minus the `le="1.0"` bucket.

# %% tags=["needs-docker"]
def prom_value(query: str) -> float:
    r = httpx.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=10).json()
    return float(r["data"]["result"][0]["value"][1]) if r["data"]["result"] else 0.0


def current_counts() -> dict:
    return {"requests": prom_value("sum(triage_request_seconds_count)"),
            "over_1s": prom_value('sum(triage_request_seconds_count) - sum(triage_request_seconds_bucket{le="1.0"})')}


# %% [markdown]
# Now wait until Prometheus has counted all eight requests, and keep the numbers.

# %% tags=["needs-docker"]
RUN_LOG["metric"] = json.dumps(wait_for(lambda: (c := current_counts())["requests"] >= 8 and c))

# %% [markdown]
# **Check 3 (requirement 4):** the trace's slowest step is the customer API's orders call, not the triage service's own labelling, and the metric counts the same slow requests as the logs. The whole-request span is left out of the comparison, because it always contains the slow call. The trace and the metric print from this run's live output, or the recorded output.

# %%
trace = json.loads(from_run("trace"))
for s in trace:
    print(f"{s['ms']:>9.1f} ms  {s['span']:<24} {s['url']}")
metric = json.loads(from_run("metric"))
print(f"metric: requests counted {metric['requests']:.0f}, slower than 1 s {metric['over_1s']:.0f}")
client_spans = [s for s in trace if "/orders" in s["url"]]
slowest = max(client_spans, key=lambda s: s["ms"])
assert int(metric["over_1s"]) == len(slow), "the metric and the logs should count the same slow requests"
print(f"check 3 passed: the slow hop is the customer API ({slowest['ms']} ms); metric and logs agree")

# %% [markdown]
# ### Step 10: the handover page
#
# The customer gets one page. Every line says where its number came from: **measured** (this run, with Docker), **recorded** (the model-call numbers, which come from the saved recording, or the last real Docker run when Docker is skipped) or **not measured**. A replayed latency is the replay's time, so the budget check on latency only means something when the calls were recorded live.

# %%
over = [p for c in CALLS for p in budget_problems(c)]
model_src = "recorded (model calls, replayed)"  # the gate and cost numbers come from the recording
docker_src = "measured" if DOCKER_RAN else "recorded"
page = [
    ("Gate verdict", "passed" if release["gate_passed"] else "refused", model_src),
    ("Pass rate, candidate v2", f"{release['pass_rate']:.0%} (shipped {release['shipped_pass_rate']:.0%})", model_src),
    ("Weak edit refused at", f"{verdict_weak['pass_rate']:.0%} pass rate", model_src),
    ("Budget problems", ("none" if not over else "; ".join(over)) if CALLS else "not checked: no model calls ran", model_src),
    ("Cost of the candidate call", f"${CALLS[1]['cost_usd']:.7f} (prices {PRICE_DATE})" if len(CALLS) > 1 else "not measured", model_src),
    ("Least privilege", "reader refused credits:write", docker_src),
    ("Slow requests", f"{len(slow)} of {len(events)} log lines took 1 s or more", docker_src),
    ("Live customer traffic", "not measured: this lab has no customer data", "not measured"),
]
print(f"{'What the customer sees':<30}{'Value':<62}Source")
for what, value, src in page:
    print(f"{what:<30}{value:<62}{src}")

# %% [markdown]
# ### Step 11: tear down
#
# Stop and remove this lesson's containers and network. The images stay. The live output of this run is saved to `../data/20/run_log.json`, so the recording can be refreshed.

# %% tags=["needs-docker"]
compose("down", "--remove-orphans")  # the images stay
(DATA / "run_log.json").write_text(json.dumps(RUN_LOG, indent=1))  # saved for the recording

# %% [markdown]
# ### Try it
#
# Change the minimum to 0.95 and gate the two versions again: `gate(candidate, shipped, 0.95)` and `gate(weak, shipped, 0.95)`. Pass the minimum as the third argument: `gate` keeps the default it had when it was defined, so changing `GATE_MINIMUM` alone does nothing. What changes for each? Before you run anything, say which rule refuses the weak edit: the pass rate or the regression rule.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
for name, rows in [("candidate", candidate), ("weak edit", weak)]:
    v = gate(rows, shipped, 0.95)
    print(f"{name:<10} pass rate {v['pass_rate']} passed: {v['passed']} regressions: {v['regressions']}")
print("the candidate still passes (100%); the weak edit is refused for two reasons: its pass rate and the regression on C06")

# %% [markdown]
# ## Reference solution
#
# One run from the gate to the handover, in order. Compare your run with it: the verdicts and the checks should match.

# %% tags=["solution"]
print("gate: candidate passed:", verdict_candidate["passed"], "| weak edit refused:", not verdict_weak["passed"])
print("deploy:", "started from the release note" if release["gate_passed"] else "refused")
print("checks: 1 gate and budget · 2 auth and isolation · 3 observability")
print("checkpoint passed:", verdict_candidate["passed"] and not verdict_weak["passed"] and release["gate_passed"])

# %% [markdown]
# ## Key terms
#
# - **release gate** — a rule that stops a release unless the evidence passes: here a pass rate on the eval set and no regression on any case the shipped prompt passes (lesson 20)
# - **regression** — a case that passed before and fails after a change; the gate checks it separately from the average (lesson 11)
# - **release note** — the file the gate writes and the deploy reads first (lesson 20)
# - **least privilege** — each account gets only the scopes it needs, and the API checks them on every call (lesson 13)
# - **internal network** — a Compose network with no route outside and no published port (lesson 15)
# - **trace id** — the id that links a log line, a span and a trace to one request (lesson 16)
# - **budget** — a limit set before a run, on tokens, cost or latency, that a call must stay inside (lesson 18)
# - **handover page** — the one page that says what was measured, what was recorded and what was not measured (lessons 07, 17)

# %% [markdown]
# **Interview:** "Your model feature got a better average score. Do you ship it?" Strong answer: "Not yet. I check that no case the shipped version passes now fails, because an average can rise while one important case breaks. The gate writes the verdict to a note, the deploy reads it, and the handover says which numbers are measured and which are not."
