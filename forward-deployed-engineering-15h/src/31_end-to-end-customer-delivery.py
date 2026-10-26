# %% [markdown]
# # 31 · Delivering one customer deployment end to end
#
# Level L5 · Part 3 · core · ~30 min · builds on 21, 25, 27
#
# This is the capstone of Part 3. It makes **1 model call** (the gate re-run, recorded once and replayed later) and starts one Compose stack on ports 8310 to 8312. The cells tagged `needs-docker` start and stop it. Without Docker, the saved output of the last real run is shown and labelled as recorded.

# %% [markdown]
# ## Goal
#
# By the end you can ship one scoped customer service whose release is gated, deployed only from the gate's release note, with a handover page that says what was and was not tested.

# %% [markdown]
# ## Why it matters
#
# Each earlier lesson fixed one part of a delivery: the eval gate, the config, the security answers, the logs, the runbook, the cost. A customer does not buy parts. They buy one service that works on a date, with a handover their team can run.
#
# - **Without this lesson:** the parts live in five folders. The deploy uses whatever image is on the laptop. Nobody can say which prompt is live or what it was tested against. The handover is a file written the night before go-live.
# - **With it:** one path, with one gate. The deploy refuses a release the gate did not pass. The handover page says what was measured, and what the customer must check on its own side.
# - **When you don't need it:** a one-off script for an internal team that never leaves your laptop. Anything a customer will depend on goes through the whole path.

# %% [markdown]
# ## The idea
#
# A **delivery** is a chain of decisions, each with its evidence. The scope says what is in and out. The design says which parts are shared (**core**) and which are one customer's rules (**custom**, kept in **config**). The **release gate** decides whether a model change may ship. The **release note** records the decision. The deploy starts only from a passed release note. The **handover** tells the customer's team what to run, watch and fix.
#
# Think of a kitchen before a new restaurant opens. The menu is the scope. The recipe card is the design. The taste test is the gate. The ticket on the pass is the release note. Nothing leaves the pass without a ticket.

# %% [markdown]
# ## Picture
#
# Nine steps, one path. Each arrow needs evidence from the step before.
#
# ```mermaid
# flowchart LR
#     S[1 Scope] --> D[2 Design: core and config]
#     D --> SEC[3 Security answers]
#     SEC --> G{4 Eval gate}
#     G -- passed --> R[5 Release note]
#     G -- refused --> X[Stop: fix and re-run]
#     R --> P[6 Deploy the stack]
#     P --> V[7 Verify: health, trace, metrics]
#     V --> H[8 Handover page and checks]
#     H --> T[9 Teardown]
# ```
#
# The gate tests the prompt; the deploy proves the delivery path.

# %% [markdown]
# ## Requirements
#
# Step 8 checks each row.
#
# | # | Requirement | Evidence the notebook checks | Taught in | In a replay run (no Docker) |
# | --- | --- | --- | --- | --- |
# | R1 | Scope lists exclusions | exclusions listed | 02, 03 | checked |
# | R2 | Secrets come from settings | no secret value in compose | 13, 25 | checked |
# | R3 | Security answers have evidence | each check is True | 27 | checked |
# | R4 | Release passes eval gate | gate verdict, this run | 11, 12, 20 | checked |
# | R5 | Deploy only from passed note | deploy read note; image exists | 20 | recorded, not verified here |
# | R6 | Customer API not published | `docker compose port erp` fails | 14, 15 | recorded, not verified here |
# | R7 | Health, traces, metrics visible | health, Jaeger, metrics answer | 16 | recorded, not verified here |
# | R8 | Handover rows name a source | source on every row | 21, 22 | checked |
# | R9 | Cost per case known | gate run cost printed | 18, 29 | checked |
# | R10 | Runbook and drill exist | **manual**: read the runbook | 17, 28 | manual |

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Setup
#
# The setup cell starts the recording of the one model call, loads the settings from `../.env` (names and yes/no only, no value is printed), and checks the files this lesson reads: the eval set from lesson 11, the recorded run from this lesson and the stack file from lessons 13 to 16. Lesson 20 sets the candidate prompt and the gate.

# %%
import sys, csv, json, os, subprocess, time
from pathlib import Path
from typing import Literal
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and tut_env.py
import llm_replay
llm_replay.start("31_end-to-end-customer-delivery")  # records the model call below, once
import httpx
from pydantic import BaseModel, Field
from tut_env import env, is_set, load

load()
NEEDED = ["../data/11/eval_set.csv", "../data/recorded/31.json", "../infra/compose/delivery-31.yml"]
assert not [p for p in NEEDED if not Path(p).exists()], f"missing one of {NEEDED}: run lessons 11 and 16 first"

# %% [markdown]
# Next, the settings for this lesson's Compose project and the helpers. Each helper runs Compose, polls until a service answers, or returns this run's output or the recorded one.

# %% [markdown]
# The constants first: the Compose project name, the ports, the release tag (`RELEASE_TAG`) and the gate's bar (`GATE_MINIMUM`).

# %%
DOCKER_RAN, RUN_LOG = False, {}  # DOCKER_RAN turns True in the first needs-docker cell; RUN_LOG keeps that run's output
STACK = "tut-forward-deployed-engineering-15h-31"  # one Compose project for this lesson only
COMPOSE = ["docker", "compose", "-p", STACK, "-f", "../infra/compose/delivery-31.yml", "--env-file", "../.env"]
COMPOSE_TEXT = Path("../infra/compose/delivery-31.yml").read_text()
SECRETS = ["ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"]
TRIAGE, JAEGER, PROM = "http://localhost:8310", "http://localhost:8311", "http://localhost:8312"
DATA = Path("../data/31")  # this lesson's run-time files
REC = json.loads(Path("../data/recorded/31.json").read_text())  # the last real Docker run
RELEASE_TAG, GATE_MINIMUM = "1.2.0", 0.9  # the triage version this release ships (lesson 16); the gate's bar
EXPECTED = {"BB-1000": "missing items", "BB-1001": "complete", "BB-1002": "missing items", "BB-1003": "missing items"}  # the lab's mock customer API
print("Compose project:", STACK, "| release:", RELEASE_TAG, "| gate minimum:", GATE_MINIMUM)

# %% [markdown]
# The three helpers: `compose` runs Docker Compose, `wait_for` polls until a service answers, and `from_run` returns this run's output or the recorded one.

# %%
def compose(*args, extra=None):
    """Run docker compose for this lesson's project."""
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900,
                          env={**os.environ, **(extra or {})})


def wait_for(check, timeout=90):
    """Call check() every 2 s until it returns something true, or stop at the timeout."""
    end = time.time() + timeout
    while time.time() < end:
        if value := check():
            return value
        time.sleep(2)
    raise TimeoutError(f"nothing after {timeout} s")


def from_run(key):
    """This run's output, or the recorded output when Docker was skipped."""
    return RUN_LOG[key] if DOCKER_RAN else REC[key]


# %% [markdown]
# ### Step 1: discovery and the scope sheet
#
# The customer is a Basket Bazaar store group (invented). Its support agents read each delivery message by hand. The scope sheet names the problem, what is in, what is out, and how success is measured. A number you do not have is written as **not measured**, never guessed. The labelled cases are the golden set from lesson 11: 12 messages, one people's label each.

# %%
SCOPE = {
    "problem": "support agents sort delivery messages into missing, wrong, late or damaged items too slowly",
    "in scope": "label one message with one issue (five labels); show the label to the agent",
    "out of scope": "refunds, credits, courier dispatch, any write to the customer's order system",
    "success measure": "pass rate on lesson 11's labelled cases, at least 90%, and no failed release",
    "baseline": "not measured: how long agents take today is not known yet",
}
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "scope.json").write_text(json.dumps(SCOPE, indent=1))
print("\n".join(f"{key:<16}{value}" for key, value in SCOPE.items()))
with open("../data/11/eval_set.csv", newline="") as f:
    CASES = list(csv.DictReader(f))
print(len(CASES), "labelled cases from lesson 11, for example:", CASES[0])

# %% [markdown]
# ### Step 2: design, core and config
#
# The reference architecture from lesson 21 has the same parts for every customer. Only the config differs.
#
# - **Core, shared, changes only through review:** the triage prompt and its five labels, the eval gate and scorer, the triage service image, the handover page.
# - **Custom, set in config (lesson 25):** the customer API address and client id, the data regions and retention days (lesson 27 settings).
# - **Where the custom part sits:** the `${NAME}` settings in `../infra/compose/delivery-31.yml`, filled from `../.env`; Step 8 checks that no secret value is written in the file.

# %% [markdown]
# ### Step 3: the security answers, with evidence
#
# A customer's review asks questions. Each answer needs a check that can fail. The checks read the settings from the lesson 27 pack. The last answer is filled in after the deploy, in Step 8.

# %%
REGIONS = env("ALLOWED_REGIONS", "us-east1,us-central1").split(",")
SECURITY = {
    "data stored in an allowed region": env("STORAGE_REGION", "us-east1") in REGIONS,
    "model prompts processed in an allowed region": env("MODEL_REGION", "us-east1") in REGIONS,
    "retention within the contract maximum": int(env("RETENTION_DAYS", "30")) <= int(env("CONTRACT_MAX_RETENTION_DAYS", "90")),
    "reader secret comes from settings, not from the image": is_set("ERP_READER_CLIENT_SECRET"),
    "customer API has no published port": None,  # pending until Step 8
}
for question, answer in SECURITY.items():
    print(f"{'pending' if answer is None else answer!s:<8} {question}")

# %% [markdown]
# ### Step 4: the eval gate, one model call
#
# The candidate prompt is lesson 20's candidate v2, with its definitions and counting rule. The model labels all twelve cases in one structured call. One call keeps the gate at one request, and all twelve labels come from the same prompt in the same run, so the pass rate measures the prompt. The scorer is plain code: a missing answer is a fail.

# %%
Issue = Literal["missing_item", "wrong_item", "late", "damaged", "other"]


class Triage(BaseModel):
    case_id: str = Field(description="the case id exactly as given, such as C01")
    issue: Issue


class TriageBatch(BaseModel):
    labels: list[Triage] = Field(description="one entry for every case id given")


PROMPT_CANDIDATE = (
    "Label each grocery delivery support message with one issue: missing_item, wrong_item, late, damaged or other. "
    "Return one label for every case id.\nDefinitions:\n"
    "- missing_item: the customer did not get all of an item they paid for, even when they say only some of it arrived.\n"
    "- late: the delivery came after the slot, or still shows as pending.\n"
    "- damaged: broken, bruised, crushed, split or leaking.\n"
    "- wrong_item: the customer got a different item from the one ordered.\n"
    "- other: none of the above, such as a courier problem.\n"
    "- Rule: if the customer names a count of items (two, three, only, not all), the issue is missing_item.")
PRICE = {"input": 0.25, "output": 1.50}  # USD per million tokens, Gemini API standard text (lesson 18)
PRICE_DATE, COST_PER_CASE_BUDGET = "2026-10-22", 0.001  # the budget: a tenth of a cent per case
CALLS = []  # one entry per real model call
print("candidate prompt:", len(PROMPT_CANDIDATE), "characters; 12 cases go in one call")

# %% [markdown]
# The model call. The request is one system prompt and the numbered cases. The answer must match the schema, so a missing or extra case id is caught by the scorer.

# %%
def run_candidate(prompt: str) -> dict:
    """The real model call: all cases in one request. Returns the labels by case id."""
    from llm_setup import get_llm
    numbered = "\n".join(f"{c['case_id']}: {c['message']}" for c in CASES)
    out = get_llm().with_structured_output(TriageBatch, method="json_schema", include_raw=True).invoke(
        [("system", prompt), ("human", numbered)])
    usage = out["raw"].usage_metadata
    cost = (usage["input_tokens"] * PRICE["input"] + usage["output_tokens"] * PRICE["output"]) / 1e6
    CALLS.append({"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                  "cost_usd": round(cost, 7)})
    return {t.case_id: t.issue for t in out["parsed"].labels}

# %% [markdown]
# Now the call, then the plain-code scorer. The pass rate is the share of cases where the label equals the people's label. `llm_setup` prints the access path (Gemini on Vertex AI) and whether a key is set. It never prints the key. Twelve cases in one call is a fair gate: one miss costs 8 points of pass rate. Every case is judged in the same run.

# %%
labels = run_candidate(PROMPT_CANDIDATE)  # the one model call of this lesson
got = {c["case_id"]: (c["want"], labels.get(c["case_id"])) for c in CASES}
hits = sum(want == label for want, label in got.values())
pass_rate = hits / len(got)
# where the numbers come from: a live call, or the saved recording (read before llm_replay.stop())
MODEL_SRC = "recorded (model call, replayed)" if llm_replay.mode() == "replay" else "measured (model call, this run)"
print(f"candidate: {pass_rate:.0%} pass ({hits} of {len(got)})")
for cid, (want, label) in got.items():
    if want != label:
        print(f"  FAIL {cid}: want={want:<12} got={label}")

# %% [markdown]
# The model call is the last one this lesson makes. The recording stops here, so the Docker steps below, which call only local services, are not saved in it.

# %%
llm_replay.stop()  # saves the recording of the one model call
print("model calls in this notebook:", len(CALLS), "of 5 allowed")

# %% [markdown]
# ### Step 5: the release note
#
# The gate passes when the pass rate meets the minimum. The release note records the verdict, the tag, the prompt and the cost of the gate run. The deploy in Step 6 reads this file and nothing else.

# %%
per_case = CALLS[0]["cost_usd"] / len(CASES)
release = {"tag": RELEASE_TAG, "prompt": "candidate v2", "pass_rate": round(pass_rate, 3),
           "gate_minimum": GATE_MINIMUM, "gate_passed": pass_rate >= GATE_MINIMUM,
           "cost_per_case_usd": round(per_case, 7), "cost_per_case_ok": per_case <= COST_PER_CASE_BUDGET}
(DATA / "release_note.json").write_text(json.dumps(release, indent=1))
print(json.dumps(release, indent=1))

# %% [markdown]
# ### Step 6: deploy, and only from the release note
#
# No Docker? Skip the tagged cells. Steps 7 to 8 then read `data/recorded/31.json`, and R5 to R7 show "recorded, not verified here".
#
# The deployed triage service is the lab's stand-in: it labels by the number of short lines (lesson 16 code), with no model call. So the candidate prompt is not live, and the handover says so. The stand-in's labels (`missing items`, `complete`) are the lesson 16 lab vocabulary, not the five scope labels. Step 7 only proves the delivery path.

# %% [markdown]
# The cell below opens the release note, refuses a release the gate did not pass, and starts the stack in `../infra/compose/delivery-31.yml`: the customer API on an internal network, the triage service as the one door on port 8310, and the Collector, Jaeger (8311) and Prometheus (8312). It records what the deploy read and checks the image exists.

# %% tags=["needs-docker"]
DOCKER_RAN = True
note = json.loads((DATA / "release_note.json").read_text())
assert note["gate_passed"], "the gate refused this release: no deploy"
RUN_LOG["deploy_read"] = {"tag": note["tag"], "gate_passed": note["gate_passed"]}  # what the deploy read
compose("down", "--remove-orphans")  # start from a clean stack
up = compose("up", "-d", "--build", "--wait", extra={"TRIAGE_TAG": note["tag"]})
assert up.returncode == 0, up.stderr[-600:]
RUN_LOG["deploy_read"]["image_exists"] = subprocess.run(
    ["docker", "image", "inspect", f"bb-triage-delivery:{note['tag']}"], capture_output=True).returncode == 0
wait_for(lambda: all(httpx.get(u, timeout=5).status_code == 200 for u in [f"{JAEGER}/", f"{PROM}/-/ready"]))
RUN_LOG["up"] = compose("ps", "--format", "table {{.Service}}\t{{.Status}}").stdout.strip()[-600:]
print("compose up, exit code:", up.returncode, "| image exists:", RUN_LOG["deploy_read"]["image_exists"])

# %% [markdown]
# The line below shows this run's status, or the recorded status when Docker was skipped.

# %%
print("stack status,", "this run, live" if DOCKER_RAN else "recorded output from the last real run")
print(from_run("up"))

# %% [markdown]
# ### Step 7: verify the running service
#
# Five checks, each a real answer. The triage service answers its health check, and its labels carry the release version. The four orders from the lab's customer API (the lesson 13 mock) get the lab's expected label. The customer API has no published port on the laptop. Jaeger lists the triage service, and the metrics endpoint shows the request-time series. These checks test the delivery path, not the prompt.

# %% tags=["needs-docker"]
wait_for(lambda: httpx.get(f"{TRIAGE}/health", timeout=5).status_code == 200)
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
RUN_LOG["verify"] = {"answers": answers, "erp_published": erp_published,
                     "jaeger_services": services, "metric_series": len(metric_lines)}
print(RUN_LOG["verify"])

# %% [markdown]
# Each line below answers one check from the Step 7 list. Read a False as a gap, not as a bug to hide.

# %%
verify = from_run("verify")
versions = {a.get("version") for a in verify["answers"].values()}
print("release version seen:", versions, "| matches the note:", versions == {RELEASE_TAG})
print("labels match the lab's expected labels:", all(a.get("label") == EXPECTED[o] for o, a in verify["answers"].items()))
print("customer API published to the laptop:", verify["erp_published"], "(must be False)")
print("bb-triage in Jaeger:", "bb-triage" in verify["jaeger_services"], "| metric series:", verify["metric_series"])

# %% [markdown]
# ### Step 8: the handover page and the requirement check
#
# The customer gets one page. Every row names its source. A row is **measured** when this run produced it with Docker, **recorded** when it comes from the saved run, and **not measured** when nobody has the number yet. A row that is a pointer rather than a number is labelled **documented, not run here** or **lab design**. The last security answer is filled in from Step 7 here.

# %%
src = "measured" if DOCKER_RAN else "recorded"
SECURITY["customer API has no published port"] = not verify["erp_published"]
SOURCES = {"measured", "recorded", "not measured", "documented, not run here", "lab design (lesson 16 code)", MODEL_SRC}
page = [
    ("Gate verdict", "passed" if release["gate_passed"] else "refused", MODEL_SRC),
    ("Pass rate, candidate", f"{release['pass_rate']:.0%} (minimum {GATE_MINIMUM:.0%})", MODEL_SRC),
    ("Cost per case, gate run", f"${release['cost_per_case_usd']:.7f} (prices {PRICE_DATE})", MODEL_SRC),
    ("Prompt the deployed service runs", "lab stand-in, not the candidate", "lab design (lesson 16 code)"),
    ("Service version", ", ".join(sorted(str(v) for v in versions)), src),
    ("Customer API reachable from laptop", "no" if not verify["erp_published"] else "yes: fix before go-live", src),
    ("Triage traces in Jaeger", "yes" if "bb-triage" in verify["jaeger_services"] else "no", src),
    ("Baseline for agent time", "not measured", "not measured"),
    ("Live customer traffic", "not measured: this lab has no customer data", "not measured"),
    ("Runbook for failures", "lesson 17 runbook; drill in lesson 28", "documented, not run here"),
]
(DATA / "handover.json").write_text(json.dumps(page, indent=1))
print(f"{'What the customer sees':<36}{'Value':<50}Source")
for what, value, source in page:
    print(f"{what:<36}{value:<50}{source}")

# %% [markdown]
# Now tick the requirements. A GAP line names what is still missing. R10 is manual, so it is never ticked here. R5 to R7 need a Docker run: in a replay run, a passing one prints "recorded, not verified here".

# %%
DEPLOY = RUN_LOG.get("deploy_read") if DOCKER_RAN else REC.get("deploy_read")  # what the deploy read
LIVE_ONLY = ("R5", "R6", "R7")  # need a Docker run; a replay reads them from the recording
checks = {
    "R1 out-of-scope named": bool(SCOPE["out of scope"]),
    "R2 customer secrets from settings, none in the file": all(f"${{{n}}}" in COMPOSE_TEXT for n in SECRETS)
        and not any(v and v in COMPOSE_TEXT for v in (env(n, "") for n in SECRETS)),  # values are never printed
    "R3 security answers all True": all(v is True for v in SECURITY.values()),
    "R4 gate passed": release["gate_passed"],
    "R5 deploy read this run's passed note, image built": bool(release["gate_passed"] and DEPLOY
        and DEPLOY["gate_passed"] and DEPLOY["tag"] == release["tag"] and DEPLOY["image_exists"]),
    "R6 customer API not published": not verify["erp_published"],
    "R7 health, traces, metrics": "bb-triage" in verify["jaeger_services"] and verify["metric_series"] > 0 and len(verify["answers"]) == 4,
    "R8 every handover row has a known source": all(row[2] in SOURCES for row in page),
    "R9 cost per case known": bool(CALLS) and release["cost_per_case_ok"],
    "R10 runbook pointer (manual)": None,
}
for name, ok in checks.items():
    status = ("manual" if ok is None else "GAP" if not ok
              else "recorded, not verified here" if name[:2] in LIVE_ONLY and not DOCKER_RAN else "ok")
    print(f"{status:<30} {name}")

# %% [markdown]
# ### Step 9: tear down
#
# Stop and remove this lesson's containers and network. The images stay. The live output of this run is saved to `../data/31/run_log.json`, so the recording can be refreshed.

# %% tags=["needs-docker"]
(DATA / "run_log.json").write_text(json.dumps(RUN_LOG, indent=1))
compose("down", "--remove-orphans")  # the images stay
print("stack down; this run's output saved to ../data/31/run_log.json")

# %% [markdown]
# ## At work
#
# - **Teams ship only what passes the eval gate.** They start with 20 to 50 tasks drawn from real failures and grade them with code, a model or a person (Anthropic's eval guidance, RESEARCH section 7.1). → lessons 11, 12, 20.
# - **Customer security reviews ask for evidence, not promises.** Expect a data-flow diagram, subprocessors, retention terms, audit logs and SOC 2 evidence (common practice, RESEARCH section 7.3). → lesson 27.
# - **Production traffic stays inside the customer's network.** The model and the customer API sit behind an internal network and an egress allow-list (RESEARCH section 7.4). → lessons 14, 15.
# - **Cost is quoted per resolved case and per tenant per month, not per token** (RESEARCH section 7.6). → lesson 29.

# %% [markdown]
# ## Common mistakes
#
# The gate's flag has an exact name, `gate_passed`. A typo in the name is the kind of mistake a deploy script makes, and the failure is the safe one: no deploy.

# %% tags=["raises-exception"]
release_wrong = json.loads((DATA / "release_note.json").read_text())
assert release_wrong["gate"], "wrong key: the note says gate_passed"  # KeyError: 'gate'

# %% [markdown]
# **Fix:** read the flag by its exact name, and let the assert stop the deploy. Never deploy from the laptop's image without a note for that image.

# %% [markdown]
# ## Production checklist
#
# Before you tell a customer "live", every line should be true:
#
# - [ ] The release note says gate passed, and the deploy read it (Steps 5 and 6).
# - [ ] Every number on the handover page says measured, recorded or not measured (Step 8).
# - [ ] The customer API has no published port, and the triage service is the one door (Step 7).
# - [ ] Traces and metrics show the triage service before anyone calls it live (Step 7).
# - [ ] The security answers each point to evidence, or to a named gap (Step 3).
# - [ ] The cost per case is known and within the budget (Steps 4 and 5).
# - [ ] The customer's team has a runbook and has run the system once (lessons 17, 22).

# %% [markdown]
# ## Try it
#
# Two tasks. First, change `GATE_MINIMUM` in the constants cell (the one with `RELEASE_TAG`, `GATE_MINIMUM`) to `1.1` and re-run from that cell. Which requirements show GAP, and why does Step 6 stop? Second, write `gap_report(checks)`: it returns the names of the requirements that show GAP (value `False`). A `None` value is a manual check, not a GAP.

# %%
# your code here
def gap_report(checks):
    """Return the names of the requirements whose value is False."""
    ...

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
# With GATE_MINIMUM = 1.1 the pass rate is below the minimum, so the note says gate_passed is False.
# GAP: R4 "gate passed" (release["gate_passed"] is False), and R5 "deploy read this run's passed note, image built".
# R5 is a GAP because release["gate_passed"] is False: it needs a passed gate in this run before the deploy can count.
# With Docker, Step 6 stops at its first line, assert note["gate_passed"], with "the gate refused this release: no deploy".
# Without Docker, Step 6 does not run, so the GAP lines in the requirement check are the only signal.
def gap_report(checks):
    """Return the names of the requirements whose value is False."""
    return [name for name, ok in checks.items() if ok is False]

# %% [markdown]
# ## Reference solution
#
# The gap list for this run, from the checks in Step 8. An empty list means every automatic requirement passed.

# %% tags=["solution"]
print("GAP for this run:", gap_report(checks) or "none")

# %% [markdown]
# ## Recap
#
# - A delivery is a chain of decisions, and each decision points to its evidence.
# - The gate decides the release; the release note records it; the deploy reads only the note.
# - The handover names its source for every number: measured, recorded or not measured.
#
# **Common mistake:** a deploy from the laptop's latest image, with no gate run for that image. Deploy from the note.
#
# **Interview:** "Walk me through how you take a customer's AI feature from scoping to go-live." Strong answer: "I scope it with in and out lists and a baseline I measure, not guess. Customer rules go in config and shared code stays shared. A model change passes the eval gate before a release note is written. The deploy reads only that note, the customer API stays off the public network, and the handover says what was measured and what the customer must check."

# %% [markdown]
# ## Key terms
#
# - **release gate** — a rule that stops a release unless the evidence passes (lesson 20)
# - **release note** — the file the gate writes (tag, prompt, verdict, numbers, cost); the deploy reads it first and stops if the gate did not pass (lessons 20, 31)
# - **handover** — the transfer of a deployed service to the customer's team, with docs and training (lesson 22)
# - **core** and **custom** — shared code, and one customer's rules kept in config (lesson 25)
