# %% [markdown]
# # 22 · Handover: documentation and enabling the customer's team
#
# Level L5 · Part 3 · professional · ~20 min · builds on 21
#
# Needs no Docker, no keys and no model calls. The handover pack is a small JSON file that this notebook writes to `../data/22/`. The checks use Pydantic, the validation library from lessons 06 and 19.

# %% [markdown]
# ## Goal
#
# By the end you can build a handover pack for the Basket Bazaar triage service, check it so that every alert has a complete runbook and no part is still owned by you, and score a training drill that the customer's on-call team runs without you.

# %% [markdown]
# ## Why it matters
#
# Without a handover, the customer's ops analyst calls you at 2 a.m., the third time this month. You are now the on-call for a system you do not own, and the customer cannot grow a team that runs it. A handover that is only a README fails the same way.
#
# The next cell counts the six questions an on-call person asks at 2 a.m. and checks how many a README has a section for.
#
# - **Without a handover pack:** the README names the start command and the settings file. The on-call person guesses the rest.
# - **With one:** every question has a section that answers it, and a drill has shown that the team can use it.
# - **When you don't need it:** a tool only you use. A customer who depends on it needs the handover pack.

# %%
README = {"start": "docker compose up", "settings": ".env file", "contact": "the FDE team"}
# A simplified key-name check: it only asks whether a section with that name exists.
# The drill in Step 5 shows whether the sections actually answer the questions.
ON_CALL_QUESTIONS = {  # question -> the handover section that answers it
    "What do I check first when triage is slow?": "runbooks",
    "Who owns the Basket Bazaar orders API?": "owners",
    "Where is the reader secret, and who rotates it?": "secrets",
    "How do I roll back a bad release?": "runbooks",
    "Is the decisions backup recent enough to restore?": "backups",
    "Who do I call, and at what hour?": "support",
}
answered = [q for q, section in ON_CALL_QUESTIONS.items() if section in README]
print(f"README has a section for {len(answered)} of {len(ON_CALL_QUESTIONS)} on-call questions")

# %% [markdown]
# ## The idea
#
# A **handover** moves a deployed service to the customer's team so it runs without the engineer who built it (glossary: handover). It has two parts. The **handover pack** is the written material: runbooks, an ownership matrix, where the secrets live, the backup policy and the support tiers. The **training drill** proves the handover pack works: the customer's on-call runs a runbook on a staged fault while you watch and keep your hands off the keyboard. You sign the handover only when the drill passes. Lessons 20 and 31 call the one-page summary a "handover page"; the handover pack is the full checked set of material behind it.
#
# Analogy: moving into a rented flat. The landlord gives you the keys and the manual, and then shows you where the fuse box is and has you switch the power off once. The keys alone do not tell you how to restore the power.

# %% [markdown]
# ## Picture
#
# The handover pack is checked before the drill, and the drill decides the sign-off.

# %% [markdown]
# ```mermaid
# flowchart LR
#     P[Handover pack: runbooks, owners, secret names, backups, support] --> C{Checks pass?}
#     C -- no --> P
#     C -- yes --> T[Training drill: customer on-call runs a runbook on a staged fault]
#     T --> D{Drill passed, FDE hands off?}
#     D -- no --> T
#     D -- yes --> S[Sign-off: the customer owns the service]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the handover pack as checked data
#
# Each runbook has the five sections from lesson 17. The handover pack has a field for each on-call question. It holds names and places of secrets, never their values. The data is invented for the lab, and the dates are a lab plan, not a real handover.
#
# The backups field uses two terms, **RPO** and **restore drill**, which lesson 17 defines; this handover pack only uses them.
#
# Basket Bazaar is the **customer**, so its teams appear as customer owners. "FDE team" is our vendor team. The lab calls the customer's system ERP in config names; it is the customer API.

# %%
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ValidationError

DATA = Path("../data/22")  # this lesson's run-time files
DATA.mkdir(parents=True, exist_ok=True)


class Runbook(BaseModel):
    symptom: str
    first_check: str
    mitigation: str
    verify: str
    escalate_to: str


class HandoverPack(BaseModel):
    service: str
    handed_over_on: date
    owners: dict[str, str]        # part of the system -> owner after handover
    secrets: str                  # where the secrets live: names and places, never values
    backups: str                  # what is copied, how often, and the RPO
    support: dict[str, str]       # support tier -> who answers, and when
    alerts: list[str]
    runbooks: dict[str, Runbook]  # alert name -> its runbook


# %% [markdown]
# The handover pack's content. Owners are teams, not people. The dates are a lab plan, and the data is invented for the lab.
# The `runbooks` field starts empty here; the next cell fills it.

# %%
pack_data = {
    "service": "Basket Bazaar triage (lab)",
    "handed_over_on": "2026-11-06",
    "owners": {
        "triage code and image": "Basket Bazaar platform team",
        "customer API": "orders API team (customer)",
        "reader secret and its rotation": "identity team (customer)",
        "decisions store and backups": "Basket Bazaar operations",
    },
    "secrets": "the customer's secret store; the handover pack names the secret, never its value",
    "backups": "decisions store copied before each release; RPO 24 hours; restore drill before go-live",
    "support": {"tier 1": "operations desk, 24/7", "tier 2": "owning team, business hours", "tier 3": "vendor FDE team, by agreement"},
    "alerts": ["triage_slow", "erp_auth_failed", "backup_older_than_24h"],
    "runbooks": {},  # the runbooks are added in the next cell
}
# %% [markdown]
# Two runbooks, one per alert. The third alert, the backup age, has no runbook yet. Step 2 finds it.
# The printed output shows the first 8 lines of the saved JSON file, and then the coverage count.

# %%
pack_data["runbooks"]["triage_slow"] = {
    "symptom": "more than 1 in 4 triage requests take over 1 s",
    "first_check": "open one slow log line; its trace_id shows the slowest span",
    "mitigation": "do not restart triage: the time is in the orders API call; send that team the trace_id",
    "verify": "one /triage call answers in under 1 s and the alert clears within 5 minutes",
    "escalate_to": "orders API on-call (tier 2), with the time window",
}
pack_data["runbooks"]["erp_auth_failed"] = {
    "symptom": "triage answers 502; logs show erp_error with status 401 or 403",
    "first_check": "ask the orders API team if the reader secret was rotated; never paste a secret into a ticket",
    "mitigation": "put the current secret in the secret store and redeploy the same image tag",
    "verify": "one /triage call answers 200 and no new erp_error lines appear",
    "escalate_to": "identity team (tier 2) if the reader account is locked",
}
pack = HandoverPack.model_validate(pack_data)
(DATA / "handover-pack.json").write_text(pack.model_dump_json(indent=2))
print("\n".join((DATA / "handover-pack.json").read_text().splitlines()[:8]))
# A section name is not an answer: the Step 5 drill shows whether the sections answer the questions.
pack_answers = [q for q, section in ON_CALL_QUESTIONS.items() if section in pack.model_dump()]
print(f"\nthe handover pack has a section for {len(pack_answers)} of {len(ON_CALL_QUESTIONS)} on-call questions")

# %% [markdown]
# ### Step 2: every alert needs a runbook
#
# The production checklist in lesson 21 says every alert has an owner and a runbook. The check lists alerts with no runbook. Run it on the handover pack as it is now.

# %%
def coverage_gaps(p: HandoverPack) -> list[str]:
    return sorted(set(p.alerts) - set(p.runbooks))


print("alerts without a runbook:", coverage_gaps(pack))

# %% [markdown]
# ### Step 3: a runbook without a verify step is refused
#
# A runbook that has no check to prove the fix worked is not finished. Pydantic refuses it and names the missing fields.

# %%
try:
    Runbook(symptom="backup is old", first_check="read the backup time", mitigation="copy the store again", escalate_to="ops")
except ValidationError as err:
    print("refused, missing:", [e["loc"][0] for e in err.errors()])

# %% [markdown]
# ### Step 4: the ownership matrix after handover
#
# Each part of the system has one owner after handover: a customer team, and never our vendor team. The check looks for owners in `VENDOR_TEAMS`, the names that mean our FDE team. After a handover that list should be empty.
#
# Support tier 3 ("vendor FDE team, by agreement") is a support role, not ownership, so this check does not read the support section.

# %%
VENDOR_TEAMS = {"FDE team"}  # the names that mean our own team in the handover pack


def still_ours(p: HandoverPack) -> list[tuple[str, str]]:
    return [(part, owner) for part, owner in p.owners.items() if owner in VENDOR_TEAMS]


for part, owner in pack.owners.items():
    print(f"{part:<34}{owner}")
print("parts still owned by the FDE team:", still_ours(pack))

# The same check on a copy where one owner is still our team: the check flags that row.
trial = pack.model_copy(update={"owners": {**pack.owners, "customer API": "FDE team"}})
print("same check, one owner set to FDE team:", still_ours(trial))

# %% [markdown]
# ### Step 5: the training drill
#
# The trainer fills in the drill record during the session: one flag per step, and the minutes the on-call team took. The drill passes only when every step is done, the FDE team did not touch the keyboard, and the time is within the limit.
#
# The six steps and the 30-minute limit are invented for the lab; a real handover plan sets its own. The records below are invented. The first result is for an empty record, before the drill has started. The second is a full record at 20 minutes, which passes.

# %%
DRILL_STEPS = ["symptom seen", "first check done", "mitigation done", "verify passed", "escalation made", "FDE hands off the keyboard"]
TIME_LIMIT_MIN = 30  # lab limit; the customer sets its own in the handover plan


def drill_result(record: dict[str, bool], minutes: float) -> str:
    missing = [s for s in DRILL_STEPS if not record.get(s)]
    if missing:
        return f"not passed: {len(missing)} step(s) not done: {missing}"
    if minutes > TIME_LIMIT_MIN:
        return f"not passed: {minutes:.0f} min is over the {TIME_LIMIT_MIN}-min limit"
    return "passed: the customer's on-call team ran the runbook alone"


print(drill_result({}, minutes=0))
full_record = {step: True for step in DRILL_STEPS}  # invented record: every step done
print(drill_result(full_record, minutes=20))

# %% [markdown]
# ## At work
#
# - **A handover is a sign-off, not a README.** Customer teams take over with runbooks, an ownership matrix and a rehearsed drill (RESEARCH.md section 7.5, unverified; the section 3 handover items come from a single practitioner source). → lesson 17, lesson 31.
# - **Ownership moves to the customer team in writing.** Cagan (SVPG, 2025) warns that bespoke FDE work piles up as thousands of custom solutions; the playbook ends with SLOs and ownership transfer (RESEARCH.md section 8, item 12). → lesson 25, lesson 31.
# - **Secrets are named in the handover pack, never written in it.** Security reviews ask for RBAC, audit logs and encryption evidence (RESEARCH.md section 7.3, list unverified). → lesson 27.
# - **An untested handover pack goes stale.** The team that inherits it finds the gaps in its first real incident. Go deeper: the customer delivery drill in lesson 32.

# %% [markdown]
# ## Common mistakes
#
# **Mistake 1: a handover that is a plain dict.** A dict is not checked, so a missing field stays hidden until the 2 a.m. incident reads it. This cell is meant to fail: it reads a runbook with no `verify` key and stops with a KeyError at that moment.

# %% tags=["raises-exception"]
raw_runbook = {"symptom": "triage is slow", "first_check": "read the trace", "mitigation": "send the trace to the orders API team"}
print(raw_runbook["verify"])  # KeyError: no verify step was written, and nothing checked it before the incident

# %% [markdown]
# **The fix:** validate at handover time with `Runbook.model_validate(...)`, as Step 3 does. The handover pack is refused before the customer ever sees it.
#
# **Mistake 2: a training session with slides and no drill.** Attendees nod and then cannot find the runbook in the incident. Score the session with the drill record instead of asking "any questions?"

# %% [markdown]
# ## Production checklist
#
# Before you sign the handover, every line should be true:
#
# - [ ] Every alert has a runbook with all five sections, and the verify step is a check the on-call person can run alone (lesson 17).
# - [ ] Every part of the system has one owner after handover, and none is the FDE team (lesson 31).
# - [ ] Secrets are named in the handover pack with their place in the secret store; no value appears in it (lesson 13).
# - [ ] The backup policy, the RPO and the last restore drill are written in the handover pack (lesson 17).
# - [ ] Each support tier names a team and its hours (lesson 31).
# - [ ] The training drill passed with the FDE off the keyboard, and the sign-off is dated (lesson 32).

# %% [markdown]
# ## Try it
#
# Close the gap from Step 2. Write a runbook for `backup_older_than_24h` (the backup is older than the 24-hour RPO), add it to `pack_data["runbooks"]`, rebuild the handover pack and print `coverage_gaps`. Then score a drill where every step was done and it took 42 minutes.

# %%
# your code here
# 1. Write a runbook dict for "backup_older_than_24h" with symptom, first_check, mitigation, verify, escalate_to.
#    Hint: the verify step must be a check the on-call person can run alone (one request, one log query, one file check).
# 2. Add it to pack_data["runbooks"], rebuild the handover pack with HandoverPack.model_validate, and print coverage_gaps(pack).
# 3. Print drill_result(record, minutes=42) for a record where every step in DRILL_STEPS is True (this 42-minute record is invented).

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
pack_data["runbooks"]["backup_older_than_24h"] = {
    "symptom": "the newest decisions backup is more than 24 hours old",
    "first_check": "read handover-pack.json's backups line and the time of the last copy job",
    "mitigation": "run the copy job now, to the scratch path; do not overwrite the live store",
    "verify": "a restore of the new copy to a scratch file passes the integrity check within 15 minutes",
    "escalate_to": "operations desk (tier 1); the backup owner (tier 2) if the copy job fails",
}
pack = HandoverPack.model_validate(pack_data)
print("alerts without a runbook:", coverage_gaps(pack))
# The 42-minute record is invented: it shows the time limit failing.
print(drill_result(full_record, minutes=42))

# %% [markdown]
# ## Recap
#
# - A handover moves the service to the customer's team: a written handover pack, an ownership matrix, and a drill they pass alone.
# - Check the handover pack like code: every alert has a complete runbook, and a dict is not enough because nothing checks it.
# - The FDE team owns nothing after sign-off. Secrets are named, never written.
# - Words to keep: **handover**, **runbook**, **restore drill** (all in the glossary).
#
# **Interview:** "You are handing an AI feature to a customer's ops team next Friday. What goes in the handover, and how do you know it worked?" Strong answer: "A handover pack with a runbook for every alert, each with a first check, a mitigation and a verify step; an ownership matrix with no row still owned by us; secret names and the backup policy. I sign off only when their on-call runs one runbook on a staged fault, alone, inside the time limit."
