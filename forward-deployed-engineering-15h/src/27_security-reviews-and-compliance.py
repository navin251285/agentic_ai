# %% [markdown]
# # 27 · Security reviews and compliance evidence
#
# Level L5 · Part 3 · core · ~25 min · builds on 13
#
# Needs no Docker, no keys and no model. The questionnaire, the records and the audit log are invented lab files that the cells write to `../data/27/`. The access check reads lesson 13's mock API file.

# %% [markdown]
# ## Goal
#
# By the end you can answer a customer's security questionnaire question by question, with a pointer to evidence for each answer: where the data is stored, how personal data is kept out of stored records, and what the audit log shows. Where the evidence is missing, you write a **gap**, never a yes.

# %% [markdown]
# ## Why it matters
#
# Before the triage service touches live orders, Basket Bazaar's security team sends you a questionnaire of eight questions. Without an evidence pack, each answer is a promise written from memory. The review stalls while you search for proof, and a claim you cannot prove becomes a finding.
#
# The next cell is the draft a tired engineer writes the night before. It has eight answers and no pointer to anything.

# %%
draft = {
    "Q1": "Customer data stays in our US region.",
    "Q2": "Our model provider only processes data in approved regions.",
    "Q3": "Personal data is removed before records are stored.",
    "Q4": "Every write to customer data is logged with who and when.",
    "Q5": "Audit log entries never hold secrets or personal data.",
    "Q6": "Access tokens expire in minutes and carry only the scopes needed.",
    "Q7": "Triage records are deleted after the agreed retention period.",
    "Q8": "We hold a SOC 2 Type II report for this service.",
}
pointers: dict[str, str] = {}  # a file, log, setting or test behind an answer
print(f"answers drafted: {len(draft)}; with evidence behind them: {len(pointers)}")

# %% [markdown]
# - **Without an evidence pack:** the answers come from memory. The reviewer asks "show me where", and you have nothing to show.
# - **Without a gap list:** a missing report stays hidden until the customer's auditor finds it.
# - **With the pack:** each answer points to a file, a log or a test that anyone can rerun. Missing items are gaps with an owner.
# - **When you don't need it:** a demo with no customer data. A live customer whose orders hold personal data needs it.
#
# A pack does not make the service compliant. It shows what is true now and what is not yet proven.

# %% [markdown]
# ## The idea
#
# A security questionnaire is a list of **claims**. A claim counts only with **evidence** the reviewer can check: a setting, a line of code, a test result or a log sample. When the evidence is missing, the answer is "not yet", with the gap written down.
#
# Some assurance cannot come from you at all. A **SOC 2** report is written by an independent auditor after they examine your controls. A **Type II** report tests that the controls worked over a period of time; a Type I report checks only their design at one date. You send the report, or you say you do not have one. This is general background, not from a source checked for this course: confirm the exact scope of a SOC 2 report with your compliance team or the auditor.
#
# Analogy: an inspector who asks for the fire certificate, not for the builder's word that the exits work.

# %% [markdown]
# ## Picture
#
# Each question follows one path: control, evidence, check, then an answer or a gap.

# %% [markdown]
# ```mermaid
# flowchart LR
#     Q[Customer question] --> C[Control in our system]
#     C --> E[Evidence: setting, code, test or log]
#     E --> K{Check passes?}
#     K -->|yes| A[Answer with a pointer to the evidence]
#     K -->|no| G[Gap: owner and date, never a yes]
#     R[Independent report, such as SOC 2] -.-> A
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the questionnaire
#
# The security team's questionnaire is invented for this lab. The cell writes it to `../data/27/questionnaire.csv` and reads it back. Each question has an area: residency, PII, audit, access, retention or assurance.

# %%
import csv, json, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path("../data/27")  # this lesson's run-time files
DATA.mkdir(parents=True, exist_ok=True)
QUESTIONS = [  # invented questions, not a real customer's form
    ("Q1", "residency", "Where is customer data stored? Name the region."),
    ("Q2", "residency", "Which region does the model provider process prompts in?"),
    ("Q3", "PII", "How is personal data removed before records are stored?"),
    ("Q4", "audit", "Is every write to customer data logged with who did it and when?"),
    ("Q5", "audit", "Can an audit log entry hold a secret or personal data?"),
    ("Q6", "access", "How long do access tokens live, and how are they scoped?"),
    ("Q7", "retention", "How long are triage records kept, and when are they deleted?"),
    ("Q8", "assurance", "Do you hold a SOC 2 Type II report for this service?"),
]
with (DATA / "questionnaire.csv").open("w", newline="") as f:
    csv.writer(f).writerows([("id", "area", "question"), *QUESTIONS])
questions = list(csv.DictReader((DATA / "questionnaire.csv").read_text().splitlines()))
print(len(questions), "questions; Q1 and Q2:", [q["question"] for q in questions[:2]])

# %% [markdown]
# You should see 8 questions. The file is the form the customer sent, so it is the same every time you run the lesson.

# %% [markdown]
# ### Step 2: the settings the check reads
#
# Regions, retention periods and the actor name come from `.env`. The defaults are lab values; the contract sets the real limits. The cell prints only `bool(...)` for each setting, so no value appears in the output. A default is not evidence: `bool(...)` is True for a default too. Q1, Q2 and Q7 pass in this lab only because the lab defaults fall inside the allowed list. In production the values come from the deployed service's configuration.

# %%
sys.path.insert(0, "..")
from tut_env import env

SETTINGS = {
    "STORAGE_REGION": env("STORAGE_REGION", "us-east1"),
    "MODEL_REGION": env("MODEL_REGION", "us-east1"),
    "ALLOWED_REGIONS": set(env("ALLOWED_REGIONS", "us-east1,us-central1").split(",")),
    "RETENTION_DAYS": int(env("RETENTION_DAYS", "30")),
    "CONTRACT_MAX_RETENTION_DAYS": int(env("CONTRACT_MAX_RETENTION_DAYS", "90")),
    "TRIAGE_ACTOR_ID": env("TRIAGE_ACTOR_ID", "bb-triage"),
}
print({name: bool(value) for name, value in SETTINGS.items()})

# %% [markdown]
# ### Step 3: personal data in the records
#
# Six invented triage notes stand in for the free text the service stores. The emails and phone numbers are fake, and the card number is a made-up 16-digit string. A regex finds only the formats it knows, which is enough to show the check. A real scan needs a dedicated detector and a human sample.

# %%
RAW = [
    "Milk missing from BB-1001. Customer ana@example.com asked for a refund.",
    "Eggs wrong in BB-1002, call 555-0142 before 6 pm.",
    f"Bread late. Card {'-'.join(['0000'] * 4)} was declined.",  # an invented 16-digit number
    "Two apples short in BB-1004, no contact details given.",
    "Juice wrong in BB-1005, reply to sam.park@example.com or 555-0199.",
    "Yogurt missing from BB-1006, the customer used 555-0177.",
]
PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"\b555-\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


def count_hits(texts: list[str]) -> dict[str, int]:
    return {kind: sum(len(p.findall(t)) for t in texts) for kind, p in PATTERNS.items()}


def redact(text: str) -> str:
    for kind, pattern in PATTERNS.items():
        text = pattern.sub(f"[{kind} removed]", text)
    return text


STORED = [redact(t) for t in RAW]  # what the pipeline writes to the store
(DATA / "records_stored.csv").write_text("\n".join(STORED) + "\n")
print("raw notes:", count_hits(RAW), "| stored notes:", count_hits(STORED))

# %% [markdown]
# You should see 6 hits in the raw notes (2 emails, 3 phone numbers, 1 card) and 0 in the stored notes. The stored copy keeps what each note means, without the personal details. The phone pattern matches only the invented 555 numbers; real formats vary. The card pattern takes a run of 13 to 16 digits, each optionally followed by a space or dash, so it also catches some long numbers that are not cards.

# %% [markdown]
# ### Step 4: the audit log
#
# Every write to a triage record adds one line to `../data/27/audit.jsonl`: when, which actor, what action, which record and which request. It never holds the note text. The helper plays the role of the triage service's audit code; in production the running service writes these lines itself.
#
# Be careful with what this proves. The notebook wrote this log, so it shows the format and the checks. A reviewer accepts a log only from the running system, for a real request.

# %%
AUDIT = DATA / "audit.jsonl"
AUDIT.write_text("")  # a fresh log each run


def audit(action: str, record_id: str, request_id: str, step: int) -> None:
    """One line per write: who, what, which record, when. Never the note text, never a secret."""
    ts = datetime(2026, 10, 24, 9, tzinfo=timezone.utc) + timedelta(seconds=step)  # fixed times keep the run repeatable
    entry = {"ts": ts.isoformat(), "actor": SETTINGS["TRIAGE_ACTOR_ID"], "action": action, "record_id": record_id, "request_id": request_id}
    AUDIT.write_text(AUDIT.read_text() + json.dumps(entry) + "\n")  # append one line


for i in range(len(RAW)):
    audit("triage.label.write", f"BB-{1001 + i}", f"req-{i + 1:03d}", i)
entries = [json.loads(line) for line in AUDIT.read_text().splitlines()]
print("writes:", len(RAW), "| audit lines:", len(entries))

# %% [markdown]
# You should see 6 writes and 6 audit lines. The first line holds the actor, the action and the record id, and no note text.
#
# Now the check a reviewer would run. Each line needs five fields, and no value may hold personal data or the word "secret".

# %%
REQUIRED = {"ts", "actor", "action", "record_id", "request_id"}


def audit_problems(entry: dict) -> list[str]:
    """Problems in one audit line: a missing field, or personal data or a secret in any value."""
    problems = [f"missing {field}" for field in sorted(REQUIRED - entry.keys())]
    text = json.dumps(entry)
    problems += [f"{kind} found" for kind, hits in count_hits([text]).items() if hits]
    return problems + (["secret word found"] if "secret" in text.lower() else [])


bad_lines = [(e["request_id"], audit_problems(e)) for e in entries]
print("audit lines with a problem:", sum(bool(ps) for _, ps in bad_lines), "of", len(entries))

# %% [markdown]
# You should see 0 problems. This check is a test, so keep it: it runs again on every release.

# %% [markdown]
# ### Step 5: the access evidence comes from code
#
# The token rules are not in a document. They are in the code of lesson 13's mock customer API. The check reads that file for the token lifetime and for the scope check on every endpoint.

# %%
SRC = Path("../apps/13/customer_api.py").read_text()
TOKEN_OK, SCOPE_OK = "TOKEN_SECONDS = 300" in SRC, "def require_scope" in SRC and "dependencies=[Depends(require_scope" in SRC
print("tokens last 5 minutes:", TOKEN_OK, "| every endpoint checks a scope:", SCOPE_OK)

# %% [markdown]
# You should see True for both lines. If a later edit removes the scope check, this check fails, and the answer to Q6 becomes a gap. This is a simple text check: it finds strings in the file, so a reformatted constant or a renamed function breaks it silently. A real review reads the deployed configuration instead. It also shows only that `require_scope` exists, not that tokens are scoped correctly. That is a lab shortcut: in a real system, the evidence is a test that calls the running API with an expired token and with a wrong-scope token, and gets 401 or 403 for each.

# %% [markdown]
# ### Step 6: the pack
#
# One check per question. Each check is True only when its evidence passes. A passing question gets an answer and a pointer; a failing one becomes a gap.

# %%
CHECKS = {  # question id: (passes, evidence)
    "Q1": (SETTINGS["STORAGE_REGION"] in SETTINGS["ALLOWED_REGIONS"], "setting STORAGE_REGION, against ALLOWED_REGIONS (rerun on production)"),
    "Q2": (SETTINGS["MODEL_REGION"] in SETTINGS["ALLOWED_REGIONS"], "setting MODEL_REGION, against ALLOWED_REGIONS (rerun on production)"),
    "Q3": (not any(count_hits(STORED).values()), "scan of data/27/records_stored.csv (rerun on production)"),
    "Q4": (len(entries) == len(RAW) and not any(p.startswith("missing") for _, ps in bad_lines for p in ps), "audit.jsonl: one line per write (rerun on production)"),
    "Q5": (not any(not p.startswith("missing") for _, ps in bad_lines for p in ps), "audit.jsonl: every line scanned (rerun on production)"),
    "Q6": (TOKEN_OK and SCOPE_OK, "apps/13/customer_api.py (lesson 13) (rerun on production)"),
    "Q7": (SETTINGS["RETENTION_DAYS"] <= SETTINGS["CONTRACT_MAX_RETENTION_DAYS"], "setting RETENTION_DAYS, against the contract maximum (rerun on production)"),
    "Q8": (False, "none in the lab: no SOC 2 report exists, so none is claimed"),
}
pack = ["# Security evidence pack (lab, invented data)"]
for q in questions:
    passes, evidence = CHECKS[q["id"]]
    status = "answered (lab)" if passes else "GAP"
    print(f"{q['id']} {status:<9} {evidence}")
    pack.append(f"\n## {q['id']} [{q['area']}] {status}\n{q['question']}\n- Evidence: {evidence}")
(DATA / "security_pack.md").write_text("\n".join(pack) + "\n")
print(f"answered with evidence: {sum(CHECKS[q['id']][0] for q in questions)} of {len(questions)}")

# %% [markdown]
# You should see Q1 to Q7 answered (lab) and Q8 as a gap. The gap is the honest result: the lab has no audit report, so the pack says so instead of claiming one. The pack is in `../data/27/security_pack.md`, ready to send with the gap list.

Q1 to Q7 are answered against lab values and lab files. They show the checks work. Only the same checks on the running service count as evidence. Q1, Q2 and Q7 pass only because of the lab defaults, and a default is not evidence. Q4's count check is true by construction here, since the notebook makes the writes; in production the count comes from the running service's own log.

# %% [markdown]
# ## At work
#
# - Customers send a standard questionnaire, such as SIG (Standardized Information Gathering) or CAIQ (the Cloud Security Alliance's questionnaire), and ask for a data flow diagram, subprocessors (third parties that handle data for you), retention terms, audit logs and a SOC 2 or ISO 27001 (an international security-management standard) report. The FDE's job is the evidence behind each answer (general industry practice; names as commonly used). → lesson 21 covers the production gaps that reviews find.
# - Residency is a deployment choice. A regional model endpoint can cost more per token, so the price belongs in the business case. → lesson 29.
# - An audit log must not hold the data it audits. Log the record id, the actor and the time, never the note text. → lesson 16.
# - Deletion must reach every copy, backups included. → lesson 17.
#
# Go deeper: a dedicated PII detector (Microsoft Presidio, which needs a spaCy model download) and the SOC 2 audit process itself.

# %% [markdown]
# ## Common mistakes
#
# - **Pointing the evidence at the wrong file.** A check that reads a missing path stops with an error. Never answer yes when the check raised one.

# %% tags=["raises-exception"]
# The access evidence lives in lesson 13's folder, apps/13, not apps/14.
SRC_WRONG = Path("../apps/14/customer_api.py").read_text()

# %% [markdown]
# The `FileNotFoundError` above is expected: the file is not at that path, and the notebook stops on purpose. In a pack script, fail closed instead: catch the error and turn it into a gap, so a missing file can never produce a yes.
#
# %%
try:
    ok = "TOKEN_SECONDS = 300" in Path("../apps/14/customer_api.py").read_text()
except OSError: ok = False  # an unreadable check is a gap, never a yes
print("Q6 check passes:", ok)

# %% [markdown]
# You should see False: the missing file becomes a gap.

# %% [markdown]
# - **Scanning the lab copy and calling it the production store.** The lab scan proves the check works. The reviewer wants it rerun on the store the customer's data really goes to.
# - **Writing the note text into the audit log.** The log then holds the personal data it was meant to protect. Log ids and times instead.

# %% [markdown]
# ## Production checklist
#
# - Every evidence check runs against the running service and the production store, not lab files.
# - Every answer has an owner and a review date. Evidence older than the last release becomes a gap.
# - Gaps go to the customer in writing, with a date. Nobody closes a gap with a yes.
# - Audit lines reach the customer's log store, and the retention rule covers them too.

# %% [markdown]
# ## Try it
#
# Someone adds a "helpful" audit line that puts the note text in. Write `unsafe_entry(note)` to build that entry, then run `audit_problems` on it. Predict the problems first.
#
# - **A:** `unsafe_entry` returns a dict with the same five fields plus `"note": note`.
# - **B:** print `audit_problems` for the entry made from the note `"Milk missing, call 555-0142"`.

# %%
# your code here
def unsafe_entry(note: str) -> dict:
    """The careless version: the same five fields, plus the note text."""

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def unsafe_entry(note: str) -> dict:
    entry = dict(entries[0])  # same five fields as a real line
    entry["note"] = note
    return entry

bad = unsafe_entry("Milk missing, call 555-0142")
print("problems:", audit_problems(bad))

# %% [markdown]
# The check flags the phone number in the log line, so Q5 would become a gap. The extra `note` key is not flagged on its own: `audit_problems` tests only for missing fields and for personal data or the word "secret" in the values, not for extra keys. Compare this with your prediction: the phone number is the reason, not the extra key. The fix is the audit helper from Step 4, which never takes the note text.

# %% [markdown]
# ## Recap
#
# - A questionnaire answer is a claim. Attach evidence a reviewer can rerun.
# - A gap is an honest answer. A yes without evidence is a finding.
# - Redact personal data before storage, and scan the stored copy.
# - The audit log records who, what, which record and when, never the content.
# - A SOC 2 report comes from an independent auditor. Send it, or say you do not have one.
# - **Interview:** "A customer's security team asks for SOC 2 evidence, data residency and audit logs before go-live. What do you send?" Strong answer: "A questionnaire where each answer points to evidence the reviewer can rerun: region settings checked against the contract, a scan of the stored copy, audit lines with actor, time and record id but no content. Gaps have owners and dates. I send a SOC 2 report only if an independent auditor issued one."
