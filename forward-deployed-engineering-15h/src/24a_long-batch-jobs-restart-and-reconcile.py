# %% [markdown]
# # 24a · Long batch jobs: restart, reconcile and finish on time
#
# Level L5 · Part 3 · professional · ~30 min · builds on 04, 14, 24
#
# Needs Docker with Compose v2 (`docker compose version`) and port 9240 free. Cells tagged `needs-docker` start containers. When they are skipped, the checks after them print the recorded output from the last real run, labelled as such. The run makes no model calls: the labels come from fixed rules.

# %% [markdown]
# ## Goal
#
# By the end you can split a batch of orders across two nodes, work out how many calls must be in flight to meet a deadline, make every write an upsert keyed by `(order_id, run_id)` so that a replay writes nothing twice, reconcile the counts of each part against a run manifest, and, when the run falls behind, check the cause in order and change one thing.

# %% [markdown]
# ## Why it matters
#
# A nightly batch is a loop over many orders, one customer call each. Done the simple way, it fails in three ways. Too slow: one call at a time finishes after the window closes. Too fragile: a crash near the end forces a restart from zero. Too loose: a restart that appends rows writes some orders twice, and nothing complains. The numbers below are for a story-sized batch: 1.2 million orders, a six-hour window, and 150 ms per customer call.

# %%
import math

STORY_ORDERS, STORY_WINDOW_H, LATENCY_MS = 1_200_000, 6, 150
rate = STORY_ORDERS / (STORY_WINDOW_H * 3600)
print(f"one call at a time: {STORY_ORDERS * LATENCY_MS / 1000 / 3600:.0f} hours (the window is {STORY_WINDOW_H} h)")
print(f"orders per second needed: {rate:.1f}")
print(f"calls in flight needed (Little's law: rate x latency): {rate * LATENCY_MS / 1000:.1f}, so at least {math.ceil(rate * LATENCY_MS / 1000)}")

# %% [markdown]
# - **Without it:** one call at a time takes about 50 hours. A restart re-sends every order, and a plain append writes the early orders twice.
# - **With it:** a few calls in flight, sized from the deadline; a stable key on every row; a manifest that says how many orders each part should hold, checked after the run.
# - **When you don't need it:** a batch that finishes inside its window with one call at a time, or a customer who offers one bulk endpoint. Check that first.

# %% [markdown]
# ## The idea
#
# Four ideas, in two parts. **Partition**: each order goes to one part, chosen by a stable hash of its `order_id`, and each node owns some parts. **In-flight calls**: a node keeps a fixed number of calls running at once. By **Little's law**, the calls in flight equal the rate times the latency, so the deadline sets the concurrency.

# %% [markdown]
# **Upsert**: a write that inserts a row or, if the key already exists, updates it. Keyed by `(order_id, run_id)`, a replay overwrites the same row. **Manifest and reconciliation**: the manifest says how many orders each part should hold; the run is finished only when every part's count matches.
#
# Think of an exam hall. The seating plan is the manifest, the register is the reconciliation, and a student who sits the same paper twice still has one mark.

# %% [markdown]
# ## Picture
#
# The input is split into parts, each node works its own parts, and every result lands once in a table keyed by order and run.

# %% [markdown]
# ```mermaid
# flowchart LR
#     IN[orders.csv] --> M[manifest: planned count per part]
#     M --> A[node a: parts 0 and 2]
#     M --> B[node b: parts 1 and 3]
#     A -->|N calls in flight| API[customer API]
#     B -->|N calls in flight| API
#     A --> T[(results table)]
#     B --> T
#     T --> R[reconcile each part against the manifest]
# ```

# %% [markdown]
# ## Before you start
#
# This lesson builds on three earlier ones. Lesson 04 gave the worker its retries (tenacity, for 429 and 502 to 504 responses) and the idempotency key that the upsert uses here. Lesson 14 gave the Compose pattern: start with `--wait` and a health check. Lesson 24 showed that a node can be killed and restarted without losing work; here that happens on purpose.
#
# The input is the invented orders file from lesson 05, after its cleaning step: `orders_clean.csv`. The raw export has 247 lines and 128 `order_id` spellings, 8 of which are the same order written with different case or spaces. The cleaned export has 224 lines and 120 distinct orders, and the lab runs the batch on those 120. Each run gets its own id and folder, so counts start at zero.

# %%
import csv, hashlib, json, math, os, sqlite3, subprocess, sys, time, uuid
from contextlib import closing
from pathlib import Path

import httpx

sys.path.insert(0, "..")
from tut_env import load

load()
INPUT = Path("../data/05/orders_clean.csv").resolve()  # invented orders, cleaned in lesson 05 (generated, no real customer data)
ERP = "http://127.0.0.1:9240"  # the customer API mock on this lesson's port
COMPOSE = ["docker", "compose", "-p", "batch-24a-lab", "-f", "../infra/compose/batch-24a.yml", "--env-file", "../.env"]
PARTS, NODES, WINDOW_S = 4, 2, 8  # four parts, two nodes; the lab deadline is 8 seconds (the story's is six hours)
RUN_ID = "nightly-" + uuid.uuid4().hex[:8]  # a new id each time this notebook starts
RUN_DIR = Path("../data/24a/runs") / RUN_ID
RUN_DIR.mkdir(parents=True)
RUN_DIR.chmod(0o777)  # the containers run as a non-root user and write here (lab only)
DOCKER_RAN = False  # the needs-docker cells set this to True
CAPTURED = {}  # the live output of each docker cell, saved at the end
REC = json.loads(Path("../data/recorded/24a.json").read_text())  # saved from a real Docker run
LABEL = f"recorded output from the last real Docker run on {REC['_recorded']} (timing-based numbers change on every run)"
print("run id:", RUN_ID)

# %% [markdown]
# Here is a peek at the input: the first lines, then the count of lines and of distinct orders.

# %%
rows = list(csv.DictReader(INPUT.open(newline="")))
orders = sorted({r["order_id"] for r in rows})
for r in rows[:3]:
    print(r)
print(f"{len(rows)} lines for {len(orders)} distinct orders")

# %% [markdown]
# The 224 cleaned lines become 120 distinct orders. The lab makes one call per order, and duplicate lines collapse onto the same `order_id`, so each order is fetched and written once.

# %% [markdown]
# Two helpers talk to the lab. `compose_run` runs Docker Compose for this lesson's project and passes the run settings to it. `api_stats` reads or resets the customer API's counters. `db_rows` counts this run's rows in the results table.

# %%
def compose_run(*args, extra=None):
    env = {**os.environ, "BATCH_INPUT": str(INPUT), "BATCH_RUN_DIR": str(RUN_DIR.resolve()),
           "BATCH_RUN_ID": RUN_ID, "BATCH_PARTS": str(PARTS), **(extra or {})}
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, timeout=900, env=env)


def api_stats(reset=False):
    return httpx.post(f"{ERP}/lab/reset").json() if reset else httpx.get(f"{ERP}/lab/stats").json()


def db_rows():
    path = RUN_DIR / "batch.db"  # no file or table until the first worker writes: 0 rows
    if not path.exists():
        return 0
    try:
        with closing(sqlite3.connect(path, timeout=10)) as db:
            return db.execute("SELECT COUNT(*) FROM results WHERE run_id = ?", (RUN_ID,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 0

# %% [markdown]
# `progress` reads each node's progress file. `start_nodes` starts both nodes with the given calls in flight, after it clears the old progress files. `wait_done` waits until both nodes report done and their containers have exited. `say` prints saved results, live or recorded.

# %%
def progress():
    return [json.loads(p.read_text()) for p in sorted(RUN_DIR.glob("progress-*.json"))]


def done_nodes():
    files = progress()
    return len(files) == NODES and all(p["state"] == "done" for p in files)


def start_nodes(concurrency):
    for p in RUN_DIR.glob("progress-*.json"):  # old progress must not look like the new run
        p.unlink()
    return compose_run("up", "-d", "worker-a", "worker-b", extra={"BATCH_CONCURRENCY": str(concurrency)})


def wait_done(timeout=120):
    end = time.time() + timeout
    while time.time() < end and not done_nodes():
        time.sleep(0.5)
    compose_run("wait", "worker-a", "worker-b")  # a node writes "done" just before its container exits
    return done_nodes()


def say(*keys):
    """Print this run's live lines, or the recorded lines when Docker was skipped."""
    if DOCKER_RAN:
        print("\n".join(line for k in keys for line in CAPTURED[k]))
    else:
        print(LABEL, *(line for k in keys for line in REC[k]), sep="\n")

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: start the customer API
#
# The customer API is the only service that stays up for the whole run. `--wait` returns when its health check passes, so the nodes never start before the API answers. The API is a local mock; its code is in `../apps/24a/erp_mock.py`. It takes 150 ms per call and refuses a call with 429 when 8 calls are already in flight.

# %% tags=["needs-docker"]
DOCKER_RAN = True
up = compose_run("up", "-d", "--build", "--wait", "erp")
if up.returncode:  # stop here with the reason, instead of running on without the API
    raise RuntimeError(up.stderr.strip()[-800:])
CAPTURED["erp_up"] = [f"exit code: {up.returncode}", f"api health: {httpx.get(f'{ERP}/health').json()}"]

# %% [markdown]
# The API start printed (live here, recorded when Docker was skipped):

# %%
say("erp_up")

# %% [markdown]
# ### Step 2: size the calls in flight, then start two nodes too slowly
#
# The lab window is 8 seconds for 120 orders: 15 orders a second. At 150 ms per call, that needs 2.25 calls in flight (Little's law again), so at least 3. The first try starts two nodes with one call each. That is 2 in flight, about 13 orders a second, so the run is behind pace from the start. The nodes run the same code; the parts split the orders between them.

# %% tags=["needs-docker"]
api_stats(reset=True)
nodes = start_nodes(concurrency=1)
if nodes.returncode:
    raise RuntimeError(nodes.stderr.strip()[-800:])
CAPTURED["start_nodes"] = [f"exit code: {nodes.returncode}", "nodes started with 1 call in flight each"]

# %% [markdown]
# The node start printed (live or recorded):

# %%
say("start_nodes")

# %% [markdown]
# ### Step 3: the pace check, in order
#
# Check 3 seconds after both nodes are calling the API. The deadline needs `orders x elapsed / window` rows by then. Read the three signals in the same order every time: the results table (pace), then the API's refusals (429), then the slots in use. Check the cheapest first, and change one thing at a time.

# %% tags=["needs-docker"]
end = time.time() + 60
while api_stats()["max_inflight"] < NODES and time.time() < end:  # wait until both nodes are calling the API
    time.sleep(0.1)
time.sleep(3)  # the lab clock starts here, so container start-up does not count against the batch
done, expected, stats = db_rows(), math.ceil(len(orders) * 3 / WINDOW_S), api_stats()
CAPTURED["pace"] = [f"rows done: {done}, needed by now: {expected}, behind: {done < expected}",
                    f"api: {stats['calls']} calls, {stats['rejected_429']} refused (429), most in flight at once: {stats['max_inflight']}"]

# %% [markdown]
# The ordered check reads the same three signals in the same order and returns the first answer that fits. It is plain Python, so it runs with or without Docker.

# %%
def ordered_check(done, expected, stats, concurrency, nodes=NODES):
    """Read the three signals in this order: the results table, the API's refusals, then the slots in use."""
    if done >= expected:
        return "1. on pace: change nothing"
    if stats["rejected_429"] > 0:
        return "2. the API refuses calls: do not add calls in flight; ask the customer for a higher limit"
    if stats["max_inflight"] >= nodes * concurrency:  # every node has all its slots busy
        return "3. the API is fine and every node uses all its slots: add calls in flight"
    return "4. the API is fine and slots are idle: look at the node logs and the network"

# %% [markdown]
# The pace check and the ordered check's answer (live or recorded):

# %%
if DOCKER_RAN:
    CAPTURED["action"] = [f"ordered check says: {ordered_check(done, expected, stats, concurrency=1)}"]
say("pace", "action")

# %% [markdown]
# The check says step 3: the API refuses nothing and both nodes are busy, so the fix is more calls in flight. Changing the setting means restarting the nodes. Here both nodes are killed hard (`SIGKILL`, like a power cut) and restarted with 3 calls in flight each: 6 in total, more than the 3 the deadline needs, and under the API's limit of 8. The restart does not start over: each node reads the rows already written and skips those orders.

# %% tags=["needs-docker"]
kill = compose_run("kill", "worker-a", "worker-b")
compose_run("wait", "worker-a", "worker-b")
rows_at_crash = db_rows()
restart = start_nodes(concurrency=3)
finished = wait_done()
CAPTURED["restart"] = [f"killed both nodes with {rows_at_crash} rows written; exit code: {kill.returncode}",
                       f"restarted with 3 calls in flight each; exit code: {restart.returncode}; finished: {finished}",
                       f"progress after restart: {[(p['node'], p['skipped_at_start'], p['written_this_start']) for p in progress()]}"]

# %% [markdown]
# The crash and the restart printed (live or recorded):

# %%
say("restart")

# %% [markdown]
# Your count will differ: it is whatever was written when the kill landed. Read it from the "killed both nodes" line above and from the progress line after the restart. The skipped column, summed over both nodes, adds up to the rows at the kill, and the rest of the orders are written by the restart, so skipped plus written is 120. If the rows at the kill were 0, the crash came before the first write, so the restart skips nothing and writes all 120.
#
# Now the reconciliation: the manifest says how many orders each part must hold, and the results table must agree part by part. It also checks the input file itself, by its checksum.

# %%
def reconcile():
    manifest = json.loads((RUN_DIR / "manifest.json").read_text())
    with closing(sqlite3.connect(RUN_DIR / "batch.db")) as db:
        per_part = dict(db.execute("SELECT part, COUNT(*) FROM results WHERE run_id = ? GROUP BY part", (RUN_ID,)).fetchall())
        total, distinct = db.execute("SELECT COUNT(*), COUNT(DISTINCT order_id) FROM results WHERE run_id = ?", (RUN_ID,)).fetchone()
    owner = {int(p): node for node, ps in manifest["owners"].items() for p in ps}
    lines = [f"{'part':<6}{'node':<6}{'planned':>8}{'in table':>10}{'match':>7}"]
    for p, planned in sorted(manifest["planned_per_part"].items(), key=lambda kv: int(kv[0])):
        got = per_part.get(int(p), 0)
        lines.append(f"{p:<6}{owner[int(p)]:<6}{planned:>8}{got:>10}{str(got == int(planned)):>7}")
    lines.append(f"total rows {total}, distinct orders {distinct}, duplicates {total - distinct}")
    lines.append(f"input checksum matches the manifest: {hashlib.sha256(INPUT.read_bytes()).hexdigest() == manifest['input_sha256']}")
    return lines


if DOCKER_RAN:
    CAPTURED["reconcile"] = reconcile()
say("reconcile")

# %% [markdown]
# Every part matches, there are no duplicates, and the input is the file the manifest describes. A part that does not match is a real problem: stop, find the missing or extra orders, and only then rerun.
#
# ### Step 4: replay the same run
#
# A replay is a second start of the same run id: the nodes read the results table, find every order done, and send no call. The table must not change. The API counter shows whether a call was made.

# %% tags=["needs-docker"]
before = db_rows()
api_stats(reset=True)
replay = start_nodes(concurrency=3)
finished = wait_done()
progress_now = [(p["node"], p["skipped_at_start"], p["written_this_start"]) for p in progress()]
CAPTURED["replay"] = [f"rows before the replay: {before}, after: {db_rows()}",
                      f"api calls during the replay: {api_stats()['calls']}",
                      f"progress during the replay (node, skipped, written): {progress_now}",
                      f"replay start exit code: {replay.returncode}; finished: {finished}"]
if not finished:  # show why a node did not report, instead of waiting in silence
    CAPTURED["replay"].append(replay.stderr.strip()[-300:])

# %% [markdown]
# The replay printed (live or recorded):

# %%
say("replay")

# %% [markdown]
# A replay that writes nothing is what you want after a crash. Calls can outnumber orders: in the pace check the API may have counted more calls than rows written, and the difference is the calls still in flight when the check ran. A crash works the same way: calls that were open when a node died are sent again on restart, so the API sees more calls than orders in total. The upsert still keeps one row per order and run.

# %% [markdown]
# ## At work
#
# - **Batch APIs for offline work.** Anthropic's Batch API is 50% off input and output and stacks with prompt caching, for work that does not need an answer in seconds. Price a nightly job that way before you size the concurrency. → lesson 29 prices it per unit.
# - **Durable execution.** Temporal records each step of a workflow in an event history and replays it after a crash, so a restart resumes where the run stopped ([Temporal: why Temporal](https://docs.temporal.io/evaluate/why-temporal)). This lesson does the same with one key per order. Go deeper: a workflow engine is the next step when a run lasts days or needs human approval in the middle.
# - **Pace checks are runbook steps.** A late batch is an incident for the on-call person, with a fixed order of checks and a fixed action for each result. → lesson 17 writes that as a runbook.

# %% [markdown]
# ## Common mistakes
#
# - **A plain append on restart.** Without a key, a second run writes every row again and nothing fails. The table below has no key, so the second insert of the same order is silently kept.

# %%
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE results (order_id TEXT, label TEXT)")  # no key
for _ in range(2):  # the same order written by the first run and by the restart
    db.execute("INSERT INTO results VALUES ('BB-1063', 'ok')")
print("rows for one order:", db.execute("SELECT COUNT(*) FROM results").fetchone()[0])

# %% [markdown]
# The fix is a key on `(order_id, run_id)`. With the key, a plain `INSERT` on the second write fails at once. That error is better than silent duplicates, but it stops the replay.

# %% tags=["raises-exception"]
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE results (order_id TEXT, run_id TEXT, label TEXT, PRIMARY KEY (order_id, run_id))")
db.execute("INSERT INTO results VALUES ('BB-1063', 'nightly-1', 'ok')")
db.execute("INSERT INTO results VALUES ('BB-1063', 'nightly-1', 'ok')")  # the replay: a plain INSERT

# %% [markdown]
# The upsert keeps the key and updates the row on the second write instead of failing. The workers do exactly this, and a restart first reads the done keys and skips them.

# %%
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE results (order_id TEXT, run_id TEXT, label TEXT, PRIMARY KEY (order_id, run_id))")
for _ in range(2):  # the first write, then the replay
    db.execute("""INSERT INTO results VALUES ('BB-1063', 'nightly-1', 'ok')
                  ON CONFLICT (order_id, run_id) DO UPDATE SET label = excluded.label""")
print("rows for one order:", db.execute("SELECT COUNT(*) FROM results").fetchone()[0])

# %% [markdown]
# - **Python's `hash()` for the partition.** Its value changes between processes, so two nodes can disagree about who owns an order. The check below runs the same expression in two processes with different hash seeds. The fix is `zlib.crc32`, the same in every process.

# %%
import zlib

for seed in ("1", "2"):
    out = subprocess.run([sys.executable, "-c", "print(hash('BB-1063') % 4)"], capture_output=True, text=True,
                         env={**os.environ, "PYTHONHASHSEED": seed})
    print(f"hash seed {seed}: part {out.stdout.strip()}")
print("crc32, every process: part", zlib.crc32(b"BB-1063") % 4)

# %% [markdown]
# The same order can land in a different part in each process, because each process has its own hash seed. `crc32` gives the same part in every process: the last line above.
#
# - **More calls in flight than the API allows.** The API answers a call over its limit with `429 Too Many Requests` and the body `{"detail": "too many calls in flight"}`, plus `Retry-After: 1` (the mock's code is in `../apps/24a/erp_mock.py`). Each retry uses up the time you were trying to save. Raise the calls only while the refused count stays at zero: that is the `refused (429)` figure in the pace line. The recorded run had 0 refusals with 2 calls in flight. Ask the customer for a higher limit when refusals appear.

# %% [markdown]
# ## Production checklist
#
# - One stable key per unit of work, and an upsert on it. A replay must be safe with no extra step.
# - Partition by a stable hash (`crc32`, not `hash()`), and record the plan in a manifest with the input's checksum.
# - Size the calls in flight from the deadline (rate x latency), leave headroom, and stay under the API's limit.
# - Check pace in the same order every time: the results table, then the API's refusals, then the slots in use.
# - Reconcile each part before you say the run is done. Zero mismatches and zero duplicates are the only pass.
# - Keep the input copy and the manifest with the run, so a later question about a number has an answer.

# %% [markdown]
# ## Try it
#
# Write `calls_in_flight(orders, window_s, latency_ms)`: the fewest calls in flight that finish `orders` in `window_s` when each call takes `latency_ms`. Check it with 120 orders, an 8-second window and 150 ms: the answer should be 3. Hint: a fraction of a call is not possible, so which way do you round so the deadline still holds?

# %%
# your code here
def calls_in_flight(orders: int, window_s: float, latency_ms: float) -> int:
    """The fewest calls in flight that meet the deadline."""
    return 0


print(calls_in_flight(120, 8, 150))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def calls_in_flight(orders: int, window_s: float, latency_ms: float) -> int:
    """The fewest calls in flight that meet the deadline."""
    return math.ceil(orders / window_s * latency_ms / 1000)


print(calls_in_flight(120, 8, 150))

# %% [markdown]
# ## Tear down
#
# The customer API and the nodes stop, and their network goes with them. The run folder stays, with the manifest, the results table and the progress files, so you can reconcile it again.

# %% tags=["needs-docker"]
down = compose_run("down", "--remove-orphans")
print("stack removed, exit code:", down.returncode)

# %% [markdown]
# Save what this run printed, next to the run's files.

# %%
(RUN_DIR / "captured.json").write_text(json.dumps(CAPTURED, indent=2))
print("saved this run's output:", bool(CAPTURED))

# %% [markdown]
# ## Recap
#
# - Split the batch into parts by a stable hash; each node owns some parts.
# - Size the calls in flight from the deadline (Little's law: rate x latency), under the API's limit.
# - Upsert every write on `(order_id, run_id)`: a replay writes nothing new.
# - Reconcile each part against the manifest before the run counts as done.
# - When the run falls behind, check pace, refusals, then slots, and change one thing.
#
# **Interview:** "A nightly job must process 1.2 million orders in six hours and must survive a crash. How do you run it?" Strong answer: "I size the calls in flight from rate times latency, split the orders into parts by a stable hash over two nodes, and upsert each result on order and run id so a restart skips what is done. A manifest gives the expected count per part, and I reconcile before I call the run finished."
