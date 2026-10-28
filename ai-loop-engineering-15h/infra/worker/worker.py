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
