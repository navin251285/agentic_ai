# Basket Bazaar delivery-issue triage (course app)

A local FastAPI backend and one web page for the Basket Bazaar support team. An agent pastes a customer message about a delivery (missing, wrong or late items). A model reads it, looks up the order with a tool, and fills a case form. A plain-code check then decides whether the case opens or needs a person. Every case is stored once, the page lists the stored cases, and the app keeps logs, a trace per request and an eval gate.

Nothing is deployed. The app runs on your computer with one command, and it reads the course's own `.env`, data and model setup.

The app was built one step per chapter. The step-by-step build, with the commands and the real output at each step, is in [GUIDE.md](GUIDE.md).

## Start it

From the course folder, with the course venv (install the app once, then start it):

```bash
.venv/bin/python -m pip install -e app
.venv/bin/python -m delivery_triage
```

The command first checks what the app needs and prints one line per check, never a value:

```text
Checking the app before it starts:
  ok   orders file: 120 orders
  ok   tenants file: 12 stores
  ok   service token: set
  ok   model access: set
  ok   eval gate files: found
Open http://127.0.0.1:8980/ in your browser. Stop the server with Ctrl+C.
```

Open http://127.0.0.1:8980/ in a browser. Stop the server with Ctrl+C. Two more forms of the same command:

```bash
.venv/bin/python -m delivery_triage --check     # the checks only, then stop
.venv/bin/python -m delivery_triage --reload    # restart on file changes, for development
```

After the install, `delivery-triage` runs the same command from any folder.

A `stop` line means the app will not start (the orders file or the tenants file is wrong). A `warn` line means it starts, and the page or the API says what to set: the service token (`TRIAGE_SERVICE_TOKEN` in the course `.env`) or the model key (`GOOGLE_CLOUD_API_KEY`, or `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`).

## What you'll see

The page has one column, in this order:

- **Service token.** A password box at the top, with the note "The browser keeps it for this tab only." Until you paste the token from the course `.env`, a red message box under the form says: "The service token is missing or wrong. Send it as 'Authorization: Bearer <token>'. (code: unauthorized)". After you paste it, the **Store** list fills in.
- **The form.** A **Store** dropdown (store 02 is chosen by default, each store shows its limit per line), then the customer message, already filled in with an invented milk example, and a **Triage this message** button.
- **The result.** A green **Case opened** badge for a message whose order checks out, with "Stored as DI-00001.", then the order, the issue, the item, the quantity claimed, a one-line summary and a **Trace** id. An amber **Needs a person to review** badge means the check rejected the record, and a bullet list says why, for example "order BB-1108 belongs to another store, not store-07". That case is stored too, as its own case.
- **The eval gate.** A **Check the eval gate** button. It answers **Passed: 100% of 12 cases right (bar 90%).** when enough of lesson 11's labelled cases get the right label, or **Blocked** with the case ids that were wrong.
- **Stored cases.** A table, newest first: case, store, order, issue, status and the time it was stored. The **Refresh list** button reloads it. Triaging the same message for the same store again says the case "was already stored as DI-00001, so nothing new was written."

## The API

Every `/api` route needs the service token: `Authorization: Bearer <TRIAGE_SERVICE_TOKEN>`. `/health` and the page stay open.

| method and path | what it does |
|---|---|
| `GET /health` | status, version, orders loaded, cases stored, and whether the token is set (a yes or no, no value) |
| `GET /api/tenants` | the stores, each with its limit per line, and the default store |
| `POST /api/triage` | body `{"message": "...", "tenant": "store-07"}` (tenant optional); returns the status, the case id, whether it was a duplicate, the record, the problems and the trace id |
| `GET /api/issues?limit=20` | the newest stored cases |
| `GET /api/issues/{case_id}` | one stored case |
| `GET /api/evals/gate` | the eval gate's result: passed or not, the pass rate, the bar and the failed case ids |

Example, from a second terminal with the token exported (`export TRIAGE_SERVICE_TOKEN='...'`):

```bash
curl -s -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" http://127.0.0.1:8980/api/tenants
```

## Settings (the course `.env`)

- `GOOGLE_CLOUD_API_KEY`, or `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`: the model access from lesson 06. Without them the page says the model is not set up.
- `TUT_LLM_MODEL`: the model id the course uses.
- `TRIAGE_SERVICE_TOKEN` (required for `/api`): the token every `/api` call sends. Make one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Empty means `/api` answers 503 until it is set.
- `TRIAGE_PORT` (optional): the port. Default: 8980.
- `TRIAGE_ORDERS_FILE` (optional): the orders file. Default: `data/05/orders_clean.csv`, written by lesson 05.
- `TRIAGE_TENANTS_FILE` (optional): the per-store limits. Default: `app/config/tenants.json`.
- `TRIAGE_STORE_FILE` (optional): where the cases are stored. Default: `data/app/issues.csv`, created by the first triage.
- `TRIAGE_TRACE_FILE` (optional): where the spans are written, one JSON line each. Default: `data/app/traces.jsonl`.
- `TRIAGE_MODEL_ATTEMPTS` (optional): how many tries a model call gets when it fails in a way a later try can fix. Default: 4.
- `TRIAGE_EVAL_SET_FILE`, `TRIAGE_EVAL_RESULTS_FILE`, `TRIAGE_EVAL_MIN_PASS_RATE` (optional): lesson 11's eval set and labels, and the gate's bar. Defaults: `data/11/eval_set.csv`, `data/11/scored_v2.json`, `0.9`.

Keys and tokens are never printed, stored in the app's files or written to a log. The customer's message text is not logged and not put in a trace.

## Errors

Every error answers with a plain `detail` and a stable `code`:

| code | status | when |
|---|---|---|
| `invalid_request` | 422 | the message is empty or too long |
| `unauthorized` | 401 | the service token is missing or wrong |
| `auth_not_configured` | 503 | `TRIAGE_SERVICE_TOKEN` is not set in the course `.env` |
| `unknown_tenant` | 404 | the store is not on the tenants list; no model call was made |
| `model_not_configured` | 503 | no model key in the course `.env` |
| `model_busy` | 503 | the model stayed busy or unreachable after all tries; nothing was stored |
| `model_reply_invalid` | 502 | the model's reply did not fit the case form; nothing was stored |
| `model_failed` | 502 | the model refused the call (for example a bad request); see the server log |
| `case_not_found` | 404 | no stored case has that id |
| `eval_files_missing` | 409 | the gate's eval files from lesson 11 are not there yet |
| `store_failed` | 500 | the cases file could not be written |

## Tests

The tests run offline, with no live model calls and no real token:

```bash
cd app
../.venv/bin/python -m pytest -q tests
```

The two step 1 triage tests replay recorded model calls from `tests/cassettes/`. The other tests use a small fake model. The tests write their cases and traces to temporary files, never to the course's `data/app/`.

The eval gate runs on its own, from `app/src`, and exits 0 when it passes:

```bash
../../.venv/bin/python -m delivery_triage.evals
```

## Files

- `src/delivery_triage/__main__.py`: the one start command and its checks.
- `src/delivery_triage/api.py`: the FastAPI app, the routes, the service-token check and the error mapping.
- `src/delivery_triage/triage.py`: the triage flow: the model asks for the order, fills the form, and the check decides.
- `src/delivery_triage/orders.py`: the orders file and the plain-code check (order exists, belongs to the store, item and count).
- `src/delivery_triage/store.py`: the cases file, one row per case, with the stable key and the store.
- `src/delivery_triage/retries.py`: retries for the failures a later try can fix.
- `src/delivery_triage/tenants.py`: the per-store limits and their checks.
- `src/delivery_triage/evals.py`: the eval gate.
- `src/delivery_triage/observability.py`: JSON log lines with the trace id, and the trace file.
- `src/delivery_triage/models.py`, `errors.py`, `config.py`: request and response shapes, the one error shape, and the settings.
- `src/delivery_triage/static/index.html`: the one page.
- `config/tenants.json`: the per-store limits (invented numbers, no secrets).
- `tests/`: the tests, with two recorded model calls in `tests/cassettes/`.

## What you built

- **A triage that checks the model.** The model may only ask for the order and fill a form; the form has fixed fields (Pydantic), and plain code decides whether a case opens (lessons 05, 06).
- **Cases that are stored once.** A stable key (store, order, item, issue) stops duplicates; an old cases file is upgraded in place (lesson 05).
- **Failures a person can act on.** Retries only for failures a later try can fix, one error shape with stable codes (lessons 04, 11).
- **Access that is checked.** A service token on every `/api` route, compared in constant time, and nothing logged about it (lesson 13).
- **Per-customer rules.** Each store has its own limit, an order from another store needs a person, and a store that is not on the list is refused before any model call (lesson 23).
- **Evidence for a change.** A trace per request with one span per step, JSON log lines with the trace id, and an eval gate that blocks a change when too many labelled cases are wrong (lessons 11, 12, 16).
- **One start command.** It checks the files and settings, says what is missing, and starts the server with the page (the course's run-it-yourself rule).
