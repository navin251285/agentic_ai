# Brightside support desk (course app)

A local FastAPI service with a one-page web UI. It is the app of the AI loop engineering course, built one step per
chapter (see `GUIDE.md` for the step-by-step build). What it does:

- **The desk loop** (chapter 1): a model answers a support question with three tools (`get_order`, `calculator`,
  `issue_refund`, which only proposes). Caps on turns, tokens and dollars stop every run on a named stop reason, and
  a stuck check stops a loop that repeats a failed call.
- **Refunds** (chapter 2): a proposed refund goes to a plain-Python checker, then to a stand-in payment service that
  retries transient errors and pays each refund once (one idempotency key per refund). An offline eval gate guards it.
- **Scheduled runs and approvals** (chapter 3): a heartbeat adds each support ticket once, a worker claims it with a
  lease, and each run works in its own git worktree under a grant list of tools. A refund over 50 USD waits for a
  person, who approves it by echoing the amount, or rejects it.

## Run it (one command)

You need Python 3.12 and the topic's virtual environment (`topics/ai-loop-engineering-15h/.venv`). Install the app once:

```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pip install -e .
```

Then start the app. This one command serves the API and the page:

```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m brightside_desk
```

It listens on http://127.0.0.1:8980/ (the course port). Open that address in a browser for the page, and check the
server from a second terminal:

```bash
curl -s http://127.0.0.1:8980/health
```

Settings come from the course `.env` (or the environment): `GOOGLE_CLOUD_API_KEY` (or a Vertex AI project) for the
model, `APP_PORT` and `APP_HOST` for the address, `APP_APPROVAL_LIMIT_USD`, `APP_LEASE_S`, `APP_REVIEW_WINDOW_S` and
`APP_TICK_S` for the scheduled runs. Use `--port 8990` to change the port for one run, and `--reload` while you develop.
The app works without a key for everything except asking the model: `/health`, the page, the permissions, the tasks
and the eval gate need none. Stop the server with Ctrl+C.

## What you'll see

- **The header and the question box.** The title "Brightside support desk", a short line about what the desk does,
  a text box, a turn cap (6 by default), a menu of payment faults, and a **Send** button.
- **A chat answer.** A badge with the stop reason (for example `answered` in green, or `turn_cap` or `stuck` in red,
  or `refund_proposed` in yellow), then each turn: the tool the model asked for and what the tool returned, then the
  answer in a grey box.
- **A refund box.** When the model proposes a refund, the checker's verdict (approved, or refused with the reason)
  and the payment result (`refunded` on the first try, or `already refunded` when a lost reply was retried).
- **Scheduled runs and approvals.** A section with the grant list of each kind of run, a **Run the scheduled tick**
  button, the tasks table (ticket, status, attempt), and each refund waiting for a reviewer with its diff and an
  amount box to echo, and **Approve** and **Reject** buttons.

## Test it (offline)

```bash
cd topics/ai-loop-engineering-15h/app
../.venv/bin/python -m pytest -q
```

The tests need no key and no network. Model calls replay the recordings in `tests/cassettes/` (each at most five
calls, made once with `llm_replay`). The scheduled-run tests and the git worktree need `git` on the path. The last
test starts the real server with `python -m brightside_desk` on a free port and stops it again.

## What you built

- A FastAPI app with `/health`, `/api/chat`, `/api/tick`, `/api/tasks`, `/api/approvals`,
  `/api/approvals/{ticket}`, `/api/permissions`, and the page at `/`.
- Caps and a stuck check around a model loop with three tools, each failure returned to the model as text.
- Refunds that are proposed, checked, retried with backoff and paid once, with an eval gate that fails on regressions.
- Unattended runs: a task queue with leases and fenced writes, one git worktree per run, a grant list of tools checked
  on every call, and a human approval gate with a review window.
- One command to run it, and 64 offline tests across the four steps.

## Layout

- `src/brightside_desk/__main__.py`: the one run command (`python -m brightside_desk`, or the `brightside-desk` script)
- `src/brightside_desk/config.py`: settings from the environment and the course `.env`
- `src/brightside_desk/tools.py`: `get_order`, `calculator`, `issue_refund` (a proposal), schema checks, `run_tool`
- `src/brightside_desk/desk.py`: the loop, the caps, the stuck check, the stop reasons
- `src/brightside_desk/llm.py`: the Gemini chat model
- `src/brightside_desk/refunds.py`: the payment stand-in ledger, retries with backoff, the checker, `review_and_pay`
- `src/brightside_desk/evals.py`: the golden refund set and the eval gate (`python -m brightside_desk.evals`)
- `src/brightside_desk/permissions.py`: the grant list of each kind of run, checked on every tool call
- `src/brightside_desk/taskqueue.py`: the task queue: heartbeat, leases, fenced writes (SQLite)
- `src/brightside_desk/workspace.py`: the desk's git repo: one worktree and one branch per run, the reviewer's diff
- `src/brightside_desk/scheduled.py`: scheduled runs, the approval gate, the optional timer (`APP_TICK_S`)
- `src/brightside_desk/api.py`: the FastAPI routes and the page at `/`
- `src/brightside_desk/static/index.html`: the one-page UI (plain HTML and JavaScript)
- `evals/baseline.json`: the accepted pass rate the gate reads
- `tests/`: TestClient tests, one file per step, and the replayed recordings

The app runs locally. Container and cloud deployment are not part of this course.
