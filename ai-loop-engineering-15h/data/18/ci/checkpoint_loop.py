"""Checkpoint loop: the Ralph loop (lesson 11) with a maker and a checker (14), retries (13) and a CI gate (17).

The notebook and CI (test_ci_gate.py) both import this file, so CI runs what the notebook ran."""
import hashlib, os, re, shutil, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

HERE = Path(__file__).resolve().parent                 # data/18/ci
TOPIC = HERE.parents[2]                                # the course folder
SRC = TOPIC / "data" / "pocket-cart"                   # read only: the generated repo
RUNS = HERE.parent / "runs"                            # run-time copies, one per run
PYTHON = os.path.abspath(sys.executable)               # the kernel may give a relative path
MAX_CALLS = 5                                          # model calls per run: the notebook's limit
GOLDEN = [  # one module per case; its test file is the spec
    {"id": "money", "scope": ["tests/test_money.py"]},
    {"id": "pricing", "scope": ["tests/test_pricing.py"]},
]
VERIFIER = ["tests/*.py", "pytest.ini"]                # the files the maker must never change

def git(work, *args):  # placeholder identity for local commits
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(name, resume=False):  # a copy of the repo with a commit named start: the undo point
    work = RUNS / name
    if resume and (work / ".git").exists():  # a real restart: keep the folder and its commits
        return work
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work, ignore=shutil.ignore_patterns("__pycache__"))
    git(work, "init", "-q"); git(work, "add", "-A"); git(work, "commit", "-q", "-m", "start")
    return work

def pytest_run(work, *args):  # the verifier: pytest with plain-text output
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    return subprocess.run([PYTHON, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *args],
                          cwd=work, capture_output=True, text=True, env=env).stdout

def failing(work, scope):  # the verifier's list of failing tests, in file order
    out = pytest_run(work, "--tb=no", "-rf", *scope)
    return [line[len("FAILED "):].split(" - ")[0] for line in out.splitlines() if line.startswith("FAILED ")]

def failure_text(work, node):  # the one failure the maker sees
    out = pytest_run(work, "--tb=short", node)
    return "\n".join(line for line in out.splitlines() if line.startswith("E "))[:600]

def verifier_digest(work):  # a fingerprint of the verifier files, compared after every attempt
    h = hashlib.sha256()
    for p in sorted(p for pat in VERIFIER for p in work.glob(pat)):
        h.update(p.relative_to(work).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]

class OutOfBudget(Exception):
    pass

def is_transient(err):  # rate limit, server error or timeout: the same call may work later
    return isinstance(err, (TimeoutError, ConnectionError)) or getattr(err, "code", None) in (429, 500, 502, 503, 504)

def apply(work, files, guard=True):  # write a proposal; with the guard on, a verifier file is refused, not written
    refused = [rel for rel in files if guard and (rel == "pytest.ini" or rel.startswith("tests/"))]
    for rel, text in files.items():
        if rel not in refused:
            (work / rel).write_text(text)
    return refused

def gate(work, case, todo, node, refused, baseline):  # the checks before the model checker
    if refused:
        return "write to a verifier file refused"
    if verifier_digest(work) != baseline:
        return "verifier files changed"
    after = failing(work, case["scope"])
    if node in after or not set(after) <= set(todo) - {node}:
        return "item not fixed, or a new failure"
    return ""

def ralph_case(work, case, maker, checker=None, guard=True, tries_per_item=2):
    """The Ralph loop on one case: one failing item per turn, pytest decides, the checker has the last word."""
    baseline, log, tries = verifier_digest(work), [], {}  # the baseline is taken before any model call
    while True:
        todo = failing(work, case["scope"])              # the verifier's list, never the model's claim
        if not todo:
            return {"case": case["id"], "stop": "done", "log": log}
        node = todo[0]
        if tries.get(node, 0) >= tries_per_item:
            return {"case": case["id"], "stop": "stuck", "log": log}
        tries[node] = tries.get(node, 0) + 1
        try:
            files = maker(work, node)                    # one proposal, fresh context
            refused = apply(work, files, guard)
            reason, verdict = gate(work, case, todo, node, refused, baseline), "-"
            if not reason and checker:
                verdict = checker(work, node)            # a second, fresh context: spec and diff only
                reason = "" if verdict == "pass" else f"checker said {verdict}"
        except OutOfBudget:
            return {"case": case["id"], "stop": "over_budget", "log": log}
        if reason:
            git(work, "checkout", "--", ".")             # revert every uncommitted edit
        else:
            git(work, "add", "-A"); git(work, "commit", "-q", "-m", f"keep {node}")
        log.append({"item": node.split("::")[1], "files": list(files), "checker": verdict,
                    "result": "reverted: " + reason if reason else "kept"})

FIX_SYSTEM = ("You fix one module of a small Python shop. Reply with the complete new text of that module: "
              "no prose and no code fences. The test file is the spec. Never change it.")
CHECK_SYSTEM = ("You review one change to a Python repo. You did not write it and you see nothing else. "
                "The test file is the spec. Fail the change if it special-cases test inputs or edits a test. "
                "Otherwise pass it if the code is right. Reply 'VERDICT: pass' or 'VERDICT: fail' on the first line, "
                "then one sentence of reason.")

@dataclass
class Judges:
    """The maker and the checker share one budget. Every model call, retries included, counts once."""
    llm: object
    max_calls: int = MAX_CALLS
    calls: int = 0

    @retry(retry=retry_if_exception(is_transient), stop=stop_after_attempt(3),
           wait=wait_exponential_jitter(initial=1, max=8), reraise=True)
    def ask(self, system, prompt):
        from langchain_core.messages import HumanMessage, SystemMessage
        if self.calls >= self.max_calls:
            raise OutOfBudget(f"{self.calls} of {self.max_calls} model calls used")
        self.calls += 1
        return self.llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])

    def maker(self, work, node):  # fresh context: this module, its test file and one failure
        module = work / ("pocket_cart/" + Path(node.split("::")[0]).name[len("test_"):])
        test_file = work / node.split("::")[0]
        prompt = (f"### MODULE {module.relative_to(work).as_posix()}\n{module.read_text()}\n"
                  f"### TEST FILE {test_file.relative_to(work).as_posix()}\n{test_file.read_text()}\n"
                  f"### FAILING TEST {node}\n{failure_text(work, node)}\n")
        text = self.ask(FIX_SYSTEM, prompt).text.replace("```python", "").replace("```", "").strip("\n") + "\n"
        return {module.relative_to(work).as_posix(): text}

    def checker(self, work, node):  # fresh context: the spec and this change, never the maker's reply
        test_file = work / node.split("::")[0]
        diff = git(work, "diff", "--", "pocket_cart")
        prompt = (f"### SPEC {test_file.relative_to(work).as_posix()}\n{test_file.read_text()}\n"
                  f"### CHANGE\n{diff}\n")
        m = re.search(r"VERDICT:\s*(pass|fail)", self.ask(CHECK_SYSTEM, prompt).text, flags=re.I)
        return m.group(1).lower() if m else "none"

def run_golden(work, judges, guard=True):
    """The golden set in order. A case the repo already marks done is skipped: a restart makes no model call for it."""
    report = []
    for case in GOLDEN:
        if f"case {case['id']} done" in git(work, "log", "--format=%s"):
            report.append({"case": case["id"], "stop": "skipped: done before", "calls": 0, "log": []})
            continue
        before = judges.calls
        res = ralph_case(work, case, judges.maker, judges.checker, guard)
        if res["stop"] == "done":
            git(work, "commit", "-q", "--allow-empty", "-m", f"case {case['id']} done")
        report.append({**res, "calls": judges.calls - before})
    return report

def run_ci(llm, name="ci", guard=True, resume=False):
    """The one run command: a fresh copy, the golden set and the budget. Returns the copy, the report and the judges.
    resume=True keeps the folder of an earlier run, so its finished cases are skipped; the default starts clean."""
    work = fresh_copy(name, resume)
    judges = Judges(llm)
    return work, run_golden(work, judges, guard), judges
