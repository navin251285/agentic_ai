# %% [markdown]
# # 17 · Runbooks and incident response for a customer deployment
#
# Level L3 · Part 2 · core · ~20 min · builds on 16
#
# Needs no Docker and no keys. The alert signals are the real output of lesson 16's run, saved in `../data/recorded/16.json`. The restore drill uses a SQLite file, which is part of Python's standard library, so it runs on a laptop.

# %% [markdown]
# ## Goal
#
# By the end you can write a runbook for each of the three most likely incidents of the Basket Bazaar triage service, and run a restore drill: restore the decisions backup to a scratch file, check it, time it against the recovery target, and only then put it live.

# %% [markdown]
# ## Why it matters
#
# At 2 a.m. the customer's ops analyst sees "triage is failing" and calls you. You built the system; they did not. Without a runbook they guess, restart things and may make it worse. Without a restore drill the backup is only a hope: it may be empty or broken, and you learn that during the outage.
#
# The next cell shows the backup problem with a file you would never test. It is plain Python. It also loads the recorded run of lesson 16, which the later steps use.

# %%
import json, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path("../data/17")  # this lesson's run-time files
DATA.mkdir(parents=True, exist_ok=True)
REC = json.loads(Path("../data/recorded/16.json").read_text())  # the real output of lesson 16's run
print("recorded run of lesson 16 loaded, keys:", sorted(REC))

bad = DATA / "backup-never-tested.db"
bad.write_bytes(b"this file has a size, but it is not a database")
try:
    sqlite3.connect(bad).execute("PRAGMA integrity_check")
except sqlite3.DatabaseError as err:
    print(f"the backup failed when we tried to use it: {err}")

# %% [markdown]
# - **Without a runbook:** each incident is solved from memory, by whoever is awake. The fix depends on who knows the system.
# - **Without a restore drill:** nobody knows whether the backup restores, or how long it takes.
# - **With both:** the on-call follows written steps, checks what they should see, and knows the recovery targets are met.
# - **When you don't need it:** a demo nobody depends on. A customer with live orders needs both.

# %% [markdown]
# ## The idea
#
# A **runbook** is a written procedure for one known incident: the alert, the first check, the **mitigation** (during an incident, the step that stops the harm, often a rollback), the check that proves it worked, and who to escalate to. An **incident** is a break in a service a customer relies on. You mitigate first and find the root cause later, in a **blameless postmortem** that asks what happened, not who.
#
# The **RPO** (how much data you may lose, counted back from the last backup) and the **RTO** (how long the service may be down) come from the customer's SLA. A **restore drill** tests the backup on purpose and records the real time it took. In this lab the RPO and RTO checks pass trivially, since the drill runs seconds after the backup; on real data they matter.
#
# Analogy: a fire drill. The map on the wall is the runbook; the restore drill is the drill itself.

# %% [markdown]
# ## Picture
#
# The alert starts the runbook. A backup taken before each release is what the restore drill tests.

# %% [markdown]
# ```mermaid
# flowchart LR
#     A[Alert fires] --> S[Severity and owner]
#     S --> R[Runbook: first check]
#     R --> M[Mitigate: roll back or restore]
#     M --> V[Verify: the runbook's check]
#     V --> P[Blameless postmortem]
#     B[Backup before each release] -.-> D[Restore drill to a scratch file] -.-> M
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the signals the alert uses
#
# Lesson 16 gave three signals: the histogram `triage_request_seconds`, a JSON log line per request with `duration_ms` and `trace_id`, and an `erp_error` line when the customer API fails. This cell reads the recorded run and applies a lab alert rule: one request in four or more takes over 1 s. The customer sets the real rule in the SLA.

# %%
print("a request line (order, status, label):", REC["requests"].splitlines()[0])
events = [json.loads(line) for line in REC["logs"].splitlines() if line.strip()]
slow = [e for e in events if e["duration_ms"] >= 1000]
metric = json.loads(REC["metric"])
share = metric["over_1s"] / metric["requests"]
print(f"log lines: {len(events)}, slow: {len(slow)}, every slow line has a trace_id: {all('trace_id' in e for e in slow)}")
print(f"metric: {metric['over_1s']:.0f} of {metric['requests']:.0f} requests over 1 s ({share:.0%})")
ALERT_SHARE = 0.25  # lab alert threshold, not a recommendation
print("alert fires:", share >= ALERT_SHARE)

# %% [markdown]
# ### Step 2: three runbooks
#
# The three most likely incidents for this service:
#
# 1. **Triage is slow.** Lesson 16's trace shows the time in the call to the customer API, not in triage.
# 2. **The customer API rejects triage's token.** Triage answers 502 and the logs show `erp_error` with a 401 or 403. The customer rotated a secret, or the account is locked (lesson 13).
# 3. **A bad release writes wrong labels.** The fix is a rollback to the last good image tag (lesson 14), then a restore of the decisions store from the backup taken before the release.
#
# The runbooks are data, so the notebook can check that every section is filled in.

# %%
SECTIONS = ["Symptom", "First check", "Mitigate", "Verify", "Escalate to"]
RUNBOOKS = {
    "1. Triage is slow": {
        "Symptom": "alert: more than 1 in 4 triage requests take over 1 s",
        "First check": "a slow log line and its trace_id; in the trace, the slowest span is the GET to the customer API",
        "Mitigate": "do not restart triage, it will not help, because the time is spent in the customer's API span; send the customer's API owner the trace_id and the times",
        "Verify": "one /triage call returns in under 1 s, and the alert clears within 5 minutes",
        "Escalate to": "the customer's API team (their on-call), with the time window",
    },
    "2. The customer API rejects triage's token": {
        "Symptom": "triage answers 502; logs show erp_error with erp_status 401 or 403",
        "First check": "did the customer rotate the reader secret? Ask them; never paste a secret into chat or a ticket",
        "Mitigate": "the customer puts the current secret in its secret store; redeploy the same image tag with it (lessons 13, 14)",
        "Verify": "one /triage call returns 200, and no new erp_error lines appear",
        "Escalate to": "the customer's identity team, if the reader account is locked",
    },
    "3. A bad release writes wrong labels": {
        "Symptom": "the customer reports labels changed since the last release; a sample of 10 orders disagrees with the eval set",
        "First check": "which tag is running (the version field) and when it was deployed",
        "Mitigate": "roll back to the last good tag (TRIAGE_TAG=<tag>; the images are kept), then restore the decisions store from the backup taken before the release; decisions written after the backup are lost, so tell the customer the time window",
        "Verify": "the sample of 10 agrees with the eval set; the restore drill checks only prove the backup is sound, so this sample is the real check on the live store",
        "Escalate to": "the customer's operations lead, with the list of affected orders",
    },
}

# %% [markdown]
# Now write the runbooks to a file. The check prints any section that is empty.

# %%
def missing_sections(runbook: dict) -> list[str]:
    return [s for s in SECTIONS if not runbook.get(s)]


def render(title: str, runbook: dict) -> str:
    return f"# Runbook: {title}\n\n" + "\n".join(f"## {s}\n{runbook[s]}\n" for s in SECTIONS)


for title, rb in RUNBOOKS.items():
    print(f"{title}: missing sections -> {missing_sections(rb) or 'none'}")
text = "\n".join(render(t, rb) for t, rb in RUNBOOKS.items())
_ = (DATA / "runbooks.md").write_text(text)  # the file is saved; write_text returns a count we do not show

# %% [markdown]
# ### Step 3: the decisions store and its backup
#
# The customer keeps an audit store of triage decisions: one row per triage request, with its label and the release that gave it. In this lab it is a SQLite file (invented data). The eight rows are the eight requests of lesson 16's recorded run, so the labels are real output. Before each release, the ops job copies the store to a backup. The copy uses SQLite's online backup, which is safe while the file is in use.

# %% [markdown]
# Two helpers: one copies a whole database, one counts rows.

# %%
def copy_db(src_path: Path, dst_path: Path) -> None:
    """Online copy of a whole SQLite database (Connection.backup, Python 3.7+)."""
    if dst_path.exists():
        dst_path.unlink()
    src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def count(path: Path, sql: str = "SELECT COUNT(*) FROM decisions") -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()

# %% [markdown]
# Now create the store from the recorded requests, and take the backup.

# %%
MISSING = "SELECT COUNT(*) FROM decisions WHERE label = 'missing items'"
db, backup, meta = DATA / "decisions.db", DATA / "decisions-before-release.db", DATA / "decisions-before-release.json"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.execute("CREATE TABLE decisions (id INTEGER PRIMARY KEY, order_id TEXT, label TEXT, version TEXT)")
rows = [line.split(" ", 2) for line in REC["requests"].splitlines()]  # order, status, label
con.executemany("INSERT INTO decisions (order_id, label, version) VALUES (?, ?, ?)",
                [(order, label, "1.2.0") for order, _, label in rows])
con.commit()
con.close()
print("rows in store:", count(db), "| labelled 'missing items':", count(db, MISSING))

# %% [markdown]
# Before the release, the ops job takes the backup and writes down when it was taken.

# %%
copy_db(db, backup)
meta.write_text(json.dumps({"taken_at": datetime.now(timezone.utc).isoformat(), "release": "1.2.0"}))
print("rows in backup:", count(backup), "| labelled 'missing items':", count(backup, MISSING))

# %% [markdown]
# ### Step 4: the bad release and the restore drill
#
# Now the incident. This lab simulates release 1.2.x writing `complete` on every order. The drill follows the runbook: restore into a **scratch file first**, run the checks, and only if every check passes copy the scratch file over the live store. The RTO target is 15 minutes and the RPO is 24 hours. These are lab values; the customer signs its own in the SLA.

# %%
RTO_S, RPO_H = 15 * 60, 24

con = sqlite3.connect(db)
con.execute("UPDATE decisions SET label = 'complete'")  # the bad release (simulated)
con.commit()
con.close()
print("live store after the bad release, 'missing items':", count(db, MISSING))


def scratch_checks(backup_path: Path, meta_path: Path) -> dict:
    """Restore to a scratch file and check it. Returns one True or False per check."""
    start = time.perf_counter()
    scratch = DATA / "restore-scratch.db"  # restore here first; never over the live file
    copy_db(backup_path, scratch)
    con = sqlite3.connect(scratch)
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    taken = datetime.fromisoformat(json.loads(meta_path.read_text())["taken_at"])
    return {
        "integrity": integrity == "ok",
        "rows": count(scratch) == count(backup_path),
        "labels": count(scratch, MISSING) == count(backup_path, MISSING),
        "rto": time.perf_counter() - start <= RTO_S,
        "rpo": datetime.now(timezone.utc) - taken <= timedelta(hours=RPO_H),
    }

# %% [markdown]
# The drill: check the scratch copy. Only if every check passes is it cut over to the live store, and every drill is written to a log.

# %%
def restore_drill(backup_path: Path, meta_path: Path, live_path: Path) -> dict:
    checks = scratch_checks(backup_path, meta_path)
    if all(checks.values()):
        copy_db(DATA / "restore-scratch.db", live_path)  # cutover: only a checked copy goes live
    with (DATA / "drill_log.jsonl").open("a") as log:
        log.write(json.dumps({"drill": datetime.now(timezone.utc).date().isoformat(), **checks}) + "\n")
    return checks


report = restore_drill(backup, meta, db)
for name, ok in report.items():
    print(f"{name:<10} {'ok' if ok else 'FAILED'}")
print("live store after the restore, 'missing items':", count(db, MISSING))

# %% [markdown]
# ## At work
#
# - **Customers ask for the runbook at handover.** It is what their team uses after you leave, so write it for a reader who did not build the system. → lesson 22 (handoff and enabling the customer's team).
# - **Roll back first.** Keep the last good image tag ready; a rollback takes minutes, a debugging session can take hours. → lesson 24 (zero-downtime changes and rollback).
# - **Test the backup on a schedule.** The RPO and RTO go into the customer's SLA, and a drill proves them. → lesson 28 (failure drill: a model provider goes down).

# %% [markdown]
# ## Common mistakes
#
# **Mistake 1: restoring to a file name with a typo.** SQLite creates an empty file when the name is new. The check then runs on an empty database, and fails with "no such table". The drill fails loudly, which is the point. The fix: before counting, check the file has a `decisions` table (a query on `sqlite_master`), and if not, redo the restore to the right name.

# %% tags=["raises-exception"]
typo = DATA / "decisions-restroed.db"  # the restore wrote to this name, with a typo
typo.unlink(missing_ok=True)
print(count(typo))

# %% [markdown]
# **Mistake 2: restoring over the live file before the check.** If the backup is bad, the live store is now bad too. Always restore to the scratch file, check it, then cut over.
#
# **Mistake 3: a runbook with no Verify step.** The on-call cannot tell whether the fix worked, so they guess again. Every runbook ends with a check someone can run in a minute.

# %% [markdown]
# ## Try it
#
# Write `drill_verdict(report)`. It returns `PASS` when every check is ok, and otherwise `FAIL: ` followed by the names of the failed checks, separated by commas. Use the two sample reports below.

# %%
# your code here
def drill_verdict(report: dict) -> str:
    """'PASS', or 'FAIL: ' and the names of the failed checks."""
    return ""  # your code here


print(drill_verdict({"integrity": True, "rows": True, "labels": False, "rto": True, "rpo": True}))
print(drill_verdict({"integrity": True, "rows": True, "labels": True, "rto": True, "rpo": True}))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def drill_verdict(report: dict) -> str:
    """'PASS', or 'FAIL: ' and the names of the failed checks."""
    failed = [name for name, ok in report.items() if not ok]
    return "PASS" if not failed else "FAIL: " + ", ".join(failed)

# %% [markdown]
# ## Recap
#
# - **Runbook**: one incident's steps: symptom, first check, mitigation, verify, escalation. Keep it next to the alert it answers.
# - **Mitigate first**: roll back or restore, then find the cause in a blameless postmortem.
# - **RPO** is how much data you may lose; **RTO** is how long you may be down. Both come from the customer's SLA.
# - **Restore drill**: restore to a scratch file, check it, time it, and only then cut over. A backup nobody has restored is a hope.
# - Go deeper: the failure drill in lesson 28 and the handoff documents in lesson 22.
#
# **Interview:** "Labels changed for the whole customer since last night. What do you do?" Strong answer: stop the harm first. Roll back to the last good tag, restore the affected store from the backup taken before the release after checking it, and confirm with a sample. Then tell the customer the time window and write the postmortem. Debugging the code comes after that.
