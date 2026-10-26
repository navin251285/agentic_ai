# %% [markdown]
# # 32 · Final checkpoint: the customer delivery drill
#
# Level L5 · Part 3 · core · ~30 min · builds on 31
#
# This is the course checkpoint. You rehearse the whole delivery path from lesson 31 for a **fresh customer** and present the result. The lab has two parts that do not meet. The gate makes **2 model calls** (one candidate run, one red-team run; recorded once and replayed later; the lesson budget is 5 calls). The Compose stack on ports 8320 to 8322 runs lesson 16's rule-based triage service, which makes no model call and does not run the candidate prompt. The cells tagged `needs-docker` start and stop the stack. Without Docker, the saved output of the last real run is shown and labelled as recorded. The time box starts at Step 0, when you read the brief and start the stopwatch, and stops at the end of Step 10, the talk. Step 11 (tear-down) is outside it.

# %% [markdown]
# ## Goal
#
# By the end you can rehearse one delivery for a new customer, from scope to handover, in the order the course teaches, and time it yourself. You can show which settings were set for that customer, which shared code did not change, which of the handover rows are measured, recorded or not measured, and what the gate did not prove.

# %% [markdown]
# ## Why it matters
#
# Lesson 31 delivered one customer, and every step was prepared in advance. A second customer shows whether the steps hold up when someone new runs them.
#
# - **Without a drill:** the second delivery copies the first one's folder, edits the code for the new customer and skips the gate because the deadline is close. Nobody can say which code is in production for which customer.
# - **With a drill:** the same steps run in the same order. A refused gate stops the release note from passing, the handover names the source of each number, and the gaps show up while there is still time to fix them.
# - **What this drill does not prove:** that the shipped service answers the customer's questions. Read "What this lab does not prove" before Step 7.
# - **When you don't need it:** a one-off internal tool with one user and no deadline. A customer-facing delivery always gets a rehearsal.

# %% [markdown]
# ## The idea
#
# A **delivery drill** repeats one delivery under the same rules and a clock. The brief names the customer, the time box and what must be handed over. The team does the steps in order: scope, config, security answers, labelled cases, gate, release note, deploy from the note, verify, handover, a short talk and tear-down. The drill passes only when every counted requirement has evidence from this run.
#
# Think of a fire drill in a building you have never used. The drill does not test the building. It tests whether the people, the exits and the signs work for a new group in a set time. The lab's fresh customer is the new group.

# %% [markdown]
# ## Picture
#
# Twelve steps, numbered 0 to 11, and one clock. The gate can stop the drill, and the drill then ends in a gap, not in a deploy.

# %% [markdown]
# ```mermaid
# flowchart LR
#     B[0 Brief and clock] --> S[1 Scope]
#     S --> C[2 Config only]
#     C --> SE[3 Security answers]
#     SE --> L[4 Labelled cases]
#     L --> G{5 Gate: candidate and red-team}
#     G -- candidate passed --> N[6 Release note]
#     G -- refused --> X[Gap: fix the prompt, no deploy]
#     N --> D[7 Deploy from the note]
#     D --> V[8 Verify]
#     V --> H[9 Handover page]
#     H --> P[10 Talk in 3 minutes]
#     P --> TD[11 Tear down]
# ```

# %% [markdown]
# ## Requirements
#
# Step 9 checks R1 to R9 and R11. R10 is a pointer; R12 is reported.
#
# | # | Requirement | Evidence | Lesson |
# | --- | --- | --- | --- |
# | R1 | Scope names what is out | list not empty | 31 |
# | R2 | Rules come from settings | six `DRILL_*` set | 25 |
# | R3 | Security answers checked | all True | 27 |
# | R4 | Candidate passes the gate | gate verdict | 20 |
# | R5 | Deploy after the gate (plumbing only) | step order, tag | 20, 31 |
# | R6 | No published customer port | `compose port` | 15 |
# | R7 | Health, traces, metrics | `/health`, Jaeger | 16 |
# | R8 | Each row has a source | source label | 22 |
# | R9 | Cost per case in budget | cost vs budget | 18 |
# | R10 | Runbook exists | pointer only | 17, 28 |
# | R11 | Shared code unchanged | fingerprint | 25 |
# | R12 | Clock reported | clock row | 31 |

# %% [markdown]
# ## Build it

# The helpers are lesson 31's, unchanged. The candidate prompt is lesson 31's with one counting rule reworded (Step 5). The new code is in Steps 4-6 and 9.

# %% [markdown]
# ### Setup
#
# The first cell starts the recording of the two model calls. The next loads the settings from `../.env`: names and yes/no only, no value is printed.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and tut_env.py
import llm_replay
llm_replay.start("32_final-delivery-drill")  # records the two model calls below once

# %% [markdown]
# Next, the imports and the clock. The clock starts here and every step marks its time on it.
#
# Course helpers, not libraries:
#
# - `llm_replay` and `llm_setup`: the model recording and model access.
# - `tut_env`: reads `.env`.
# - `CORE_FILE`: the shared triage code from lesson 16.
# - `apps/32/`: this lesson's stack.
# - `data/recorded/32.json`: the saved run.

# %%
import csv, hashlib, json, math, os, shutil, subprocess, time
from collections import Counter
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from tut_env import env, is_set, load

load()
DRILL_START = time.monotonic()  # the drill clock starts here
CLOCK: list[tuple[str, float]] = []  # (step, minutes into the drill), filled by mark()
DOCKER_RAN = False  # becomes True once the stack has started
RUN_LOG = {}        # the real output of each Docker step, saved for the recording
CALLS: list[dict] = []  # one entry per real model call
print("clock started: 0.0 minutes into the drill")

# %% [markdown]
# The constants: the stack's names and ports, the shared code, the saved run and the prices. Nothing here calls a service.

# %%
DRILL_MINUTES = 30  # the time box the brief gives the team (the clock reports it; it is not enforced)
STACK = "tut-forward-deployed-engineering-15h-32"  # one Compose project for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../apps/32/delivery-32.yml", "--env-file", "../.env"]
TRIAGE, JAEGER, PROM = "http://localhost:8320", "http://localhost:8321", "http://localhost:8322"
CORE_FILE = Path("../apps/16/triage_service.py")  # the shared service code the release ships
DATA = Path("../data/32")
DATA.mkdir(parents=True, exist_ok=True)
REC = json.loads(Path("../data/recorded/32.json").read_text())  # the output of the last real Docker run
RELEASE_TAG = "1.2.0"  # the code still reports 1.2.0: a new customer changes config, not code
GATE_MINIMUM = 0.9     # the candidate must label at least this share of the cases right
EXPECTED = {"BB-1000": "missing items", "BB-1001": "complete", "BB-1002": "missing items", "BB-1003": "missing items"}  # the lab's stand-in customer API: lesson 13's mock, with the old customer's orders, not Corner Shop Co data
PRICE = {"input": 0.25, "output": 1.50}  # USD per million tokens, Gemini API standard text (lesson 18)
PRICE_DATE = "2026-10-22"
print("constants set:", len(EXPECTED), "stand-in orders;", "gate minimum", f"{GATE_MINIMUM:.0%}", ";", "prices dated", PRICE_DATE)

# %% [markdown]
# The clock helper marks the start of each step. Every step cell calls it once.
#
# The status line after it reports three things, as yes or no only: Docker is on the machine, a model key is set, and the customer API secrets (`ERP_SIGNING_KEY`, `ERP_READER_CLIENT_SECRET`) are set. Those secrets come from the setup of lessons 13 and 31.

# %%
def mark(step: str) -> None:
    """Record how many minutes into the drill this step starts."""
    CLOCK.append((step, round((time.monotonic() - DRILL_START) / 60, 2)))


print("docker:", bool(shutil.which("docker")),
      "| model key:", bool(is_set("GOOGLE_CLOUD_API_KEY") or is_set("GOOGLE_CLOUD_PROJECT")),
      "| customer API secrets:", all(is_set(n) for n in ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET"]))

# %% [markdown]
# Next, the helpers. They run Compose for this lesson's project, poll until something answers, and pick the live or the recorded output.

# %%
def compose(*args, extra=None):
    """Run docker compose for this lesson's project."""
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
# ### Step 0: the brief
#
# The brief is what the customer asked for, written before the drill starts. Read it once, then start the clock: the time box starts here. The customer is invented: a second grocery group with its own city, stores and regions.

# %%
mark("0 brief")
BRIEF = {
    "customer": "Corner Shop Co (invented grocery group, a second customer)",
    "ask": "the same delivery triage for this customer, live on a go-live date",
    "time box": f"{DRILL_MINUTES} minutes from scope to handover and talk",
    "rule": "shared code does not change; only config and the labelled cases change",
    "hand over": "scope, config, gate result, release note, deploy from the note, verify, handover, talk",
}
for key, value in BRIEF.items():
    print(f"{key:<10}{value}")

# %% [markdown]
# ### Step 1: the scope sheet
#
# The scope sheet is the same shape as lesson 31's. A number nobody has is written as **not measured**.

# %%
mark("1 scope")
SCOPE = {
    "problem": "support agents cannot sort delivery messages into missing, wrong, late or damaged items fast enough",
    "in scope": "label one message with one issue (five labels); show the label to the agent",
    "out of scope": "refunds, credits, courier dispatch, any write to the customer's order system",
    "success measure": "pass rate on the 12 labelled cases, at least 90%, and no failed release",
    "baseline": "not measured: this customer has not timed its agents yet",
    "owner": "the customer's support lead (named in the contract, not here)",
}
(DATA / "scope.json").write_text(json.dumps(SCOPE, indent=1))
for key, value in SCOPE.items():
    print(f"{key:<16}{value}")

# %% [markdown]
# ### Step 2: config, not code
#
# The customer's rules are read from settings here, in the notebook. The six `DRILL_*` settings go in `../.env` (names and lab defaults are in `.env.example`). If one is missing, the notebook uses its lab default and R2 shows GAP. The Compose stack does not read these `DRILL_*` settings: the triage service is lesson 16's code, unchanged, so the customer's config and labelled cases are used by this notebook, not by the container. The fingerprint of the shared service file is taken now and again at the handover. It is a tripwire: it shows the file did not change during this run. It does not prove the code was never changed before.

# %%
mark("2 config")


def fingerprint(path: Path) -> str:
    """A short SHA-256 of the file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


CORE_BEFORE = fingerprint(CORE_FILE)
CONTROL = DATA / "control_copy.py"  # a control: one changed byte must change the fingerprint, or the check cannot fail
CONTROL.write_bytes(CORE_FILE.read_bytes() + b" ")
CONTROL_OK = fingerprint(CONTROL) != CORE_BEFORE
CONTROL.unlink()
print("fingerprint control (one byte changed gives a different value):", CONTROL_OK)
CUSTOMER_KEYS = ["DRILL_STORAGE_REGION", "DRILL_MODEL_REGION", "DRILL_ALLOWED_REGIONS",
                 "DRILL_RETENTION_DAYS", "DRILL_CONTRACT_MAX_RETENTION_DAYS", "DRILL_COST_PER_CASE_BUDGET"]
CONFIG_FROM_ENV = all(is_set(n) for n in CUSTOMER_KEYS)  # True only when all six settings are in .env
CUSTOMER = {
    "storage region": env("DRILL_STORAGE_REGION", "europe-west1"),
    "model region": env("DRILL_MODEL_REGION", "europe-west1"),
    "allowed regions": env("DRILL_ALLOWED_REGIONS", "europe-west1,europe-west4").split(","),
    "retention days": int(env("DRILL_RETENTION_DAYS", "14")),
    "contract max retention days": int(env("DRILL_CONTRACT_MAX_RETENTION_DAYS", "30")),
    "cost per case budget, USD": float(env("DRILL_COST_PER_CASE_BUDGET", "0.001")),
}
print("shared service file, fingerprint:", CORE_BEFORE)
for key, value in CUSTOMER.items():
    print(f"  {key:<30}{value}")
print("all six settings set in .env:", CONFIG_FROM_ENV)

# %% [markdown]
# ### Step 3: the security answers, with evidence
#
# The same questions as lesson 31, asked about this customer's config. Each answer is a check that can fail. The last line is filled in at Step 8, after the deploy, from a check on the laptop.

# %%
mark("3 security")
SECURITY = {
    "data stored in an allowed region": CUSTOMER["storage region"] in CUSTOMER["allowed regions"],
    "model prompts processed in an allowed region": CUSTOMER["model region"] in CUSTOMER["allowed regions"],
    "retention within the contract maximum": CUSTOMER["retention days"] <= CUSTOMER["contract max retention days"],
    "reader secret comes from settings, not from the image": is_set("ERP_READER_CLIENT_SECRET"),
    "customer API has no published port": "checked after the deploy (Step 8)",
}
for question, answer in SECURITY.items():
    print(f"{answer!s:<6} {question}")

# %% [markdown]
# ### Step 4: the labelled cases
#
# The customer's golden set does not exist yet, so the lab makes a **tiny generated example**: twelve invented messages for this drill, labelled by the drill team with the same five labels as lesson 31. No real customer data is used. The cases are checked with a schema before any model sees them.
#
# Twelve cases we wrote ourselves is a rehearsal, not evidence; a real gate needs the customer's own cases. A pass rate on twelve cases is also a wide interval: one wrong label moves it by about 8 points.

# %%
mark("4 cases")
Issue = Literal["missing_item", "wrong_item", "late", "damaged", "other"]


class EvalCase(BaseModel):
    case_id: str
    order_id: str = Field(pattern=r"^CS-\d{4}$")
    message: str = Field(min_length=10)
    want: Issue


print("schema ready: a case needs an id, an order id like CS-2101, a message and one of five labels")

# %% [markdown]
# The twelve cases, each checked against the schema when it is built, then written to a CSV file for the record.

# %%
FRESH = [  # case id, order id, message, the drill team's label
    ("F01", "CS-2101", "I ordered two cartons of oat milk and only one came in the bag.", "missing_item"),
    ("F02", "CS-2102", "The bananas arrived but the strawberries I paid for are not in the bag.", "missing_item"),
    ("F03", "CS-2103", "I asked for full-fat milk and got skimmed milk instead.", "wrong_item"),
    ("F04", "CS-2104", "My slot was 6 to 7pm, it is now 9pm and the order still shows pending.", "late"),
    ("F05", "CS-2105", "Three eggs were cracked when I unpacked the box.", "damaged"),
    ("F06", "CS-2106", "The courier left the bags at the wrong flat, not at my door.", "other"),
    ("F07", "CS-2107", "Only three of the five apples came, the rest are missing.", "missing_item"),
    ("F08", "CS-2108", "The yogurt tubs were split open and leaking over the other shopping.", "damaged"),
    ("F09", "CS-2109", "I got a bag of brown rice but I ordered basmati rice.", "wrong_item"),
    ("F10", "CS-2110", "The order was due this morning and it came after noon.", "late"),
    ("F11", "CS-2111", "Two of the four bottles of juice were in the bag, not all four.", "missing_item"),
    ("F12", "CS-2112", "The driver would not wait at the door while I got my card.", "other"),
]
CASES = [EvalCase(case_id=c, order_id=o, message=m, want=w) for c, o, m, w in FRESH]
with open(DATA / "fresh_cases.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["case_id", "order_id", "message", "want"])
    writer.writerows((c.case_id, c.order_id, c.message, c.want) for c in CASES)
print(f"{len(CASES)} labelled cases; the drill team's labels:", dict(Counter(c.want for c in CASES)))

# %% [markdown]
# ### Step 5: the gate, two model calls
#
# The candidate is the lesson 20 candidate v2 prompt, as lesson 31 used it, with one counting rule reworded (below). The **red-team candidate** is the same prompt with one wrong rule on purpose: the partial-item cases become `late`. A gate that passes it is broken. The model labels all twelve cases in one structured call, so each candidate costs one call. The scorer is plain code: a missing answer is a fail. This is a standalone model call on the prompt. Nothing below deploys this prompt; Step 7 deploys lesson 16's code.

# %% [markdown]
# The output schema, the two prompts and the one model call. The red-team prompt is built from the candidate by changing one line, and the code checks that the change happened.

# %%
mark("5 gate")


class Triage(BaseModel):
    case_id: str = Field(description="the case id exactly as given, such as F01")
    issue: Issue


class TriageBatch(BaseModel):
    labels: list[Triage] = Field(description="one entry for every case id given")


PROMPT_CANDIDATE = ("Label each grocery delivery support message with one issue: missing_item, wrong_item, "
                    "late, damaged or other. Return one label for every case id.\n"
                    "Definitions:\n"
                    "- missing_item: the customer did not get all of an item they paid for, even when they say only some of it arrived.\n"
                    "- late: the delivery came after the slot, or still shows as pending.\n"
                    "- damaged: broken, bruised, crushed, split or leaking.\n"
                    "- wrong_item: the customer got a different item from the one ordered.\n"
                    "- other: none of the above, such as a courier problem.\n"
                    "- Rule: if the customer says only part of an item they paid for arrived (two of four, only three, not all), the issue is missing_item.")
PROMPT_RED_TEAM = PROMPT_CANDIDATE.replace("(two of four, only three, not all), the issue is missing_item.", "(two of four, only three, not all), the issue is late.")
assert PROMPT_RED_TEAM != PROMPT_CANDIDATE, "the red-team change did not apply"
print("candidate rule:    ", PROMPT_CANDIDATE.splitlines()[-1].strip())
print("red-team rule:     ", PROMPT_RED_TEAM.splitlines()[-1].strip())
print("the two prompts differ:", PROMPT_RED_TEAM != PROMPT_CANDIDATE)


# %% [markdown]
# The model call. All cases go in one request, and the cost comes from the usage the model returns, at the prices and date in the table. The scorer compares each label with the drill team's label.

# %%
def run_gate(prompt: str, label: str) -> dict:
    """The real model call: all cases in one request. Returns the labels by case id and records the cost."""
    from llm_setup import get_llm
    numbered = "\n".join(f"{c.case_id}: {c.message}" for c in CASES)
    out = get_llm().with_structured_output(TriageBatch, method="json_schema", include_raw=True).invoke(
        [("system", prompt), ("human", numbered)])
    usage = out["raw"].usage_metadata
    cost = (usage["input_tokens"] * PRICE["input"] + usage["output_tokens"] * PRICE["output"]) / 1e6
    CALLS.append({"label": label, "input_tokens": usage["input_tokens"],
                  "output_tokens": usage["output_tokens"], "cost_usd": round(cost, 7)})
    return {t.case_id: t.issue for t in out["parsed"].labels}


def score(labels: dict) -> tuple[float, dict]:
    """The pass rate, and each case with what was wanted and what was given."""
    rows = {c.case_id: {"want": c.want, "got": labels.get(c.case_id)} for c in CASES}
    return sum(r["want"] == r["got"] for r in rows.values()) / len(rows), rows


print(f"two prompts ready; {len(CASES)} cases go in one call each")

# %% [markdown]
# The first real call: the candidate, with its counting rule reworded to cover only a part of an item the customer paid for. The earlier wording (any named count is `missing_item`) would send F05 ("Three eggs", labelled `damaged`) to `missing_item`, which conflicts with the drill team's label; the new wording does not. The recorded run labelled all twelve cases the way the drill team did. One run on twelve cases is a small check, not a measure of the prompt in production. MODEL_SRC is read before llm_replay.stop() so it can tell replay from live.

# %% tags=["needs-llm"]
labels = run_gate(PROMPT_CANDIDATE, "candidate")
cand_rate, cand_rows = score(labels)
MODEL_SRC = "recorded (model call, replayed)" if llm_replay.mode() == "replay" else "measured (model call, this run)"
print(f"candidate: {cand_rate:.0%} pass ({round(cand_rate * len(CASES))} of {len(CASES)})")
for cid, r in cand_rows.items():
    if r["want"] != r["got"]:
        print(f"  FAIL {cid}: want={r['want']:<12} got={r['got']}")

# %% [markdown]
# The second real call: the red-team candidate, with the partial-item cases sent to `late`. It is refused: it labels 9 of 12 cases right (75%), below the 90% minimum. The three misses are F01, F07 and F11, the partial-item cases, and the wrong rule sends each of them to `late`, as the rule says. The gate in Step 6 refuses it, so the gate can say no.

# %% tags=["needs-llm"]
red_labels = run_gate(PROMPT_RED_TEAM, "red-team")
red_rate, red_rows = score(red_labels)
print(f"red-team candidate: {red_rate:.0%} pass ({round(red_rate * len(CASES))} of {len(CASES)}), wrong on purpose")
for cid, r in red_rows.items():
    if r["want"] != r["got"]:
        print(f"  FAIL {cid}: want={r['want']:<12} got={r['got']}")

# %% [markdown]
# The model calls are the last ones this lesson makes. The recording stops here, so the Docker steps below, which call only local services, are not saved in it.

# %%
llm_replay.stop()  # saves the recording of the two model calls
print("model calls in this notebook:", len(CALLS), "(lesson budget: 5)")

# %% [markdown]
# ### Step 6: the release notes
#
# The gate passes when the pass rate meets the minimum. Each note records the tag, the verdict, the pass rate and the cost of its gate run. The candidate's note is the one the deploy will read. The red-team note is kept to show the refusal.

# %%
mark("6 release note")


NOTE_SEQ = iter(range(1, 10_000))  # each note gets the next number: the highest one is the newest


def make_note(rate: float, call: dict, tag: str) -> dict:
    per_case = call["cost_usd"] / len(CASES)
    return {"release": f"triage service {tag}: candidate prompt scored in the gate; the stack runs lesson 16's code, not this prompt",
            "written_seq": next(NOTE_SEQ), "scored_prompt": call["label"], "tag": tag,
            "pass_rate": round(rate, 3), "gate_minimum": GATE_MINIMUM,
            "gate_passed": rate >= GATE_MINIMUM,
            "cost_per_case_usd": round(per_case, 7),
            "cost_per_case_ok": per_case <= CUSTOMER["cost per case budget, USD"],
            "prices_date": PRICE_DATE}


NOTE = make_note(cand_rate, CALLS[0], RELEASE_TAG)
REFUSED = make_note(red_rate, CALLS[1], RELEASE_TAG)
(DATA / "release_note.json").write_text(json.dumps(NOTE, indent=1))
(DATA / "refused_note.json").write_text(json.dumps(REFUSED, indent=1))
print("release note, candidate:", json.dumps(NOTE, indent=1))
print("red-team note, gate passed:", REFUSED["gate_passed"], f"({REFUSED['pass_rate']:.0%})")

# %% [markdown]
# ### What this lab does not prove
#
# Read this before the deploy. The gate in Steps 4 to 6 scores lesson 31's prompt in a standalone model call, on twelve labelled cases we wrote. The stack deployed in Step 7 runs lesson 16's rule-based triage service: it makes no model call, does not run the candidate prompt, and does not read the `DRILL_*` settings. So the deploy proves the release plumbing (the note, the tag, the stack, the health check, the traces), not that the candidate prompt works in production. Steps 7 and 8 check plumbing only.

# %% [markdown]
# ### Step 7: deploy, and only from the candidate's note
#
# Step 7 starts with two cells that need no Docker. `latest_note()` picks the newest note file. `deploy_from()` is the guard: it reads a note and returns its tag only when the gate passed.

# %%
def latest_note() -> Path:
    """The newest release note file in the data folder: the one written last, by its number."""
    return max(DATA.glob("*_note.json"), key=lambda p: json.loads(p.read_text())["written_seq"])


def deploy_from(note_path: Path) -> str:
    """The guard: return the tag of a note only when its gate passed."""
    note = json.loads(note_path.read_text())
    assert note["gate_passed"], f"{note_path.name}: the gate refused the {note['scored_prompt']} prompt at {note['pass_rate']:.0%}: no deploy"
    return note["tag"]


print("newest note:", latest_note().name)
print("deploy tag from the candidate's note:", deploy_from(DATA / "release_note.json"))

# %% [markdown]
# Common mistake: a deploy that takes the newest note. The newest file is the red-team note, so the guard refuses it. The cell below shows that refusal on purpose.

# %% tags=["raises-exception"]
deploy_from(latest_note())

# %% [markdown]
# The deploy cell reads the tag from the candidate's note through the guard, then starts the stack in `../apps/32/delivery-32.yml`: the customer API on an internal network, the triage service as the one door on port 8320, and the Collector, Jaeger (8321) and Prometheus (8322). It needs Docker. The cell polls the two UIs, which have no health check.

# %% tags=["needs-docker"]
mark("7 deploy")
TAG = deploy_from(DATA / "release_note.json")  # refuses unless the candidate's gate passed
compose("down", "--remove-orphans")  # start from a clean stack
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": TAG})
assert up.returncode == 0, tail(up.stderr, 12)
DOCKER_RAN = True  # set only once the stack is up
wait_for(lambda: all(httpx.get(u, timeout=5).status_code == 200 for u in [f"{JAEGER}/", f"{PROM}/-/ready"]))
ps = compose("ps", "--format", "table {{.Service}}\t{{.Status}}")
RUN_LOG["up"] = tail(ps.stdout + ps.stderr, 8)
RUN_LOG["trail"] = {"steps": [s for s, _ in CLOCK], "deployed_tag": TAG}  # the order the steps ran in
print("compose up, exit code:", up.returncode)

# %% [markdown]
# The line below shows this run's status, or the recorded status when Docker was skipped.

# %%
print("stack status, source:", "this run, live" if DOCKER_RAN else "recorded output from the last real run")
print(from_run("up"))

# %% [markdown]
# ### Step 8: verify the running service
#
# Five checks, each a real answer. The triage service answers its health check, and its labels carry the release version. Four orders from the stand-in customer API get a label, and each must match the order's short lines. The stand-in is lesson 13's mock with the old customer's orders (BB-100x), not Corner Shop Co data, so these checks prove the plumbing, not Corner Shop Co's answers. The customer API has no published port on the laptop. The last security line of Step 3 is filled in here from that check. Jaeger lists the triage service, and the metrics endpoint shows the request-time series.

# %% tags=["needs-docker"]
mark("8 verify")
wait_for(lambda: httpx.get(f"{TRIAGE}/health", timeout=5).status_code == 200)
health = httpx.get(f"{TRIAGE}/health", timeout=5).status_code  # the status of the health check, 200 when the service is up
answers = {}
for order in EXPECTED:
    r = httpx.get(f"{TRIAGE}/triage/{order}", timeout=10)
    answers[order] = r.json() if r.status_code == 200 else {"status": r.status_code}
erp_published = compose("port", "erp", "8000").returncode == 0  # True would mean the customer API is open


def jaeger_has_triage():
    names = httpx.get(f"{JAEGER}/api/v3/services", timeout=10).json().get("services", [])  # Jaeger's v3 query API
    return names if "bb-triage" in names else None


services = wait_for(jaeger_has_triage, timeout=60)  # spans reach Jaeger a few seconds after the requests
metric_lines = [ln for ln in httpx.get(f"{TRIAGE}/metrics", timeout=10).text.splitlines() if ln.startswith("triage_request_seconds")]
RUN_LOG["verify"] = {"health": health, "answers": answers, "erp_published": erp_published,
                     "jaeger_services": services, "metric_series": len(metric_lines)}
print(from_run("verify"))

# %% [markdown]
# Each line below answers one check from Step 8. Read a False as a gap, not as a bug to hide.

# %%
verify = from_run("verify")
versions = {o: a.get("version") for o, a in verify["answers"].items()}
print("health check status:", verify["health"], "(200 means up)")
print("release version seen by the service:", set(versions.values()), "| matches the note:", set(versions.values()) == {RELEASE_TAG})
labels_ok = {o: a.get("label") == EXPECTED[o] for o, a in verify["answers"].items()}
print("labels match the short lines:", all(labels_ok.values()), labels_ok)
print("customer API published to the laptop:", verify["erp_published"], "(must be False)")
print("traces: the triage service is in Jaeger:", "bb-triage" in verify["jaeger_services"])
print("metrics: request-time series found:", verify["metric_series"] > 0)
SECURITY["customer API has no published port"] = not verify["erp_published"]

# %% [markdown]
# ### Step 9: the handover page and the requirement check
#
# The customer gets one page. Every row names its source: **measured** when this run produced it, **recorded** when it comes from the saved run, **not measured** when nobody has the number yet, and **documented, not run here** for a pointer. The clock row is the notebook's own clock: it reports the length of this run and is not a met time box. The time box runs from Step 0 to the end of Step 10 (the talk); the notebook reads its clock here, at Step 9, so this row is not the full box. You time your own run by hand, with a stopwatch, against the 30-minute box. Only the rows named in the check below count toward the pass count: R10 is a pointer and R12 is reported.

# %%
mark("9 handover")
verify = from_run("verify")
trail = from_run("trail")
src = "measured" if DOCKER_RAN else "recorded"
core_after = fingerprint(CORE_FILE)
drill_minutes = round((time.monotonic() - DRILL_START) / 60, 2)
page = [
    ("Gate verdict, candidate", "passed" if NOTE["gate_passed"] else "refused", MODEL_SRC),
    ("Pass rate, candidate", f"{NOTE['pass_rate']:.0%} (minimum {GATE_MINIMUM:.0%}, 12 invented cases)", MODEL_SRC),
    ("Red-team candidate", "refused, as it must be" if not REFUSED["gate_passed"] else "NOT refused: the gate is broken", MODEL_SRC),
    ("Cost per case, gate run", f"${NOTE['cost_per_case_usd']:.7f} (budget ${CUSTOMER['cost per case budget, USD']})",
     f"{MODEL_SRC}; prices from lesson 18, dated {PRICE_DATE}"),
    ("Shared service code changed for this customer", "no" if core_after == CORE_BEFORE else "yes: review", "measured (file fingerprint)"),
    ("Service version", ", ".join(sorted({str(a.get("version")) for a in verify["answers"].values()})), src),
    ("Customer API reachable from laptop", "no" if not verify["erp_published"] else "yes: fix before go-live", src),
    ("Triage traces in Jaeger", "yes" if "bb-triage" in verify["jaeger_services"] else "no", src),
    ("Drill clock, notebook run (not a met time box)", f"{drill_minutes:.1f} min; box is {DRILL_MINUTES} min", "measured (notebook clock only)"),
    ("Baseline for agent time", "not measured", "not measured"),
    ("Live customer traffic", "not measured: this drill has no customer data", "not measured"),
    ("What the gate did not prove", "12 invented cases (a wide interval); no real customer messages; the shipped stack does not run this prompt", "not measured"),
    ("Runbook for failures", "lesson 17 runbook; drill in lesson 28", "documented, not run here"),
]

# %% [markdown]
# The handover page as the customer sees it. The Source column says where each value came from.

# %%
print(f"{'What the customer sees':<46}{'Value':<46}Source")
for what, value, source in page:
    print(f"{what:<46}{value:<46}{source}")
print("Source of Docker rows:", "this run, live" if DOCKER_RAN else "recorded run (this machine ran without Docker)")
handover_saved = (DATA / "handover.json").write_text(json.dumps(page, indent=1))  # assigned: no stray byte count printed
print("handover page saved to ../data/32/handover.json")

# %% [markdown]
# Now tick the requirements. A GAP line names what is still missing. Each check reads evidence from this run, or from the recorded run when Docker was skipped (the R5 and R7 rows come from the recorded run in that case). R10 is a pointer and is not counted. R2 needs all six `DRILL_*` settings in `.env`; without them it shows GAP.

# %%
SOURCES = ("measured", "recorded", "not measured", "documented")
steps = trail["steps"]  # the order the steps ran in, from the clock (this run, or the recording)
deployed_after_gate = (all(s in steps for s in ["5 gate", "6 release note", "7 deploy"])
                       and steps.index("5 gate") < steps.index("6 release note") < steps.index("7 deploy")
                       and trail["deployed_tag"] == NOTE["tag"])
print("step order:", " > ".join(steps))
print("deploy came after the gate and the note, with the note's tag:", deployed_after_gate)

# %% [markdown]
# The checks. Each line is one requirement from the table above, read against the evidence in this run or the recording.

# %%
checks = {
    "R1 out-of-scope named": bool(SCOPE["out of scope"]),
    "R2 customer rules from settings (all six DRILL_* set)": CONFIG_FROM_ENV,
    "R3 security answers checked": all(v is True for v in SECURITY.values()),
    "R4 candidate passed the gate": NOTE["gate_passed"],
    "R5 deploy after the gate (plumbing only), with the note's tag": deployed_after_gate,
    "R6 customer API not published": not verify["erp_published"],
    "R7 health 200, traces, metrics, 4 answers": verify["health"] == 200 and "bb-triage" in verify["jaeger_services"]
                                              and verify["metric_series"] > 0 and len(verify["answers"]) == 4,
    "R8 every handover row has a value and a valid source": all(row[1].strip() and row[2].startswith(SOURCES) for row in page),
    "R9 cost per case within budget": NOTE["cost_per_case_ok"],
    "R11 shared code unchanged (fingerprint control works)": core_after == CORE_BEFORE and CONTROL_OK,
}
print(f"R9 detail: ${NOTE['cost_per_case_usd']:.7f} per case, against a budget of ${CUSTOMER['cost per case budget, USD']} per case")
for name, ok in checks.items():
    print(f"{'ok ' if ok else 'GAP'}  {name}")
print("R10  runbook pointer: documented, not run here (not counted)")
print("R12  notebook clock reported:", f"{drill_minutes:.1f} min of {DRILL_MINUTES} (not counted; you time your own run)")
print(f"counted checks passed: {sum(checks.values())} of {len(checks)}; GAP lines: {sum(not v for v in checks.values())}")

# %% [markdown]
# ### Step 10: the talk
#
# The talk is three minutes and five lines. Each line names a number from the handover page, so a question can be answered from the page. Say the gaps first, then the numbers you measured.

# %%
mark("10 talk")
TALK = [
    f"1. The problem: {SCOPE['problem']}.",
    f"2. What ships: triage service {NOTE['tag']}, lesson 16's code. The candidate prompt scored {NOTE['pass_rate']:.0%} in the gate (minimum {GATE_MINIMUM:.0%}), and the red-team candidate was refused. The stack does not run that prompt.",
    f"3. What is this customer's: {CUSTOMER['storage region']} storage, {CUSTOMER['retention days']} days of retention, the same shared code.",
    "4. What we did not measure: the agents' baseline time and live traffic. What the gate did not prove: 12 invented cases (a wide interval, no real customer messages), and the shipped stack runs lesson 16's code, not this prompt.",
    "5. What your team does next: get the customer's own labelled cases, run the failure drill from lesson 28 once, and set the baseline.",
]
for line in TALK:
    print(line)

# %% [markdown]
# ### Step 11: tear down
#
# Stop and remove this lesson's containers and network. The images stay. The live output of this run is saved to `../data/32/run_log.json`, so the recording can be refreshed.

# %% tags=["needs-docker"]
mark("11 teardown")
compose("down", "--remove-orphans")  # the images stay
(DATA / "run_log.json").write_text(json.dumps(RUN_LOG, indent=1))
print("drill steps and minutes into the drill (this run):", CLOCK[-1][0], CLOCK[-1][1])

# %% [markdown]
# ## Production checklist
#
# Before you tell a customer "live", every line should be true:
#
# - [ ] The customer's rules are in config, and the shared code's fingerprint did not change (Steps 2 and 9).
# - [ ] The candidate passed the gate on this customer's own cases, and a red-team candidate was refused (Steps 4 to 6).
# - [ ] The deploy read the candidate's note and nothing else (Step 7).
# - [ ] Every number on the handover page says measured, recorded or not measured (Step 9).
# - [ ] The customer API has no published port, and traces and metrics show the service (Step 8).
# - [ ] The customer's team has a runbook and has run the system once (lessons 17, 22).

# %% [markdown]
# ## At work
#
# - **Teams rehearse the go-live with a stopwatch, not a demo.** Customer delivery is judged by the go-live date and the customer outcome, not by the feature count (RESEARCH section 3, practitioner sources). → lesson 31.
# - **Teams check that the gate can say no.** A gate that has never refused anything is not evidence (RESEARCH section 7.1, eval practice). → lessons 11, 20.
# - **Packaging and change windows decide the go-live day.** Container images in the customer's registry, reviewed configuration and change approvals take longer than the code (RESEARCH section 7.4, standard practice). → lessons 14, 24.

# %% [markdown]
# ## Reference solution
#
# The hidden cell checks the evidence behind four of the ticks, one assert each. Open it only after you have run the drill yourself.

# %% tags=["solution"]
assert NOTE["gate_passed"] and not REFUSED["gate_passed"], "R4: the candidate passes and the red-team candidate is refused"
assert deployed_after_gate, "R5: the gate and the release note ran before the deploy, with the note's tag"
assert CONTROL_OK and core_after == CORE_BEFORE, "R11: the shared code's fingerprint is unchanged and the control works"
assert not verify["erp_published"], "R6: the customer API is not published to the laptop"
print("R4, R5, R6 and R11 hold for the saved evidence. Any other GAP line above is an open item before go-live.")

# %% [markdown]
# ## Recap
#
# - A delivery drill runs the same steps for a new customer; every handover number names its source.
# - Customer rules sit in settings; shared code stays shared. Its fingerprint is a tripwire, not proof.
# - A gate proves something only when it has refused a bad candidate, on cases the customer owns.
# - The stack proves the release plumbing, not that the candidate prompt works in production.
#
# **Common mistake:** deploying from whichever release note is newest. Deploy from the note that passed.
#
# **Interview:** "Walk me through a customer delivery you ran end to end." Strong answer: "Shared code stayed unchanged and the rules lived in config. The gate passed, I had checked that it refuses a bad candidate, and the deploy read only the passed note. The handover named the source of every number and what we had not proved."

# %% [markdown]
# ## Try it
#
# A customer asks for a 70% gate instead of 90%. How many of the twelve cases must the candidate label right to pass it? Write the code, then compare with the answer. (Hint: 95% would need all twelve, so it could not separate a 95% gate from a 100% one.)

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
needed = math.ceil(0.70 * len(CASES))  # ceil(8.4) = 9
print(needed, "of", len(CASES), "cases,", f"{needed / len(CASES):.1%}", "- the candidate",
      "passes" if cand_rate >= 0.70 else "fails")

# %% [markdown]
# ## Key terms
#
# - **delivery drill** — a timed run of the whole delivery path for a new customer, from scope to handover, that finds the gaps before go-live (lesson 32)
# - **red-team candidate** — a deliberately wrong prompt that the gate must refuse, to show the gate can say no (lesson 32)
# - **release note** — the file the gate writes; the deploy reads only the note of a passed candidate (lessons 20, 31)
# - **core** and **custom** — shared code, and one customer's rules kept in config (lesson 25)
