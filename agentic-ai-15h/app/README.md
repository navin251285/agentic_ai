# Brightside support desk (course app)

A local FastAPI service with a one-page web UI, run with one command. Nothing else is needed: no Docker, no
Node, no database server. The app answers support questions for a small shop, Brightside, in three parts:

- **Order lookup.** You ask about an order; an agent looks it up with a tool, uses a calculator for sums, and stops
  at a step cap or a spend cap.
- **Refund desk.** The desk answers from the refund policy with the passages it cites, remembers the customer's
  facts, and pauses a refund over $50 until a senior lead approves it. A refund is paid once per order, even after
  a restart.
- **Traces and cost.** Every question and decision leaves a trace: the model calls with their tokens, the tool
  calls with what the desk decided. A dashboard shows one row per ticket, the cost per ticket and the p95 time,
  and a policy check runs before every tool call.

`GUIDE.md` builds the app one step per chapter and explains each file.

## Run it

From the course folder, after the course setup in `../README.md` (the one-time install is `.venv/bin/python -m pip install -e app`):

```bash
cd topics/agentic-ai-15h
.venv/bin/python -m support_desk
```

Then open http://127.0.0.1:8980/ in a browser. Stop the app with Ctrl+C. The health check answers at
http://127.0.0.1:8980/health.

The port is `SUPPORT_PORT` (default 8980). Settings come from the course's `.env` (see `../.env.example`):

| Setting | What it does | Default |
|---|---|---|
| `SUPPORT_MAX_STEPS` | model calls per chat turn (the step cap) | 4 |
| `SUPPORT_MAX_USD` | money per chat turn, estimated from each reply's usage (the spend cap) | 0.01 |
| `SUPPORT_ORDERS_FILE` | the small order world the tools read | `data/support_eval.json` |
| `SUPPORT_POLICY_FILE` | the policy passages the desk searches | `data/ftc_chunks_embeddings.json` |
| `SUPPORT_STATE_DIR` | the saved memory, refunds, runs and traces | `app/state/` |
| `SUPPORT_PORT` | the port the app listens on | 8980 |

Keys: the app never needs one for the recorded questions. Questions that were recorded by the course replay offline
from `tests/cassettes/`. For any other question, `GOOGLE_CLOUD_API_KEY` in `.env` records it once, one model call at a
time. Without the key, an unrecorded question is refused with `503`; it is never answered with an invented reply.

The app's saved state (`app/state/`: the customer memory, the refund ledger, the saved runs and `traces.jsonl`) is
created on first use and is never committed. To start clean, stop the app and delete that folder.

## What you'll see

- **The header and the order lookup.** A chat box under the title "Order lookup". Ask "Where is my parcel for order
  1002? It was due on Monday." Your question appears in a blue-shaded line, the answer below it, and under the answer a line
  for each tool call with its result, such as `lookup_order({"order_id":"1002"})`.
- **The refund desk.** A customer box (C-88 by default), a box to remember a fact, and a pre-filled request for
  order 1007. Ask the desk and the answer appears with the cited policy passages, `[policy-27, policy-31]`, and a
  status line with the stop reason, the model calls and the cost. A refund over $50 shows an approval panel with a
  "Decided by" choice (agent-desk-1 or senior-lead), Approve and Refuse. Only a senior lead's approval pays the refund.
- **The traces and cost table.** A line above the table with the tickets, the answered rate, the cost per ticket and
  the p95 time. Each ticket is one row with its outcome, model calls, tool calls, refusals, cost and time. Click a row
  to see its span tree: the question's model calls and searches, then the decision and the refund's policy check.

Read the answer against the calls. A reply's words are not the end state: the calls list and the trace show what the
app really did. This app has no email tool, so a reply that promises a follow-up email is wrong, and the calls show it.

## Test it

The tests run offline (model calls replay the recordings; no key, no network):

```bash
cd topics/agentic-ai-15h/app
../.venv/bin/python -m pytest -q
```

They call the API through FastAPI's `TestClient`: the chat, the desk, the approvals and restarts, the policy guard,
the 20 injection attacks, the traces, and the run command.

## Layout

```
app/
  pyproject.toml          the package (support-desk) and its dependencies
  src/support_desk/
    __main__.py           python -m support_desk: the one run command
    api.py                the FastAPI app: the page, /health and every /api route
    agent.py              the step-1 agent loop with the step and spend caps
    tools.py              lookup_order and calculator, with schemas that refuse bad input
    policy.py             the policy search (cited passages)
    memory.py             the customer memory, with the card and password guard
    ledger.py             the refund ledger: one payment per order, saved in sqlite
    desk.py               the desk graph (LangGraph) with the approval pause
    guard.py              scopes and the refund policy, checked before every tool call
    observe.py            the tracer, the dashboard rows, the cost and the p95 time
    course.py             the bridge to the course's llm_setup.py, llm_replay.py and tut_env.py
    settings.py           the settings, read from the environment and the course's .env
    static/index.html     the one-page UI, served by the API (plain HTML and JavaScript)
  tests/                  the offline tests and the recordings (cassettes/)
  GUIDE.md                the step-by-step guide
```

## What you built

Over four steps you built one service that does three jobs with the same model:

1. **An agent that uses tools and stops** (chapters 1 to 2): a chat with an order lookup and a calculator, with a step
   cap and a spend cap that stop a run and say why.
2. **Answers you can check, and money that waits for a person** (chapters 3 to 4): policy answers with the passages they
   cite, a customer memory that refuses card numbers and passwords, and a refund that pauses for a senior lead and is
   paid once per order, even across restarts.
3. **Traces, a cost meter and a policy check** (chapter 5): every call is traced, every ticket has a cost, the
   dashboard shows the answered rate against a target, and the guard refuses a refund the policy forbids before any
   person is asked to approve it. The 20 injection attacks of the course move no money.
4. **One command and a finished test suite** (chapter 6): `python -m support_desk` starts all of it, `/health` reports it,
   and the 71 offline tests check each part, including every route the page calls.

The app does not do tenant isolation, a signed agent identity or a hash-chained audit log; those are left to the course's
later lessons and to a production build. It also does not deploy anywhere: running it in a container or on a cloud is a
course of its own.
