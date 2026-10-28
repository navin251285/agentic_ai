# %% [markdown]
# # 28b · A worker fleet in Docker Compose: scale, lease expiry and the drill
# Level L6 · Part 4 · core · ~25 min · builds on 28a, 26b
#
# ## Goal
# Start a Postgres queue and three workers with `docker compose up --scale worker=3`. Kill one worker while it holds a finding, let its lease expire, and show which limit breaks first: the provider's requests per minute. Scaling the workers does not raise that limit.
#
# ## Before you start
# - **Docker Engine and Docker Compose v2** on this machine, and about 1.5 GB of free RAM: the database has a 512 MB limit and each worker 256 MB. Run the next cell. If it reports a missing piece, follow `../SETUP_CLUSTERS.md`.
# - Port **10280** on 127.0.0.1 must be free. The lab database listens there.
# - No key is needed. The four model replies are recorded, so a rerun replays them. The Docker cells are tagged `needs-docker`: without Docker, the notebook prints the recorded output of a real run.

# %%
import shutil
print("docker:", shutil.which("docker") or "not found: the Docker cells will be skipped and the recorded output printed")

# %% [markdown]
# ## Why it matters
# Lesson 28a runs one worker in one process. A fleet means several workers, and a crashed worker must not strand its run. Without a fleet tool:
#
# | Without this | What goes wrong |
# |---|---|
# | Three terminals, three `python worker.py` commands | Nobody restarts a worker that dies. Nobody knows which three are up |
# | Each worker retries a 429 on its own schedule | Three workers retry together and hit the provider's limit again and again |
# | A dead worker's run stays `claimed` forever | The customer's refund waits until someone edits the database by hand |
#
# With Compose, one command starts the database and N workers, waits until they are healthy, and stops them with one `down`. The provider's limit stays the same number; more workers only wait for it. You do not need Compose for one worker.

# %% [markdown]
# ## The idea
# **Compose starts N copies of one worker container, and they share one Postgres queue. Each finding is claimed under a lease that a heartbeat renews. A killed worker stops renewing, so its lease expires and another worker takes the finding as attempt + 1. Every provider call counts against one limit for the whole project, and a worker that hits it waits with backoff and jitter.**
#
# Analogy: a bakery has several ovens, one order board and a gas meter with a fixed allowance per minute. Adding ovens does not add gas, and an oven that goes silent loses its order slip to another oven.

# %% [markdown]
# ## Picture
# The fleet, the heartbeat and the shared limit. Every worker talks to the same database, and the provider check is one row count in that database.
#
# ```mermaid
# flowchart LR
#   S["Heartbeat scan"] -->|writes findings| Q[("Postgres: inbox, leases, provider calls")]
#   W1["worker 1"] -->|claim with SKIP LOCKED| Q
#   W2["worker 2"] -->|claim with SKIP LOCKED| Q
#   W3["worker 3"] -->|claim with SKIP LOCKED| Q
#   W1 -->|provider call: limit shared| Q
#   W2 -->|provider call: limit shared| Q
#   W3 -->|provider call: limit shared| Q
#   W2 -.->|killed: no heartbeat, lease expires| Q
#   W1 -->|takeover: attempt 2| Q
# ```

# %% [markdown]
# ## Step by step
# 1. Set up the lab settings and the four findings, then the model writes one refund proposal per finding (4 model calls, recorded).
# 2. Write the worker and the Compose file. The worker is one file that the containers run and the notebook imports.
# 3. Start the database, wait until it is healthy, and create the tables.
# 4. Run the heartbeat scan: it writes the findings into the inbox.
# 5. Run the fleet with one worker, then with three. Compare the 429s and the time to drain.
# 6. The drill: kill the worker that holds a finding. Watch the lease expire and the takeover.
# 7. The stale worker wakes up and tries to write. The write is refused.

# %% [markdown]
# ### Step 1: the setup and the model proposals
# The desk has four refund requests. The inbox in this lesson stands in for the triage inbox of a support desk: each row is one finding. The lab provider is a table that counts requests and answers 429 past the limit. Only the four proposals in step 1 call a real model. Its limit is 3 requests per 10 seconds for the whole project. The lab settings are small on purpose, so that the drill fits in a lesson. A real provider limit is per model and per project and is shown in AI Studio.

# %%
import json, os, shutil, subprocess, sys, time
from pathlib import Path

import psycopg
sys.path.insert(0, "..")
import llm_replay
llm_replay.start("28b_worker-fleet-compose")  # records the model calls once, replays them later

import tut_env
from tut_env import env
tut_env.load()  # sets the .env values (or the lab defaults in .env.example) in os.environ

DATA = Path("../data/28b").resolve()  # run-time files only
WORK = DATA / "work"                  # one folder per finding, mounted into every worker
COMPOSE_FILE = Path("../infra/compose/worker-fleet.yml").resolve()
COMPOSE_NAME = "tut-ai-loop-engineering-15h-28b"  # the Compose project name: no other course uses it
PG_PORT = 10280                       # this lesson's port, bound to 127.0.0.1
LLM_LIMIT, LLM_WINDOW_S = int(env("LLM_LIMIT")), float(env("LLM_WINDOW_S"))  # lab provider: 3 requests per 10 s
LEASE_TTL_S, HEARTBEAT_S, WORK_S = float(env("LEASE_TTL_S")), float(env("HEARTBEAT_S")), float(env("WORK_S"))
FLEET_UP = False  # set to True by the cell that starts the database
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)
print("lab settings: LEASE_TTL_S", LEASE_TTL_S, "| HEARTBEAT_S", HEARTBEAT_S, "| WORK_S", WORK_S)

# %% [markdown]
# The four findings are invented for the course. Each one is a row in the triage inbox: a refund request with the order it names.

# %%
FINDINGS = [
    {"customer": "C-17", "order": "BS-1042", "paid": 120.0,
     "text": "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."},
    {"customer": "C-21", "order": "BS-1057", "paid": 80.0,
     "text": "Customer C-21 says the rain jacket from order BS-1057 has a broken zip. Order BS-1057 paid 80 USD."},
    {"customer": "C-30", "order": "BS-1063", "paid": 45.0,
     "text": "Customer C-30 says the water bottle from order BS-1063 leaks. Order BS-1063 paid 45 USD."},
    {"customer": "C-44", "order": "BS-1071", "paid": 150.0,
     "text": "Customer C-44 says the hiking boots from order BS-1071 have a sole that peels off. Order BS-1071 paid 150 USD."},
]

# %% [markdown]
# The model writes one proposal per finding, using the same tool shape as lesson 26b. The tool does not run: the worker does the write. Four model calls in total. The cell is tagged `needs-llm`, so a rerun replays the recording.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    raise NotImplementedError("the worker runs the write itself")

SYSTEM = ("You are the support desk for Brightside Outfitters. Refund what was paid for a damaged item, "
          "by calling issue_refund once. Never refund more than was paid.")
desk = get_llm().bind_tools([issue_refund])
PROPOSALS = {}
for f in FINDINGS:
    call = desk.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=f["text"])]).tool_calls[0]
    PROPOSALS[f["customer"]] = {"order_id": call["args"]["order_id"], "amount_usd": float(call["args"]["amount_usd"])}
(DATA / "proposals.json").write_text(json.dumps(PROPOSALS))
print("model proposals:", PROPOSALS, "| model calls: 4")

# %% [markdown]
# ### Step 2: the worker, the image and the Compose file
# The worker is one Python file. The container runs it, and the notebook imports the same file to call one function. The file is written in two cells. The first holds the settings, the queue claim and the provider call.
#
# `SKIP LOCKED` lets two workers claim at the same time without waiting for each other. Each one skips the row the other has locked. The claim and the lease start are one transaction.

# %%
%%writefile ../infra/worker/worker.py
"""Fleet worker for lesson 28b: claims a finding under a lease, asks the lab provider, writes one refund."""
import json, os, socket, threading, time
from pathlib import Path
import psycopg
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

LEASE_TTL_S = float(os.environ["LEASE_TTL_S"])   # set by Compose from the notebook; with the lab settings the lease lasts 4 heartbeats
HEARTBEAT_S = float(os.environ["HEARTBEAT_S"])
LLM_LIMIT = int(os.environ["LLM_LIMIT"])         # requests per window, shared by the whole project
LLM_WINDOW_S = float(os.environ["LLM_WINDOW_S"])
WORK_S = float(os.environ["WORK_S"])             # how long the desk spends on one finding
WORK_DIR = Path("/work")                         # the bind mount: one folder per finding
MAX_TRIES = 20

class RateLimited(Exception):  # the lab provider's HTTP 429
    pass

def connect():  # libpq reads PGHOST, PGUSER, PGPASSWORD and PGDATABASE from the environment
    return psycopg.connect(autocommit=True)

def claim(conn, owner):  # the oldest new finding, or one whose lease ran out
    with conn.transaction():
        row = conn.execute("""select id, attempt from inbox
            where status = 'new' or (status = 'claimed' and lease_expires_at < now())
            order by id for update skip locked limit 1""").fetchone()
        if row is None:
            return None
        conn.execute("""update inbox set status = 'claimed', owner = %s, attempt = attempt + 1,
            lease_expires_at = now() + make_interval(secs => %s) where id = %s""", (owner, LEASE_TTL_S, row[0]))
    return row[0], row[1] + 1

def call_provider(conn, owner, finding):  # one request against the project-wide limit: a 200, or a 429
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(28)")  # one count-and-record at a time, across all workers
        used = conn.execute("""select count(*) from provider_calls where code = 200
            and ts > now() - make_interval(secs => %s)""", (LLM_WINDOW_S,)).fetchone()[0]
        code = 429 if used >= LLM_LIMIT else 200
        conn.execute("insert into provider_calls (owner, finding, code) values (%s, %s, %s)", (owner, finding, code))
    if code == 429:
        raise RateLimited(f"HTTP 429: {used} requests in the last {LLM_WINDOW_S:g} s, limit {LLM_LIMIT}")
    return float(conn.execute("select proposal_usd from inbox where id = %s", (finding,)).fetchone()[0])

def log_wait(state):  # tenacity calls this before each wait
    print(f"  {state.args[1]}: finding {state.args[2]}: {state.outcome.exception()}; "
          f"retry in {state.next_action.sleep:.1f} s", flush=True)

# exponential backoff with full jitter (a random wait up to 0.5, 1, 2, 4 s, capped at 4 s), then give up
@retry(retry=retry_if_exception_type(RateLimited), wait=wait_random_exponential(multiplier=0.5, max=4),
       stop=stop_after_attempt(MAX_TRIES), before_sleep=log_wait, reraise=True)
def ask_provider(conn, owner, finding):
    return call_provider(conn, owner, finding)

# %% [markdown]
# The second cell holds the heartbeat, the fenced write and the loop. The heartbeat thread writes the worker's health row and renews the lease of the finding this worker holds. The fenced write checks the lease in the same transaction as the refund.

# %%
%%writefile -a ../infra/worker/worker.py

def beat(owner, state, stop):  # a heartbeat thread: the health row, and the lease of the finding this worker holds
    conn = connect()
    while not stop.is_set():
        conn.execute("""insert into workers (owner, seen_at) values (%s, now())
            on conflict (owner) do update set seen_at = now()""", (owner,))
        if state.get("finding") is not None:
            moved = conn.execute("""update inbox set lease_expires_at = now() + make_interval(secs => %s)
                where id = %s and owner = %s and attempt = %s and status = 'claimed'""",
                (LEASE_TTL_S, state["finding"], owner, state["attempt"])).rowcount
            if moved == 0:
                state["lost"] = True  # another worker took the finding: stop working on it
        stop.wait(HEARTBEAT_S)

def write_refund(conn, finding, owner, attempt, amount):  # fenced: counts only while this worker holds the lease
    with conn.transaction():
        held = conn.execute("""select 1 from inbox where id = %s and owner = %s and attempt = %s
            and status = 'claimed' and lease_expires_at > now() for update""", (finding, owner, attempt)).fetchone()
        if held is None:
            return "refused"
        new = conn.execute("""insert into ledger (finding, amount_usd, attempt, owner) values (%s, %s, %s, %s)
            on conflict (finding) do nothing""", (finding, amount, attempt, owner)).rowcount
        conn.execute("update inbox set status = 'done' where id = %s", (finding,))
    return "written" if new else "duplicate"

def process(conn, owner, state, finding, attempt):
    folder = WORK_DIR / f"finding-{finding}"  # one folder per finding, like one git worktree per finding (lesson 21)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        proposal = ask_provider(conn, owner, finding)
    except RateLimited:  # too many 429s: give the finding back to the inbox
        conn.execute("update inbox set status = 'new', owner = null where id = %s and owner = %s", (finding, owner))
        return "released after 20 x 429"
    time.sleep(WORK_S)  # the desk checks the order in the folder
    if state.get("lost"):
        return "lease lost, nothing written"
    (folder / "proposal.json").write_text(json.dumps({"finding": finding, "attempt": attempt, "amount_usd": proposal}))
    return write_refund(conn, finding, owner, attempt, proposal)

def main():
    owner = socket.gethostname()  # in a container this is the container id, so the notebook can match owner to container
    conn, state, stop = connect(), {}, threading.Event()
    threading.Thread(target=beat, args=(owner, state, stop), daemon=True).start()
    print(f"{owner}: up", flush=True)
    while True:
        got = claim(conn, owner)
        if got is None:
            time.sleep(0.5)
            continue
        finding, attempt = got
        state.update(finding=finding, attempt=attempt, lost=False)
        print(f"{owner}: finding {finding}, attempt {attempt}", flush=True)
        outcome = process(conn, owner, state, finding, attempt)
        state.update(finding=None)
        print(f"{owner}: finding {finding} -> {outcome}", flush=True)

if __name__ == "__main__":
    main()

# %% [markdown]
# The image pins the Python patch version and the driver version. The Compose file reads every setting from the environment, so no password is typed into a file. The database publishes one port on 127.0.0.1. The workers publish none: a scaled service cannot share one fixed host port.

# %%
%%writefile ../infra/worker/Dockerfile
# Worker image for lesson 28b. Pinned base image and library versions (never latest).
FROM python:3.12.16-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.3.6" "tenacity==9.1.4"
WORKDIR /app
COPY worker.py .
CMD ["python", "-u", "worker.py"]

# %% [markdown]
# The Compose file names the two services. `db` has a healthcheck. Each `worker` waits for a healthy `db`, mounts the work folder, and gets its settings from the environment. Scaling it is one flag, not a copy of the file.

# %%
%%writefile ../infra/compose/worker-fleet.yml
# Lesson 28b: a Postgres queue and a scaled fleet of workers. The notebook starts it with
#   docker compose -p tut-ai-loop-engineering-15h-28b -f ../infra/compose/worker-fleet.yml up -d --wait --scale worker=3
# Every value comes from the notebook's environment (tut_env.load()); no password is written here.
services:
  db:
    image: postgres:18-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "127.0.0.1:${FLEET_PG_PORT}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 2s
      timeout: 3s
      retries: 20
    mem_limit: 512m
  worker:
    build: ../worker
    depends_on:
      db:
        condition: service_healthy
    user: "${FLEET_UID}:${FLEET_GID}"
    environment:
      PGHOST: db
      PGUSER: ${POSTGRES_USER}
      PGPASSWORD: ${POSTGRES_PASSWORD}
      PGDATABASE: ${POSTGRES_DB}
      LEASE_TTL_S: ${LEASE_TTL_S}
      HEARTBEAT_S: ${HEARTBEAT_S}
      LLM_LIMIT: ${LLM_LIMIT}
      LLM_WINDOW_S: ${LLM_WINDOW_S}
      WORK_S: ${WORK_S}
    volumes:
      - ${FLEET_WORK_DIR}:/work
    mem_limit: 256m

# %% [markdown]
# ### Step 3: start the database and wait until it is healthy
# `up --wait` returns when the healthcheck passes, so no fixed sleep is needed. The host connects to the same database through 127.0.0.1:10280 and creates the tables. The queue is the table `inbox`. `ledger` has one row per finding, and its key makes a repeated refund a no-op. `provider_calls` is the provider's log: every request, with its code.

# %%
def fleet_env():  # the environment for Compose: lab settings and paths. Nothing here is printed.
    e = dict(os.environ)
    e.update(POSTGRES_USER=env("POSTGRES_USER"), POSTGRES_PASSWORD=env("POSTGRES_PASSWORD"),
             POSTGRES_DB=env("POSTGRES_DB"), FLEET_PG_PORT=str(PG_PORT), FLEET_WORK_DIR=str(WORK),
             FLEET_UID=str(os.getuid()), FLEET_GID=str(os.getgid()), LEASE_TTL_S=str(LEASE_TTL_S),
             HEARTBEAT_S=str(HEARTBEAT_S), LLM_LIMIT=str(LLM_LIMIT), LLM_WINDOW_S=str(LLM_WINDOW_S), WORK_S=str(WORK_S))
    return e

def compose(*args, check=True):  # one docker compose command for this lesson's project
    r = subprocess.run(["docker", "compose", "-p", COMPOSE_NAME, "-f", str(COMPOSE_FILE), *args],
                       env=fleet_env(), capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError("docker compose failed: " + r.stderr[-600:])
    return r.stdout

# %% [markdown]
# The schema: `inbox` is the queue, `ledger` has one row per finding, and `provider_calls` is the provider's log. Nothing here calls a model.

# %%
SCHEMA = """
drop table if exists inbox, ledger, provider_calls, workers;
create table inbox (
  id serial primary key,
  customer text not null, order_id text not null, paid_usd numeric not null, request text not null,
  proposal_usd numeric not null,                     -- the refund the desk proposed (the recorded model reply)
  status text not null default 'new',                -- new, claimed, done
  owner text, attempt int not null default 0, lease_expires_at timestamptz
);
create table ledger (finding int primary key, amount_usd numeric not null, attempt int not null, owner text);
create table provider_calls (ts timestamptz not null default now(), owner text, finding int, code int not null);
create table workers (owner text primary key, seen_at timestamptz not null default now());
"""

# %% [markdown]
# Start Postgres and wait for its healthcheck. The host then connects through 127.0.0.1 and creates the tables.

# %% tags=["needs-docker"]
compose("up", "-d", "--build", "--wait", "db")  # starts Postgres and waits for its healthcheck
db = psycopg.connect(host="127.0.0.1", port=PG_PORT, user=env("POSTGRES_USER"),
                     password=env("POSTGRES_PASSWORD"), dbname=env("POSTGRES_DB"), autocommit=True)
db.execute(SCHEMA)
FLEET_UP = True
print("database healthy on 127.0.0.1:%d | tables: %s" % (PG_PORT, [r[0] for r in db.execute(
    "select tablename from pg_tables where schemaname = 'public' order by 1").fetchall()]))

# %% [markdown]
# ### Step 4: the heartbeat scan writes the inbox
# A scheduled heartbeat (lesson 20) wakes up, looks for work, and writes it into the inbox. It does not do the work. The workers take the rows. `seed_inbox()` is that scan: it resets the inbox for one experiment and writes the four findings with the proposals from step 1. The helper functions below are shared by the experiments and the drill.

# %%
def q(sql, args=()):  # rows from the lab database
    return db.execute(sql, args).fetchall()

def scalar(sql, args=()):
    return q(sql, args)[0][0]

def wait_until(cond, timeout=60.0, step=0.2):  # a poll with a timeout, never a fixed sleep
    t0 = time.time()
    while not cond():
        assert time.time() - t0 < timeout, "timed out waiting for the fleet"
        time.sleep(step)

DONE = "select count(*) from inbox where status = 'done'"

def fleet_size():  # workers whose heartbeat is fresh: the fleet's health check
    return scalar("select count(*) from workers where seen_at > now() - interval '3 seconds'")

def seed_inbox():  # the heartbeat scan: a fresh inbox, one row per finding
    db.execute("truncate inbox, ledger, provider_calls restart identity")
    for f in FINDINGS:
        db.execute("insert into inbox (customer, order_id, paid_usd, request, proposal_usd) values (%s, %s, %s, %s, %s)",
                   (f["customer"], f["order"], f["paid"], f["text"], PROPOSALS[f["customer"]]["amount_usd"]))
    print("inbox:", scalar("select count(*) from inbox"), "findings, all new")

# %% [markdown]
# One printout serves both the live run and the recorded output, so the two read the same.

# %%
def show_table(rows):  # the same printout for a live run and for the recorded output
    print(f"{'workers':>7} {'drain s':>8} {'ok':>4} {'429s':>5} {'first 429 after s':>18} {'refund rows':>12} {'claimers':>9}")
    for r in rows:
        print(f"{r['workers']:>7} {r['drain_s']:>8} {r['requests_ok']:>4} {r['requests_429']:>5} "
              f"{str(r['first_429_after_s']):>18} {r['refund_rows']:>12} {r['workers_that_claimed']:>9}")

# %% [markdown]
# ### Step 5: one worker, then three
# `run_fleet(n)` scales the fleet to `n` workers, waits until all of them report a heartbeat, seeds the inbox and waits until every finding is done. Then it measures. The 429s are the provider's answers. The first 429 is counted from the first request of the run.

# %% tags=["needs-docker"]
def run_fleet(scale):
    compose("up", "-d", "--build", "--wait", "--scale", f"worker={scale}")
    wait_until(lambda: fleet_size() == scale)
    seed_inbox()
    t0 = time.time()
    wait_until(lambda: scalar(DONE) == len(FINDINGS), timeout=240)
    secs = time.time() - t0
    first = scalar("select extract(epoch from min(ts)) from provider_calls")
    first429 = scalar("select extract(epoch from min(ts)) from provider_calls where code = 429")
    return {"workers": scale, "drain_s": round(secs, 1),
            "requests_ok": scalar("select count(*) from provider_calls where code = 200"),
            "requests_429": scalar("select count(*) from provider_calls where code = 429"),
            "first_429_after_s": round(float(first429) - float(first), 1) if first429 is not None else None,
            "refund_rows": scalar("select count(*) from ledger"),
            "workers_that_claimed": scalar("select count(distinct owner) from inbox")}

if FLEET_UP:
    rows = [run_fleet(n) for n in (1, 3)]
    show_table(rows)
    print("the provider allows", LLM_LIMIT, "requests per", LLM_WINDOW_S, "s for the whole project")

# %% [markdown]
# Read the table. In the recorded run both runs drained in about the same time: 14.3 s with one worker and 13.5 s with three. A live run will differ by a few seconds, but three workers still finish no sooner than one. With one worker, the fourth request lands at about 9 s, inside the 10 s window of the first three, so it gets a 429. With three workers, the first three asks land at once, and the fourth finding's ask, about 3 s later, is refused. The limit sets the speed: three requests per window, whatever the number of workers. A 429 costs time, not a refund, because the lease and the ledger keep the write to one.

# %% [markdown]
# ### Step 6: the drill, kill a worker while it holds a finding
# Three workers. Once finding 2 is claimed, we kill the container that holds it, with `docker kill`. This is a hard stop, like a crashed process. The worker does not clean up. Its heartbeat stops. The lease runs out after `LEASE_TTL_S`, and another worker takes the finding with attempt 2.

# %% tags=["needs-docker"]
def container_of(owner):  # the owner is the container id's first 12 characters (the container hostname)
    ids = compose("ps", "-q", "worker").split()
    return next(c for c in ids if c.startswith(owner))

if FLEET_UP:
    compose("up", "-d", "--wait", "--scale", "worker=3")
    wait_until(lambda: fleet_size() == 3)
    seed_inbox()
    wait_until(lambda: scalar("select count(*) from inbox where id = 2 and status = 'claimed'") == 1)
    owner, attempt = q("select owner, attempt from inbox where id = 2")[0]
    print("finding 2 is held by", owner[:12], "attempt", attempt, "| ledger rows now:",
          scalar("select count(*) from ledger where finding = 2"))
    subprocess.run(["docker", "kill", container_of(owner)], check=True, capture_output=True)
    print("killed the worker; its heartbeat stops")
    wait_until(lambda: scalar(DONE) == len(FINDINGS), timeout=240)
    new_owner, new_attempt = q("select owner, attempt from inbox where id = 2")[0]
    print("takeover:", new_owner[:12], "attempt", new_attempt, "| refund rows for finding 2:",
          scalar("select count(*) from ledger where finding = 2"))

# %% [markdown]
# ### Step 7: the stale worker wakes up
# A worker that only paused, a frozen VM for example, comes back with its old attempt and tries to write. The write checks the owner, the attempt and the lease in one transaction. It is refused, and the ledger does not change. The notebook calls the same function the containers run, from the same file: the settings in that file come from `os.environ`, where `tut_env.load()` put them in step 1.

# %% tags=["needs-docker"]
if FLEET_UP:
    import importlib.util
    # worker.py reads LEASE_TTL_S and the other settings from os.environ when it is imported
    spec = importlib.util.spec_from_file_location("worker", COMPOSE_FILE.parent.parent / "worker" / "worker.py")
    w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)  # the file the containers run
    amount = float(scalar("select proposal_usd from inbox where id = 2"))
    stale = w.write_refund(db, 2, owner, 1, amount)  # the old owner with attempt 1
    print("the killed worker wakes up with attempt 1:", stale)
    print("refund rows for finding 2 after the stale write:", scalar("select count(*) from ledger where finding = 2"))

# %% [markdown]
# **No Docker on this machine?** The cells above are skipped and nothing is made up. This cell prints the recorded output of a real run of this notebook, labelled as such.

# %%
if not FLEET_UP:
    rec = json.loads(Path("../data/recorded/28b.json").read_text())
    print("recorded output (a real run of this notebook with Docker; not produced in this session)")
    show_table(rec["experiments"])
    print("drill:", rec["drill"])
    print("the provider allows", rec["lab"]["llm_limit"], "requests per", rec["lab"]["llm_window_s"], "s for the whole project")

# %% [markdown]
# ## At real scale
# - **Your provider's limit sets the speed.** Gemini limits apply per project: requests per minute, tokens per minute and requests per day. Your model's numbers are in AI Studio. The lab's 3 per 10 s is a stand-in. Size the fleet to the limit, not the reverse.
# - **Share the budget, not the worker.** One counter, in Postgres or Redis, or a gateway (lesson 29a), counts every request. A per-worker counter lets three workers send nine requests into a window of three.
# - **Compose is one host.** A machine failure stops the fleet. Several hosts need an orchestrator (Kubernetes is a separate course) and a managed Postgres with failover (lessons 26a, 29b).
# - **A lease is only as good as its heartbeat.** Keep the TTL above three heartbeats, and keep the fenced write, so a long pause cannot write twice.

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One worker keeps up with the provider's limit | One process, no fleet | Extra workers only wait at the limit |
# | Many workers, one host, a laptop or a lab | Compose with `--scale` and `--wait` | One command, health checks, one `down` |
# | Workers on several hosts or a host failure must not stop the fleet | An orchestrator and managed Postgres | Compose runs on one machine only |
# | A retry from many workers | Backoff with jitter, and one budget counter | Fixed retries from every worker collide again |
# | A worker dies holding a finding | A lease with a heartbeat, the next attempt number and a fenced write | The finding moves on, and the old worker cannot write |

# %% [markdown]
# ## What just happened
# With one worker and with three, the provider's limit set the speed of the run, and the 429s came from the shared limit, not from the database. The drill killed the worker that held finding 2. Its lease ran out, another worker took it as attempt 2, and the ledger holds one refund for that finding. The stale attempt was refused.

# %% [markdown]
# ## Common mistakes
# The easy mistake is a limit counter inside each worker. Each worker then allows its own three requests, and three workers send nine into one window. This cell is arithmetic, not a fleet run: it shows the count that goes wrong. The assert fails, which is the expected result.

# %% tags=["raises-exception"]
per_worker_limit = LLM_LIMIT   # each worker counts only its own requests
workers_running = 3
sent_in_window = workers_running * per_worker_limit  # 9 requests into a window of 3
assert sent_in_window <= LLM_LIMIT, f"expected 429s: {sent_in_window} requests against a limit of {LLM_LIMIT}"

# %% [markdown]
# The fix is one counter that every worker shares, as in `call_provider()`. Under one advisory lock, the count and the insert are one step.

# %% [markdown]
# ## Try it
# Write `refunds_per_finding()` that returns a dict from finding id to the number of ledger rows for that finding. After a good drill, every value is 1. Use `q()`. Needs the Docker run; without Docker, read the answer.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def refunds_per_finding():
    return {finding: n for finding, n in q("select finding, count(*) from ledger group by finding order by finding")}

if FLEET_UP:
    print(refunds_per_finding())  # {1: 1, 2: 1, 3: 1, 4: 1}
else:
    print("no fleet in this session: the recorded output above shows one refund row per finding")

# %% [markdown]
# The last Docker cell stops the fleet, the database and its volume. It runs even when the drill cells were skipped. Then the recording is saved.

# %% tags=["needs-docker"]
if FLEET_UP:
    db.close()
    compose("down", "-v", "--remove-orphans")  # stops the workers and Postgres and removes the lab volume
    FLEET_UP = False
    print("fleet stopped")

# %% [markdown]
# The recording is saved last, after every model call of the lesson.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Key terms
# - **Compose `--scale`** — starts N copies of one service; `--wait` returns when they report healthy.
# - **heartbeat** — the worker's regular write that shows it is alive and renews its lease (lesson 20).
# - **lease takeover** — when a lease expires, the next worker claims the finding with attempt + 1 (lesson 26b).
# - **fenced write** — a write that checks owner, attempt and lease in one transaction (lesson 26b).
# - **RPM** — requests per minute, one of the provider's limits; this lesson uses a 10-second lab window.
# - **backoff with jitter** — a random wait that grows after each 429, so workers do not retry together.
# - **triage inbox** — the table of findings that a heartbeat scan writes and workers take.
#
# **Interview:** How do you scale workers under a provider rate limit? Strong answer: more workers do not raise a per-project limit. Count requests in one shared place, back off with jitter on a 429, and claim work under leases with fenced writes.
