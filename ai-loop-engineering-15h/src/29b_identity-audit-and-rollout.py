# %% [markdown]
# # 29b · Identity, audit and rollout: agent identity, shadow runs, canary and rollback
# Level L6 · Part 4 · core · ~20 min · builds on 29a
#
# ## Goal
# Give every run an identity (agent, tenant, run id, config bundle), write an append-only audit row for each tool call and each approval, and roll a new bundle out as shadow, then a 5% canary, then back to stable when the golden set or the canary metric says so.
#
# ## Before you start
# No key, no Docker and no network. This is a walkthrough: you read the bundle and the rules, run the cells, and read the audit rows they write to a local SQLite file. Nothing calls a model. The score and count numbers in Step 8 are labelled examples, not a measured run.

# %% [markdown]
# ## Why it matters
# Lesson 29a limits how much a tenant can spend. Spending is not the only risk: a bad change can start refunds that nobody approved. Without identity, audit and a controlled rollout:
#
# | Without this | What goes wrong |
# |---|---|
# | Every run uses one shared key and one name | Nobody can say which agent or tenant made a refund |
# | Tool calls are printed, not stored | The investigation after a bad refund has nothing to read |
# | A prompt edit goes live for every run at once | A change that breaks refunds reaches 100% of customers before anyone sees it |
# | Rollback means redeploying the code | The fix waits for a build, while bad refunds keep going out |
#
# With identity on every row, an append-only audit and a 5% canary, a bad change stops at 5% and goes back with one pointer change. You do not need any of this for one agent you run by hand.

# %% [markdown]
# ## The idea
# **A release is one bundle: the prompt, the tool list, the model id, the caps and the golden set it must pass. Every run records its identity and its bundle id, and every tool call and approval writes one row to an audit table that cannot be edited. A new bundle first runs in shadow, then takes 5% of new runs, and goes back to stable on a regression. Runs already in flight keep the bundle they started with.**
#
# Analogy: an airline's flight manifest and a test flight. Every passenger is listed with a ticket (identity), every crew action is logged in the flight record (audit), and a new procedure is first flown with a few passengers on the same route (canary). If the test flight shows a problem, the crew goes back to the old procedure for the next flight. The flight already in the air finishes the way it started.

# %% [markdown]
# ## Picture
# Stable and candidate bundles sit side by side. A pointer decides who gets which. Every run and every tool call writes a row to the same audit table.
#
# ```mermaid
# flowchart LR
#   R["new run"] --> L{"lane: hash of run id mod 100 < 5?"}
#   L -->|yes, 5%| C["candidate bundle"]
#   L -->|no, 95%| S["stable bundle"]
#   C --> A[("audit table<br/>append-only")]
#   S --> A
#   G["golden set gate"] -->|fail| B["rollback: pointer back to stable"]
#   C -.-> G
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: one bundle per release
# A bundle holds everything that changes behaviour. The model id is read from config, never hard-coded. The bundle id is a hash of its contents, so changing one word changes the id and the audit rows point at the exact version.

# %%
import sys; sys.path.insert(0, "..")
import hashlib, json, pathlib, sqlite3
from collections import Counter
from tut_env import env  # the model id comes from .env (optional), with a default

def make_bundle(prompt, tools, caps):
    body = {"prompt": prompt, "tools": tools, "model": env("TUT_LLM_MODEL", "gemini-2.5-flash-lite"), "caps": caps}
    return {"bundle_id": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10], **body}

CAPS = {"max_steps": 4, "max_usd_per_run": 4.0}
PROMPT = "You are the support desk for Brightside Outfitters. Look up the order, then propose a refund for a damaged item."
STABLE = make_bundle(PROMPT, ["get_order", "propose_refund"], CAPS)
CANDIDATE = make_bundle(PROMPT + " Quote the order id in every proposal.", ["get_order", "propose_refund"], CAPS)
print("stable:", STABLE["bundle_id"], "| candidate:", CANDIDATE["bundle_id"], "| same caps:", STABLE["caps"] == CANDIDATE["caps"])

# %% [markdown]
# **What you should see:** two ids. The candidate differs by one sentence, so its id differs too. Same caps, so only the prompt is the change under test.

# %% [markdown]
# ### Step 2: identity on every run
# A run's identity has four fields: the agent, the tenant, the run id and the bundle. The gateway key from lesson 29a carries the tenant and the agent in its `metadata`. The platform issues a short-lived credential per run; this lesson prints only its shape, and no token is made.

# %%
def run_identity(run_id, tenant, bundle):
    return {"run_id": run_id, "tenant.id": tenant, "agent.id": "desk-refunds", "version_bundle": bundle["bundle_id"]}

ident = run_identity("run-0001", "brightside", STABLE)
KEY_METADATA = {"team_id": "brightside", "metadata": ident,
                "credential": {"lifetime_s": 900, "scope": "gateway:brightside"}}  # shape only, no token
print(json.dumps(KEY_METADATA, indent=2))

# %% [markdown]
# **What you should see:** the run's four identity fields next to the key's lifetime. The credential lasts 15 minutes and is scoped to one tenant, so a leaked one expires soon and reaches one tenant only.

# %% [markdown]
# ### Step 3: role-based access to tools
# Role-based access control (RBAC) says which role may call which tool. Deny by default: a role that is not in the table can call nothing. The agent can propose a refund but cannot approve one, so the same identity cannot both ask for and grant a payout.

# %%
ROLES = {"desk-agent": {"get_order", "propose_refund"}, "desk-approver": {"approve_refund"}}

def may_call(role, tool):
    return tool in ROLES.get(role, set())  # not in the table: no

for role, tool in [("desk-agent", "propose_refund"), ("desk-agent", "approve_refund"), ("desk-approver", "approve_refund")]:
    print(f"{role:14} {tool:16} -> {'allowed' if may_call(role, tool) else 'denied'}")

# %% [markdown]
# **What you should see:** the agent may propose and may not approve. The approver may approve. This is separation of duties, checked before the tool runs.

# %% [markdown]
# ### Step 4: the audit table, append-only
# Every tool call and every approval writes one row: time, run, tenant, the chain of actors, the tool, the decision, a hash of the result and the bundle id. The result is hashed, not stored, so customer text stays out of the audit by default. Two triggers refuse every `UPDATE` and `DELETE`, so a row, once written, stays as it was.

# %%
AUDIT = pathlib.Path("../data/29b/audit.db")
AUDIT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.unlink(missing_ok=True)  # a fresh audit file each time the notebook runs
db = sqlite3.connect(AUDIT)
db.executescript("""
CREATE TABLE audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, run_id TEXT NOT NULL, tenant TEXT NOT NULL, actor_chain TEXT NOT NULL,
  tool TEXT NOT NULL, decision TEXT NOT NULL, result_hash TEXT NOT NULL, version_bundle TEXT NOT NULL
);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
""")
clock = iter(range(1, 1000))  # a fixed clock, so the printed rows are the same on every run

def audit(ident, actor_chain, tool, decision, result=""):
    ts = f"2026-10-28T09:{next(clock):02d}:00Z"
    db.execute("INSERT INTO audit (ts, run_id, tenant, actor_chain, tool, decision, result_hash, version_bundle) "
               "VALUES (?,?,?,?,?,?,?,?)",
               (ts, ident["run_id"], ident["tenant.id"], actor_chain, tool, decision,
                hashlib.sha256(result.encode()).hexdigest()[:12], ident["version_bundle"]))

# %% [markdown]
# ### Step 5: one run, written to the audit
# The run below asks for a refund. The agent's proposal is allowed, the agent's approval attempt is denied, and the approver's decision is recorded. The tool results are examples; the cell calls no model.

# %%
audit(ident, "tenant:brightside > agent:desk-refunds", "get_order", "allowed", "BS-1042 paid 120")
audit(ident, "tenant:brightside > agent:desk-refunds", "propose_refund", "allowed", "refund 120 proposed")
audit(ident, "tenant:brightside > agent:desk-refunds", "approve_refund", "denied: role desk-agent")
audit(ident, "tenant:brightside > desk-approver:ana", "approve_refund", "approved", "refund 120 accepted")
for row in db.execute("SELECT seq, ts, tool, decision, version_bundle FROM audit ORDER BY seq"):
    print(row)

# %% [markdown]
# **What you should see:** four rows in order, one per call or decision, each with the bundle id. The denied attempt is a row too: a refusal is evidence.

# %% [markdown]
# ### Step 6: try to edit the audit
# The triggers make a rewrite fail. The `try` below attempts the edit and prints the error the database returns. The row is unchanged after the attempt.

# %%
try:
    db.execute("UPDATE audit SET decision = 'approved' WHERE seq = 3")
except sqlite3.DatabaseError as err:
    print("blocked:", err)
print("row 3 still says:", db.execute("SELECT decision FROM audit WHERE seq = 3").fetchone()[0])

# %% [markdown]
# **What you should see:** the edit is blocked with the message from the trigger, and row 3 still says `denied`. The audit records what happened, not what someone wishes had happened.

# %% [markdown]
# ### Step 7: route 5% of new runs to the candidate
# A lane is decided by a hash of the run id: `hash mod 100 < 5` is the canary. The same run id always gets the same lane, so a retry of a run stays on its bundle. Over 1,000 run ids the share should be close to 5%.

# %%
def lane(run_id, canary_pct=5):
    bucket = int(hashlib.sha256(run_id.encode()).hexdigest(), 16) % 100
    return "canary" if bucket < canary_pct else "stable"

runs = [f"run-{i:04d}" for i in range(1000)]
counts = Counter(lane(r) for r in runs)
print(counts, "| same run, same lane:", lane("run-0001") == lane("run-0001"))

# %% [markdown]
# **What you should see:** about 50 runs in the canary and about 950 in stable. The exact count is fixed by the hash, so it is the same on every run.

# %% [markdown]
# ### Step 8: the gates, with example numbers
# A rollout moves in three stages. Shadow: the candidate runs on the golden set, its answers are discarded, and it passes if it scores at least as well as stable. Canary: 5% of runs use the candidate. Rollback: if the candidate's golden score falls below the accepted score, or its error rate on live canary runs is more than 5 points worse than stable, the pointer goes back to stable.
#
# The numbers below are illustrative, not a measured run. They show how the gate reads counts.

# %%
GOLDEN_ACCEPTED = 4          # cases that pass on the stable bundle (the four golden cases of lesson 07)
shadow_pass = 4              # example: the candidate, run in shadow, passes all four
canary_err, canary_n = 0.20, 54   # example: 20% of the 54 canary runs ended in an error
stable_err, stable_n = 0.03, 946  # example: 3% of the 946 stable runs did

def gate(shadow_pass, canary_err, stable_err, max_extra=0.05):
    if shadow_pass < GOLDEN_ACCEPTED:
        return "block: shadow golden score below accepted"
    if canary_err - stable_err > max_extra:
        return "rollback: canary errors exceed stable by more than 5 points"
    return "keep canary"

print("stage 1 (shadow):", "promote to canary" if shadow_pass >= GOLDEN_ACCEPTED else "block")
print("stage 2 (canary):", gate(shadow_pass, canary_err, stable_err))

# %% [markdown]
# **What you should see:** the candidate passes shadow, so it goes to canary. The canary error rate is 17 points over stable, so the gate says rollback. The 54 canary runs are a small sample: the gate reads a large gap, not a fine one.

# %% [markdown]
# ### Step 9: the pointer, rollback and in-flight runs
# The release is one file: which bundle is stable, which is the candidate, and whether the canary is on. Changing that file is the rollback. A run reads its bundle once, when it starts, and writes that id to its identity. A rollback changes new runs only.

# %%
RELEASE = pathlib.Path("../data/29b/release.json")
RELEASE.write_text(json.dumps({"stable": STABLE["bundle_id"], "candidate": CANDIDATE["bundle_id"], "canary_on": True}))

def bundle_for(run_id):
    rel = json.loads(RELEASE.read_text())  # read at run start, once
    return rel["candidate"] if rel["canary_on"] and lane(run_id) == "canary" else rel["stable"]

canary_run = next(r for r in runs if lane(r) == "canary")  # the first run id in the canary lane
in_flight = bundle_for(canary_run)                          # this run started during the canary
print(canary_run, "before rollback gets:", in_flight, "| candidate is", CANDIDATE["bundle_id"])
RELEASE.write_text(json.dumps({"stable": STABLE["bundle_id"], "candidate": CANDIDATE["bundle_id"], "canary_on": False}))
print(canary_run, "as a new run after rollback gets:", bundle_for(canary_run))
print("the in-flight run still records:", in_flight)

# %% [markdown]
# **What you should see:** before the rollback, the canary run is on the candidate. After it, a new run with the same lane gets the stable id. The run that started earlier keeps the candidate id it recorded, so its audit rows still say which bundle made each call.

# %% [markdown]
# ## At real scale
# - **One config bundle per release.** Prompt, tools and model id changed in separate places make a release nobody tested. Read the model id from config: model ids are retired on a schedule. → lesson 30 puts the bundle into the capstone.
# - **Audit is a stream.** Teams forward audit events to a log store or SIEM, with the actor chain and bundle id on each event and content kept out. The trigger here is the smallest version of append-only.
# - **Canaries are small.** A 5% lane on a few hundred runs a day gives tens of canary runs: enough to show a large regression, not a small one. Keep the golden set as the stronger gate.
# - **In-flight runs keep their bundle.** This is the rainbow pattern in Anthropic's and Managed Agents' guidance. Runs that must stop now need the kill switch of lesson 26b.

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | A tool can change money or data | RBAC table, deny by default | The denial is checked before the call and is audited |
# | An action must be traceable | Append-only audit row per call and per approval | A rewrite leaves a trace; the result stays out as a hash |
# | A prompt or model change may break runs | Shadow, then 5% canary, with the golden set as the gate | Problems show on a small share first |
# | A bad release is live | Point the release at stable | Only new runs move; no redeploy |
# | A stop must act now on running runs | The kill switch of lesson 26b | Rollback never touches runs in flight |

# %% [markdown]
# ## What just happened
# You built one bundle per release and one identity per run, checked a tool call against a role table, and wrote four audit rows that a trigger keeps unchanged. The 5% lane came from a hash, so a retry stays on its bundle. The gate read a canary error rate 17 points over stable and sent the release back to stable with one file change. The run that started in the canary kept its candidate id, so its audit trail still says what happened.

# %% [markdown]
# ## Common mistakes
# The common mistake is an audit that is only a table, with no rule against edits. This cell writes a plain table without the triggers, changes a row, and then asserts the row is intact. The `AssertionError` is the expected failure: the edit went through.

# %% tags=["raises-exception"]
db.execute("CREATE TABLE naive_audit (seq INTEGER PRIMARY KEY, decision TEXT)")
db.execute("INSERT INTO naive_audit VALUES (1, 'denied')")
db.execute("UPDATE naive_audit SET decision = 'approved' WHERE seq = 1")  # nothing stops this
assert db.execute("SELECT decision FROM naive_audit WHERE seq = 1").fetchone()[0] == "denied", \
    "this error is expected: the plain table let someone rewrite a denial"

# %% [markdown]
# The fix is the trigger in Step 4. With it, the same `UPDATE` raises and the row keeps its value.

# %% [markdown]
# ## Try it
# Write `share_in_canary(run_ids, canary_pct)` that returns the fraction of run ids in the canary lane. Predict first: with 5% and 1,000 runs, is the answer near 0.05, 0.5 or 5?

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def share_in_canary(run_ids, canary_pct):
    return sum(lane(r, canary_pct) == "canary" for r in run_ids) / len(run_ids)

# A fraction, so about 0.05 with 1,000 run ids. The same hash decides, so the answer is the same on every run.
print(f"share in canary at 5%: {share_in_canary(runs, 5):.3f}")

# %% [markdown]
# ## Key terms
# - **agent identity** — the fields that name the agent, the tenant, the run and the bundle on every call and row.
# - **RBAC** — role-based access control: a table of which role may call which tool; denied by default.
# - **audit trail** — one row per tool call and approval, kept so the history can be read later; append-only.
# - **shadow run** — the candidate runs on the same inputs, its answers are discarded and only its scores are compared.
# - **canary** — a small share of new runs (here 5%) on the candidate bundle; the rest stay on stable.
# - **rollback** — moving the release pointer back to the stable bundle; new runs change, running ones finish.
# - **config bundle** — one versioned set of prompt, tools, model id and caps that is released as a unit.
#
# %% [markdown]
# **Interview:** How do you roll out a change to an agent safely, and how do you prove who did what? Strong answer: ship the prompt, tools, model and caps as one bundle with an id; run it in shadow on the golden set, then send 5% of new runs to it by a hash of the run id; roll back by moving the pointer, which leaves in-flight runs on their own bundle; give each run an identity and write an append-only audit row for every tool call and approval.
