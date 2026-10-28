# %% [markdown]
# # 20 · Triggers: cron, events and heartbeats with leases
# Level L5 · Part 3 · core · ~20 min · builds on 12, 19
#
# ## Goal
# Start a run from a schedule (a heartbeat) and from an event (a new ticket), then stop two runs from taking the same task: a lease expires when its worker stops renewing it, and a stale worker cannot write after it has lost the lease.
#
# ## Why it matters
# Lesson 19's desk loop still needs a starter: a timer, a webhook or a queue. Without a key per task and a lease:
#
# | Without a key and a lease | What goes wrong |
# |---|---|
# | The timer and the webhook both start a run for BO-2207 | Two runs answer the same customer |
# | Two workers read "free" at the same moment | Both claim the task |
# | A worker dies halfway through | The task stays taken forever, or a new worker repeats the refund |
# | A worker wakes after a long pause, still sure it owns the task | It overwrites the work of the worker that took over |
#
# With a key per task, a claim that sets an owner and an expiry, and a write that checks both, each task has one owner at a time. You do not need this for one run you start by hand.

# %% [markdown]
# ## The idea
# **A trigger only starts work; it does not decide who does it. A heartbeat is a timer that wakes the loop on a beat and scans for work. An event is a push, such as a webhook. Both write a task keyed by the ticket id, so a repeat adds nothing. A worker takes a task by writing a lease: an owner, an attempt number and an expiry time. It renews the lease on a short beat while it works. If renewals stop, the lease expires and another worker takes the task with a higher attempt. Every side effect checks the owner and attempt in the same transaction, so a stale worker is refused.**
#
# Analogy: a hotel's housekeeping board. The morning round and the doorbell both list a room once. A housekeeper signs for a room and renews the sign while cleaning. If the renewals stop, the room returns to the pool.

# %% [markdown]
# ## Picture
# Two triggers feed one table. Worker C stops renewing its lease, so worker D takes the task with attempt 2. Worker C's late write is refused.
#
# ```mermaid
# flowchart LR
#   T["Heartbeat: cron tick every 15 min"] --> I["Tasks table: one row per ticket"]
#   E["Event: webhook for a new ticket"] --> I
#   I --> C["Worker C claims, attempt 1, then stops renewing"]
#   I --> D["Worker D claims after expiry, attempt 2"]
#   C -. "late reply: lease lost, refused" .-> O["Outbox: one reply per ticket"]
#   D --> O
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the tables and a peek at the inbox (no model call)
# The inbox is a generated list of ticket ids; a real desk would get them from its ticket system. The state lives in SQLite, a file, so a new process reads it. Each statement commits on its own (`isolation_level=None`), so a transaction is written only where the code asks for one.

# %%
import shutil
import sqlite3
from pathlib import Path

ROOT = Path("../data/20")                  # run-time files only: the SQLite databases
shutil.rmtree(ROOT, ignore_errors=True)    # a clean start each time this notebook runs
ROOT.mkdir(parents=True)
INBOX = [f"BO-{n}" for n in range(2201, 2207)]  # six generated tickets already waiting

def open_db(path=ROOT / "triage.db"):
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("create table if not exists tasks (ticket text primary key, status text default 'open', "
               "owner text, attempt integer default 0, lease_until real default 0)")
    db.execute("create table if not exists outbox (ticket text primary key, attempt integer, reply text)")
    return db

db = open_db()
print("inbox peek:", INBOX[:3], "... total", len(INBOX))

# %% [markdown]
# ### Step 2: a heartbeat and a webhook feed the same table (no model call)
# The heartbeat is a cron tick. The lesson uses a 900 s scan beat, as `*/15 * * * *` would fire. Each scan rescans the whole inbox. The key makes a rescan harmless: a ticket that is already a task adds nothing. The webhook is an event for one new ticket. Both write with `insert or ignore` on the ticket id, so the second trigger for the same ticket adds nothing.
#
# No real timer runs in this notebook. We call `heartbeat` and `webhook` at the times a timer or a webhook would fire, and the clock is a number we pass in (seconds since t=0).

# %%
LEASE_S = 90   # a lease lasts 90 s; each renewal gives it 90 s more
RENEW_S = 30   # the worker's renewal beat: it renews every 30 s, so the TTL is 3 x this beat
BEAT_S = 900   # the scan beat: the cron tick, 15 minutes between heartbeat scans

def heartbeat(db):  # cron tick: add each ticket that is not a task yet
    return sum(db.execute("insert or ignore into tasks (ticket) values (?)", (t,)).rowcount for t in INBOX)

def webhook(db, ticket):  # event: a new ticket arrives and triggers at once
    INBOX.append(ticket)  # also lists the ticket in INBOX, so the later heartbeat scan sees BO-2207
    return db.execute("insert or ignore into tasks (ticket) values (?)", (ticket,)).rowcount

print("t=0    heartbeat adds:", heartbeat(db))
print("t=10   webhook BO-2207 adds:", webhook(db, "BO-2207"))
print(f"t={BEAT_S}  next heartbeat adds:", heartbeat(db), "(the tickets are already tasks)")

# %% [markdown]
# ### Step 3: the lease, by hand (no model call)
# No library in this course's stack gives a lease on a laptop queue, so the lease is written here, about 30 lines. This is the `why` reason of the lesson. The clock is fake: `now` is a number the caller passes in, not `time.time()`, so every run prints the same result.
#
# A claim is one write transaction. `begin immediate` takes the write lock before the read. With `isolation_level=None` the code opens and closes each transaction itself. A renewal works only while the worker still holds the lease. The side effect, `send_reply`, checks the lease in the same transaction and then writes once.

# %%
def claim(db, owner, now):  # one write transaction: take the first open or expired task
    db.execute("begin immediate")  # the write lock comes before the read, so no second worker reads the same row
    row = db.execute("select ticket from tasks where status = 'open' or (status = 'leased' and lease_until < ?) "
                     "order by ticket limit 1", (now,)).fetchone()
    if row:
        db.execute("update tasks set status = 'leased', owner = ?, lease_until = ?, attempt = attempt + 1 "
                   "where ticket = ?", (owner, now + LEASE_S, row[0]))
    db.execute("commit")
    return row[0] if row else None

def renew(db, ticket, owner, attempt, now):  # the worker's renewal: 1 row only while it still holds the lease
    return db.execute("update tasks set lease_until = ? where ticket = ? and owner = ? and attempt = ? "
                      "and status = 'leased' and lease_until >= ?",
                      (now + LEASE_S, ticket, owner, attempt, now)).rowcount

def send_reply(db, ticket, owner, attempt, now, text):  # the side effect: checks the lease, then writes once
    db.execute("begin immediate")
    held = db.execute("select 1 from tasks where ticket = ? and owner = ? and attempt = ? and status = 'leased' "
                      "and lease_until >= ?", (ticket, owner, attempt, now)).fetchone()
    if not held:
        db.execute("rollback")
        return "rejected: lease lost"
    sent = db.execute("insert or ignore into outbox values (?, ?, ?)", (ticket, attempt, text)).rowcount
    db.execute("update tasks set status = 'done' where ticket = ?", (ticket,))
    db.execute("commit")
    return "sent" if sent else "already sent"

# %% [markdown]
# ### Step 4: three workers claim, then two of them act (no model call)
# Three workers claim at t=0, and each lease runs to t=90. Worker A renews its lease on the 30 s renewal beat, so it renews at t=30 and t=60. Worker B replies and finishes at t=35. Worker C claims BO-2203 and then dies: it never renews.

# %%
print("t=0  A claims", claim(db, "worker-A", 0))                       # BO-2201, lease until 90
print("t=0  B claims", claim(db, "worker-B", 0))                       # BO-2202, lease until 90
print("t=0  C claims", claim(db, "worker-C", 0))                       # BO-2203, then C dies
print("t=30 A renews BO-2201:", renew(db, "BO-2201", "worker-A", 1, 30), "row")  # lease until 120
print("t=35 B replies:", send_reply(db, "BO-2202", "worker-B", 1, 35, "Your return label is attached."))
print("t=60 A renews BO-2201:", renew(db, "BO-2201", "worker-A", 1, 60), "row")  # lease until 150

# %% [markdown]
# ### Step 5: the crash drill (no model call)
# At t=100, C's lease (until 90) has expired. BO-2201 is still safe: its lease runs to t=150. Worker D claims BO-2203 as attempt 2. Then the dead worker C wakes up at t=102 and tries to reply. Its lease is gone, so the write is refused. D replies at t=105, and its reply goes out once. At t=110 D renews, but the task is done, so the renewal changes no row.

# %%
print("t=100 D claims", claim(db, "worker-D", 100))                    # BO-2203 again, attempt 2
print("t=102 zombie C replies:", send_reply(db, "BO-2203", "worker-C", 1, 102, "Refund of 40 units sent."))
print("t=105 D replies:", send_reply(db, "BO-2203", "worker-D", 2, 105, "Refund of 40 units sent to the card on file."))
print("t=110 D renews after its reply:", renew(db, "BO-2203", "worker-D", 2, 110), "rows")  # 0: the task is done

# %% [markdown]
# ### Step 6: read the state (no model call)
# A new process would read exactly these rows. BO-2201 is still A's: its lease runs to t=150, so nobody takes it before then. BO-2204 to BO-2207 are still open.

# %%
for ticket, status, owner, attempt in db.execute("select ticket, status, owner, attempt from tasks order by ticket"):
    print(f"{ticket}  {status:6s}  owner={owner}  attempt={attempt}")
print("outbox:", db.execute("select ticket, attempt, reply from outbox order by ticket").fetchall())

# %% [markdown]
# ## At work
# - **Claude Code `/loop` is a session timer.** Its recurring tasks expire after 7 days, and a laptop loop stops when the machine sleeps (Claude Code docs, checked 2026-10-26). Cloud routines have a one-hour minimum. → lesson 21.
# - **Heartbeat triage (Osmani's pattern).** A daily run reads failing CI jobs and open issues, writes findings to a state file, and starts one worktree and one sub-agent per finding. The key per finding stops a second trigger from starting the same fix. → lesson 21.
# - **Leases in production.** Postgres claims a row with `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL docs) and keeps owner, expiry and attempt on the row, with the TTL at least three times the renewal interval. A paused hosted schedule does not backfill missed triggers, so design the catch-up. → lesson 26a.
#
# Go deeper: Temporal schedules, GitHub Actions `schedule:`, and LangSmith cron with webhooks run the same pattern on hosted services.

# %% [markdown]
# ## Common mistakes
# Wrong: check, then write, in two steps. Two workers read the same open task before either one writes. The cell below uses two connections to show it. It is tagged to raise: it asserts that the two workers took different tasks, so the `AssertionError` prints. That failure is the point.

# %% tags=["raises-exception"]
naive = open_db(ROOT / "naive.db")
naive.execute("insert or ignore into tasks (ticket) values ('BO-9001')")          # one open task
a, b = open_db(ROOT / "naive.db"), open_db(ROOT / "naive.db")                     # two workers, two connections
got_a = a.execute("select ticket from tasks where status = 'open' order by ticket limit 1").fetchone()[0]
got_b = b.execute("select ticket from tasks where status = 'open' order by ticket limit 1").fetchone()[0]  # both read first
a.execute("update tasks set status = 'leased', owner = 'A' where ticket = ?", (got_a,))
b.execute("update tasks set status = 'leased', owner = 'B' where ticket = ?", (got_b,))
assert got_a != got_b, f"both workers took {got_a}; the last write owns it"  # AssertionError

# %% [markdown]
# Right: the claim is one write transaction (`begin immediate`), as in `claim` above. A second worker that asks for the write lock while the first one holds it gets `database is locked`, so it cannot take the same row. The cell below shows that with two connections. The same rule applies to a write: check the lease in the same transaction as the write.

# %%
first = open_db(ROOT / "lock.db")                                              # worker 1
second = sqlite3.connect(ROOT / "lock.db", isolation_level=None, timeout=0)    # worker 2: timeout=0 gives up at once
first.execute("begin immediate")                                               # worker 1 takes the write lock
try:
    second.execute("begin immediate")                                          # worker 2 asks for the same lock
except sqlite3.OperationalError as err:
    print("worker 2 while worker 1 holds the lock:", err)
first.execute("rollback")                                                      # worker 1 lets go
second.execute("begin immediate")                                              # worker 2 asks again
print("worker 2 after the rollback: lock taken")
second.rollback()                                                              # the connection's own rollback, no output

# %% [markdown]
# Wrong: a trigger that inserts without a key. A webhook that fires twice, or a heartbeat that runs during a webhook, makes two tasks. The fix is the primary key on the ticket with `insert or ignore`, as in Step 2.

# %% [markdown]
# ## Production checklist
# Before a scheduled loop runs unattended, check each line. A "no" means the run needs a person.
#
# - [ ] Every trigger writes its task with a stable key, so a repeat adds nothing.
# - [ ] A claim is one write transaction that sets the owner, the expiry and the attempt.
# - [ ] The lease TTL is at least three times the worker's renewal interval (`RENEW_S` in Step 2, not the 15-minute scan beat).
# - [ ] Every side effect checks the owner and attempt in the same transaction as the write.
# - [ ] A kill switch is read before every claim, so a stop takes effect on the next tick.
# - [ ] A refused write, a lost lease and a skipped duplicate each leave a row a person can read.

# %% [markdown]
# ## Try it
# Worker C was refused at t=102. Write a query that prints the outbox row for BO-2203 and the task row for BO-2203 (owner, attempt, status). Then answer: if `send_reply` had no lease check, which reply would the customer get, and why?

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
print("task:  ", db.execute("select ticket, owner, attempt, status from tasks where ticket = 'BO-2203'").fetchone())
print("outbox:", db.execute("select ticket, attempt, reply from outbox where ticket = 'BO-2203'").fetchall())
# Without the check, C's write at t=102 would land first, and "insert or ignore" keeps the first row.
# The customer would get C's reply (attempt 1), and D's reply would be ignored even though D held the lease.
# The lease check ties the write to who holds the lease now, not to who arrived first.

# %% [markdown]
# ## Recap
# - A trigger only starts work. A heartbeat (cron tick) and an event (webhook) both write one task per ticket id, so a repeat adds nothing.
# - A claim is one write transaction that sets an owner, an expiry and an attempt number. Two workers cannot take the same open task.
# - A worker keeps its task by renewing the lease. When the renewals stop, the lease expires and another worker takes the task with a higher attempt.
# - The side effect checks the lease in the same transaction as the write (a fencing check), so a stale worker's late reply is refused.
#
# **Interview:** How do you stop two runs of a scheduled agent from taking the same task? Strong answer: a stable key makes each trigger idempotent; a claim is one write transaction that sets owner, expiry and attempt; renewals are the heartbeat; each side effect checks the lease in the same transaction, so a paused worker cannot write.
