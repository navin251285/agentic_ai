# Build the course app: the Brightside support desk

The course builds one small app alongside the notebooks. It is a local FastAPI service with a one-page chat
page, and each chapter adds one step: the desk loop with caps (chapter 1), retries and a checker (chapter 2),
approvals and isolated runs (chapter 3), and the finished app that starts with one command (chapter 4). Every step runs with one
command and has tests that run offline.

Run every command from the topic folder `topics/ai-loop-engineering-15h` unless a step says otherwise. The
model settings come from the course `.env` (`GOOGLE_CLOUD_API_KEY`, or a Vertex AI project); the tests need no key.

## Step 1: Desk loop with caps and a stuck detector
**After chapter 1 · uses lessons 01–08** — the app answers a support question in a chat page: the model calls
`get_order` and `calculator`, every run stops on a named stop reason (answered, turn cap, token or dollar cap,
or stuck), and a loop that repeats a failed call is stopped by the stuck check.

### What you add
- `pyproject.toml`: the package and its dependencies (FastAPI, uvicorn, httpx, LangChain core, the Gemini chat package, python-dotenv).
- `src/brightside_desk/config.py`: reads the course `.env` once and returns the settings; placeholders count as not set.
- `src/brightside_desk/tools.py`: `get_order` (four invented orders) and `calculator` (arithmetic only, no `eval`), each with a pydantic schema; `run_tool` turns every failure into text the model reads.
- `src/brightside_desk/desk.py`: the loop with `Caps`, `Budget`, `stuck_reason` and `run_desk`. Each reply is counted once; caps are checked before a reply's tools run.
- `src/brightside_desk/llm.py`: builds the Gemini chat model at temperature 0. A missing key raises a clear error that names the setting.
- `src/brightside_desk/api.py`: `/health`, `POST /api/chat` and the page at `/`.
- `src/brightside_desk/static/index.html`: the chat page (a form, the stop reason, the turns, the answer, and each tool call).
- `tests/conftest.py` and `tests/test_step1_desk.py`: offline tests with FastAPI's `TestClient`; two recordings in `tests/cassettes/` replay the model calls.

### The code that matters
Each reply counts once, and the caps are checked before its tools run (lesson 05 and 08):
```python
reply = model.invoke(messages)            # one paid model call: the whole list is sent again
budget.count(reply)                       # one turn, its tokens, its dollars
if not reply.tool_calls:
    return _finish("answered", reply.text, None, budget, steps)
if cap := budget.exceeded():              # turn_cap, over_budget_tokens or over_budget_usd
    return _finish(cap, None, None, budget, steps)   # this reply's tools do not run
```

The stuck check reads its own steps (lesson 06). Two signals are enough here: the same call three times in a row, or the same error twice:
```python
errors = [text for s in steps for _, text in s.results if text.startswith("error")]
if len(errors) >= 2 and errors[-1] == errors[-2]:
    return "the same error twice, even with a success between"
```

A tool failure is text for the model, not an exception that ends the run (lesson 04). The calculator parses the
expression and never calls `eval`, so `__import__('os')` is refused:
```python
def safe_eval(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")   # parse only: names and calls are not evaluated
    return _eval_node(tree.body)                # numbers, + - * / and unary signs only
```

### Run it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pip install -q -e .
cd src
../../.venv/bin/uvicorn brightside_desk.api:app --reload --port 8980
```
Then open http://127.0.0.1:8980/ in a browser. Check the server from a second terminal:
```bash
curl -s http://127.0.0.1:8980/health
```

### Test it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pytest -q
```

### What you should see
The health check answers with the status, and the page is served as HTML:
```
{"status":"ok"}
page 200 text/html; charset=utf-8
```
A bad request is refused by the schema before any model call (`max_turns` must be 1 to 10, and the message cannot be empty):
```
{"detail":[{"type":"string_too_short","loc":["body","message"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]} 422
```
The recorded run of the question "What did customer C-17 pay for order BS-1042, and what is that doubled?" replays
in the tests. Printed from the same recording, the run looks like this:
```
status 200 | stop answered | turns 3 | usd 9.2e-05
turn 1 model asks: get_order({"order_id": "BS-1042"})
turn 1 tool get_order returns: {"order_id": "BS-1042", "customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"}
turn 2 model asks: calculator({"expression": "120 * 2"})
turn 2 tool calculator returns: 240
answer: Customer C-17 paid $120 for order BS-1042. Doubling that amount results in $240.
```
Ask the same question with a turn cap of 1 and the stop is `turn_cap`: the model asked for `get_order`, but the cap
stopped the loop before the tool ran, so `steps[0].results` is empty.

The test run ends with:
```
11 passed in 1.34s
```

## Step 2: Retries, idempotent refunds and a checker
**After chapter 2 · uses lessons 13, 14 and 17** — the desk can now refund. The model only proposes a refund with `issue_refund`; a plain-Python checker approves it against the order record; the payment service pays it once, retrying transient errors with backoff and one idempotency key per refund; and an offline eval gate fails when the checker or the retry path gets worse.

### What you add
- `src/brightside_desk/refunds.py`: the stand-in payment service (a SQLite ledger with a unique key column, and a `script` for 503s and lost replies), `pay_with_retry` (tenacity: transient errors only, four tries, exponential backoff with jitter), `check_refund` (the checker) and `review_and_pay` (checker first, then the paid write).
- `src/brightside_desk/evals.py`: the golden set of six refund cases, the gate, and `python -m brightside_desk.evals`, which exits 1 below the baseline.
- `evals/baseline.json`: the accepted pass rate (1.0). The gate only reads it.
- `src/brightside_desk/tools.py` (changed): `issue_refund` with a pydantic schema, and `propose_refund`, which turns the model's call into a proposal. The desk never runs the write itself.
- `src/brightside_desk/desk.py` (changed): a refund proposal ends the loop with the stop reason `refund_proposed`, and the proposal goes to the checker.
- `src/brightside_desk/api.py` and `config.py` (changed): `/api/chat` takes `payment_faults` (stand-in faults for this request), runs the checker and the payment for each proposal, and returns them as `refunds`. The ledger is at `data/app/ledger.db` in the course folder, made on the first refund.
- `static/index.html` (changed): a fault selector, and a refund box with the checker's reason and the payment result.
- `tests/test_step2_refunds.py` and `tests/test_step2_evals.py`, with `tests/cassettes/step2_refund_proposal.yaml`: the one model call of lesson 13, replayed. The tests need no key.
- `pyproject.toml` (changed): `tenacity>=9.1.4,<9.2`, the retry library the course pins.

### The code that matters
The write is idempotent because the provider keeps one row per key. A repeat returns the first result and writes nothing (lesson 13):
```python
with self.db:  # committed before the reply can be lost; a repeated key writes nothing
    cur = self.db.execute("insert or ignore into refunds (key, order_id, amount_usd) values (?, ?, ?)",
                          (key, order_id, amount_usd))
if cur.rowcount == 0:  # the key is already in the ledger: return the first result
```
Only transient errors are retried, with exponential backoff and jitter, and every try sends the same key (lesson 13):
```python
retrying = Retrying(retry=retry_if_exception_type(TransientPaymentError),
                    stop=stop_after_attempt(MAX_TRIES), wait=wait_exponential_jitter(initial=0.2, max=2, jitter=0.2),
                    before_sleep=_announce, reraise=True)
text = retrying(svc.refund, order_id, amount_usd, key)
```
The checker is plain Python. It sees the order record and the proposal, never the model's reasoning, and it keeps the total refunded within what was paid (lesson 14):
```python
left = round(paid - refunded_so_far, 2)
if round(amount_usd, 2) > left:
    return Verdict(False, f"{amount_usd} is more than the {left} still refundable on {order_id} (paid {paid})")
```
A refund is a write, so the loop stops at the proposal and hands it over (lessons 14 and 22 for approvals later):
```python
if proposals:  # the maker is done; the checker and the payment service decide the rest
    return _finish("refund_proposed", None, None, budget, steps, proposals)
```

### Run it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pip install -q -e .
cd src
../../.venv/bin/uvicorn brightside_desk.api:app --reload --port 8980
```
Then open http://127.0.0.1:8980/. Ask for a refund on BS-1042 (for example "Customer C-17 says the trail jacket from order BS-1042 arrived torn. Refund it."), and pick a payment fault to watch the retry. The chat calls the model, so it needs the key in the course `.env`. The eval gate runs with no key:
```bash
cd topics/ai-loop-engineering-15h/app/src
../../.venv/bin/python -m brightside_desk.evals
```

### Test it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pytest -q
```

### What you should see
The health check and the page are unchanged from step 1:
```
{"status":"ok"}
page 200 text/html; charset=utf-8
```
A fault the service does not know is refused before any payment is tried:
```
{"detail":[{"type":"literal_error","loc":["body","payment_faults",0],"msg":"Input should be '503' or 'lost_reply'","input":"timeout","ctx":{"expected":"'503' or 'lost_reply'"}}]} 422
```
The recorded run of the refund request, replayed from lesson 13's recording, with no faults. The model asks for one refund, the checker approves it, and the payment is made on the first try:
```
faults none | stop refund_proposed | turns 1
model asks: issue_refund({"amount_usd": 120.0, "order_id": "BS-1042"})
proposals: [{'order_id': 'BS-1042', 'amount_usd': 120.0}]
checker: approved | within the 120.0 still refundable on BS-1042
payment: refunded 120.0 on BS-1042 | tries 1
```
The same request with a lost reply. The first try is written but the reply is lost, the retry finds the key, and the refund is paid once. The log line shows the wait, which is random jitter, so it differs from run to run:
```
payment try 1 failed (read timeout: the write happened, the reply did not arrive); waiting 0.38 s
faults ['lost_reply'] | stop refund_proposed | turns 1
model asks: issue_refund({"amount_usd": 120.0, "order_id": "BS-1042"})
proposals: [{'order_id': 'BS-1042', 'amount_usd': 120.0}]
checker: approved | within the 120.0 still refundable on BS-1042
payment: already refunded 120.0 on BS-1042 | tries 2
```
Asking for the same refund again is refused by the checker, because nothing is still refundable on BS-1042. The eval gate prints one line per golden case and the verdict:
```
R1-full-refund-lost-reply        pass  verdicts [True]  paid 120.0
R2-more-than-paid                pass  verdicts [False]  paid 0.0
R3-partial-after-two-503s        pass  verdicts [True]  paid 40.0
R4-unknown-order                 pass  verdicts [False]  paid 0.0
R5-same-refund-asked-again       pass  verdicts [True, False]  paid 18.0
R6-two-partials-within-paid      pass  verdicts [True, True]  paid 40.0
pass rate 1.00 vs accepted baseline 1.00: pass
```
The test run ends with:
```
36 passed in 2.01s
```

## Step 3: Approvals, triggers and isolated runs
**After chapter 3 · uses lessons 19 to 24 (20 triggers and leases, 21 worktrees, 22 approvals, 23 permissions, 24 the checkpoint)** — the desk now runs unattended. A heartbeat adds each support ticket once, a worker claims it with a lease, and the run works in its own git worktree under a grant list of tools. A refund over 50 USD waits in an approval queue for a person, who approves it by echoing the amount or rejects it. A late answer is refused and the task goes back to the queue. Chat runs that a person starts by hand keep the step 2 behaviour (lesson 19: a run you start by hand needs no gate).

### What you add
- `src/brightside_desk/permissions.py`: the grant list per kind of run (`scheduled-desk` may read orders, calculate and propose a refund; nothing else), and `permit`, which fails closed for an unknown run or tool.
- `src/brightside_desk/taskqueue.py`: the task queue in SQLite. `heartbeat` adds a ticket once; `claim` takes an open or lapsed task in one write transaction and sets an owner and an attempt; `park`, `finish` and the other writes check the owner, the attempt and the lease in the same transaction (the fenced write of lesson 20).
- `src/brightside_desk/workspace.py`: the desk's git repo. Each run gets one worktree and one branch from `main`; a case file is committed on the branch; the reviewer reads the branch's diff; an approval merges it.
- `src/brightside_desk/scheduled.py`: `ScheduledDesk.tick` (the heartbeat and the worker), `decide` (the approval gate), and `Ticker`, a timer that runs `tick` every `APP_TICK_S` seconds (off by default).
- `src/brightside_desk/desk.py` (changed): `run_desk` takes an `allowed` check; a refused tool gets a "denied" message and never runs.
- `src/brightside_desk/config.py` and `api.py` (changed): the approval limit, the lease, the review window and the timer come from the `.env` or the environment (`APP_APPROVAL_LIMIT_USD`, `APP_LEASE_S`, `APP_REVIEW_WINDOW_S`, `APP_TICK_S`), with the defaults 50, 90, 3600 and 0. The endpoints are `POST /api/tick`, `GET /api/tasks`, `GET /api/approvals`, `POST /api/approvals/{ticket}` and `GET /api/permissions`.
- `static/index.html` (changed): a "Scheduled runs and approvals" panel with the grant lists, the tick button, the tasks, and each pending approval with its diff and an amount to echo.
- `tests/test_step3_queue.py` and `tests/test_step3_scheduled.py`: the queue, the leases, the grant check, and the whole gate on one replayed model call (lesson 13's recording, `step2_refund_proposal`). The tests need `git`.

The approval queue is a table row, not a LangGraph `interrupt()` as in lesson 22. The reason is the lease: the parked run's state and its owner are one row, so the lease check and the merge can share one transaction. The gate's rules are the same as lesson 22's: the reviewer sees the real arguments, the echoed amount must match, and an answer after the window is refused.

### The code that matters
A run that waits for a person holds its lease for the review window. The approval checks the lease in the same transaction as the merge, so a late answer changes nothing (lessons 20 and 24):
```python
with transaction(db):  # BEGIN IMMEDIATE: the write lock comes before the read
    row = get_task(db, ticket)
    if row["lease_until"] < now:  # the window closed: nothing merges, the task goes back to the queue
        requeue(db, ticket, "review window closed: the task went back to the queue")
```
The reviewer must echo the amount they were shown. A different amount is refused before any merge or payment (lesson 22):
```python
if amount_usd is None or round(amount_usd, 2) != total:
    raise AmountMismatch(f"approve by echoing the amount shown: {total} USD")
self.repo.merge(row["branch"])  # inside the transaction: the lease was checked just above
```
Each run is one worktree and one branch from `main`, created from a known commit, so runs cannot overwrite each other (lesson 21):
```python
self.repo.add_run(branch, folder)  # git worktree add -b run/TK-2201-a1 <folder> main
```
The grant list is fixed in code, and the runner checks every call against it. The model is shown the granted tools, but the check is what stops a call (lesson 23):
```python
def permit(run: str, tool: str) -> tuple[bool, str]:
    grants = GRANTS.get(run)
    if grants is None:
        return False, f"no run named {run}"  # an unknown run gets nothing
    if tool not in grants:
        return False, f"{tool} is not granted to {run}"
    return True, "granted"
```

### Run it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pip install -q -e .
cd src
../../.venv/bin/uvicorn brightside_desk.api:app --reload --port 8980
```
Then open http://127.0.0.1:8980/ and scroll to "Scheduled runs and approvals". Click **Run the scheduled tick**: the heartbeat adds ticket TK-2201 and one scheduled run makes its one model call, so the tick needs the key in the course `.env`. The run's refund is over 50 USD, so it waits under "Waiting for a reviewer", with its diff. Approve it with the amount shown, or reject it. To tick on a timer, start uvicorn with `APP_TICK_S=60` in the environment. The endpoints can be checked with no key:
```bash
curl -s http://127.0.0.1:8980/health
curl -s http://127.0.0.1:8980/api/permissions
curl -s http://127.0.0.1:8980/api/tasks
```

### Test it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pytest -q
```

### What you should see
The health check, the page and the grant lists answer with no key. Before the first tick, the queue is empty:
```
{"status":"ok"}
page 200 text/html; charset=utf-8
{"desk-chat":["calculator","get_order","issue_refund"],"scheduled-desk":["calculator","get_order","issue_refund"]}
{"tasks":[]}
```
A decision on a ticket that does not exist is refused, and a decision that is not approve or reject is refused by the schema:
```
{"detail":"no task TK-9999"}
422
```
The recorded run of lesson 13's request, replayed through the scheduled path in a fresh state folder. The tick makes one call, and the refund waits at the gate instead of being paid:
```
[approve] tick 1: added 1, runs [('TK-2201', 'waiting', 1)]
[approve] window closes at t=3600; ledger refunds before the decision: 0
[approve] reviewer sees: TK-2201 attempt 1, total 120.0 USD, proposals [{'order_id': 'BS-1042', 'amount_usd': 120.0}]
[approve] diff first line: cases/TK-2201.json | 14 ++++++++++++++
[approve] decision: 200 outcome paid | reason: refunded 120.0 on BS-1042
[approve] ledger refunds written: 1 | record on main: True | branches: ['main', 'run/TK-2201-a1']
[approve] tasks: [('TK-2201', 'paid', 1)]
[approve] tick 2 (no model call): added 0, runs []
[approve] approve again: 409 TK-2201 is paid, not waiting for a decision
```
The same run with the amount echoed wrongly. The gate refuses it, and nothing is merged or paid until the reviewer echoes 120.0:
```
[mismatch] echo 100.0: 409 approve by echoing the amount shown: 120.0 USD
```
Rejecting it keeps the branch as the record and pays nothing:
```
[reject] decision: 200 outcome rejected | reason: rejected by the reviewer
[reject] ledger refunds written: 0 | record on main: False | branches: ['main', 'run/TK-2201-a1']
```
An answer after the one-hour window is refused, and the task goes back to the queue, where the next tick claims it again as attempt 2:
```
[lapsed] decision: 409 review window closed: the task went back to the queue
[lapsed] ledger refunds written: 0 | record on main: False | branches: ['main', 'run/TK-2201-a1']
[lapsed] tasks: [('TK-2201', 'open', 1)]
```
The test run ends with:
```
53 passed in 3.47s
```

## Step 4: Finish and run it
**After chapter 4 · uses lessons 25 to 30 (the Enterprise part; its labs stay in the notebooks, and the app keeps the step 3 queue)** — the whole app starts with one command, `python -m brightside_desk`, serves the page and the API on port 8980, and passes its 64 offline tests. Nothing new is added to the desk itself: this step makes the first three steps easy to run, test and read.

### What you add
- `src/brightside_desk/__main__.py`: the one run command. `python -m brightside_desk` (or the `brightside-desk` script that `pip install -e .` makes) starts uvicorn on `APP_HOST` and `APP_PORT`; `--port` overrides the port for one run, and `--reload` restarts on code changes while you develop.
- `src/brightside_desk/config.py` (changed): two settings, `APP_HOST` (default `127.0.0.1`) and `APP_PORT` (default `8980`). A port that is not a number from 1 to 65535 is refused with the setting's name in the message.
- `pyproject.toml` (changed): the `brightside-desk` script.
- `src/brightside_desk/api.py` (changed): the docstring names the one command. The routes are the same.
- `tests/test_step4_run.py`: the settings, the run command with a fake server, `/health` and the page through `TestClient`, and one end-to-end test that starts `python -m brightside_desk` on a free port and reads `/health`.
- `README.md` (rewritten for the finished app): what it does, the one run command, what you see on the page, the test command, and what you built.

No model call is made in this step: the tests replay the recordings of steps 1 to 3, and `/health` and the page need no key.

### The code that matters
One command starts the app with the settings from the course `.env` (lessons read their settings from that file, never from the code). The host and port come from the environment, and `main` is the only place that starts the server, so a test can check the call without a real server:
```python
def main(argv: list[str] | None = None) -> int:
    args = parser.parse_args(argv)
    settings = load_settings()  # a bad APP_PORT stops here, with the setting's name in the message
    port = args.port if args.port is not None else settings.port
    uvicorn.run("brightside_desk.api:app", host=settings.host, port=port, reload=args.reload, log_level="info")
    return 0
```

A bad setting is refused by name, and its value is never printed (the same rule as steps 1 to 3):
```python
if not raw.isdigit() or not 1 <= int(raw) <= 65535:
    raise ValueError(f"{name} must be a port number from 1 to 65535 (see the course .env file)")
```

The end-to-end test checks the app the way a learner runs it. It starts the real server on a free port, waits for `/health`, and stops the server:
```python
proc = subprocess.Popen([sys.executable, "-m", "brightside_desk", "--port", str(port)], cwd=APP, ...)
body = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).json()
assert body == {"status": "ok"}
```

### Run it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pip install -e .
../.venv/bin/python -m brightside_desk
```
Then open http://127.0.0.1:8980/ in a browser. In a second terminal, check the server:
```bash
curl -s http://127.0.0.1:8980/health
```
Stop the server with Ctrl+C in the terminal where it runs. To use another port for one run, add `--port 8990`. To restart on code changes while you develop, add `--reload`.

### Test it
```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pytest -q
```

### What you should see
The server starts, logs the address it serves, and waits for requests:
```
2026-10-28 08:41:25,940 INFO brightside_desk: serving the desk on http://127.0.0.1:8980/ (health: /health)
INFO:     Started server process [110734]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8980 (Press CTRL+C to quit)
```
The health check and the page answer:
```
{"status":"ok"} 200
page 200 text/html; charset=utf-8
```
The server log of the run shows the requests, then the clean stop:
```
INFO:     127.0.0.1:57948 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:57962 - "GET / HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Application shutdown complete.
```
Before the first line, the run also printed one dotenv warning: the course `.env` has a line that is neither `NAME=value` nor a comment (its first line), so python-dotenv skips it with `could not parse statement starting at line 1`. The app does not need that line. To silence the warning, put a `#` in front of it in the course `.env`.

The full test run ends with:
```
64 passed in 4.83s
```
