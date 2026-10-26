# Building the Basket Bazaar triage app, step by step

This guide builds one small app alongside the course. The notebooks teach each idea. The app shows how the same idea is built as a real service: a FastAPI backend, configuration from the course `.env`, tests, and one web page. Each step adds a chapter's work and tells you how to run and test it. Follow the steps in order.

The app lives in `app/` inside the course folder and reuses the course's own `tut_env.py` and `llm_setup.py`. Nothing is deployed: it runs on your laptop with one command.

## Step 1: A local triage API
**After chapter 1 · uses lessons 05 and 06** — after this step, one endpoint triages one customer message with a model call and a plain-code check, and a web page shows the result.

### What you add
- `app/pyproject.toml`: the app's name and dependencies (FastAPI, uvicorn, httpx, Pydantic, LangChain for the model, pytest for the tests).
- `app/src/delivery_triage/api.py`: the FastAPI app. It serves `/health`, the triage endpoint `POST /api/triage`, and the web page at `/`.
- `app/src/delivery_triage/triage.py`: the lesson 06 flow. The model asks for the order with a tool, fills the case form, and the check runs.
- `app/src/delivery_triage/orders.py`: loads the orders file that lesson 05 wrote, and the check that runs after the model.
- `app/src/delivery_triage/models.py`: the case form (`CaseRecord`) and the request and response shapes.
- `app/src/delivery_triage/config.py`: reads the settings from the course `.env`. Nothing is typed in the code.
- `app/src/delivery_triage/static/index.html`: the one page. A form, a result area, and `fetch` calls to the API.
- `app/tests/`: the tests, with two recorded model calls in `app/tests/cassettes/`.
- `app/README.md`: what the app is and how to run it.

### The code that matters
The model never looks up the order itself. It asks a tool, and our code runs the tool and sends the answer back (lesson 06, step 3 and 4):

```python
first = llm.bind_tools([lookup]).invoke(asked)          # model call 1: the model asks for the order
for call in first.tool_calls:
    history.append(ToolMessage(content=lookup.invoke(call["args"]), tool_call_id=call["id"]))
form = llm.with_structured_output(CaseRecord, method="json_schema")
record = form.invoke(history + [("human", FORM_REQUEST)])  # model call 2: the model fills the form
```

The form is a Pydantic class. The model must fill it, and Pydantic refuses a wrong type (lesson 06, step 2):

```python
class CaseRecord(BaseModel):
    order_id: str = Field(description="the order number as written, such as BB-1108")
    issue: Literal["missing_item", "wrong_item", "late", "damaged", "other"]
```

The check is plain code. It compares the record with the orders file and never asks the model (lesson 06, step 6):

```python
problems = check_record(record, orders)          # empty list = passed
status = "needs_review" if problems else "opened"
```

The settings come from the course `.env` through `tut_env`, so no key is written in the app (the same rule as every lesson, see `standards/NOTEBOOK_RULES.md`):

```python
return Settings(orders_file=orders, port=int(env("TRIAGE_PORT", str(DEFAULT_PORT))))
```

### Run it
Install the app into the course venv, then start the server from `app/src`. The port is the first one of this course's app range (8980).

```bash
.venv/bin/python -m pip install -e app
cd app/src
uvicorn delivery_triage.api:app --reload --port 8980
```

Leave the server running. Open http://127.0.0.1:8980/ in a browser. To check the API from a second terminal:

```bash
curl -s http://127.0.0.1:8980/health
```

The page needs a model key in the course `.env`: `GOOGLE_CLOUD_API_KEY`, or `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. `TUT_LLM_MODEL` is already used by the course. Without a key the page shows that the model is not set up.

### Test it
The tests run offline. The two triage tests replay the model calls recorded in `app/tests/cassettes/`, so no key is needed.

```bash
cd app
../.venv/bin/python -m pytest -q tests
```

### What you should see
In the browser, the page shows a form with an invented customer message already filled in. Click **Triage this message**. For the missing-milk message the result is a green "Case opened" badge, with order BB-1108, issue `missing_item`, item `milk`, quantity claimed 4, and a one-line summary. A message with an order number that does not exist shows an amber "Needs a person to review" badge and the check's reason.

The API gives the same answer. The output of the live calls in step 1 (the model's answer will vary a little between runs, but the check decides the same way):

```text
$ curl -s http://127.0.0.1:8980/health
{"status":"ok","orders_loaded":120}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H 'Content-Type: application/json' \
    -d '{"message":"Hi, I am writing about order BB-1108. The delivery came today but the milk is missing. I paid for four. Can I get a credit?"}'
{"status":"opened","record":{"order_id":"BB-1108","issue":"missing_item","item":"milk","qty_claimed":4,"summary":"Customer reported four units of milk missing from order BB-1108."},"problems":[]}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H 'Content-Type: application/json' -d '{"message":""}'
{"detail":[{"type":"string_too_short","loc":["body","message"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
```

The tests pass with no model calls made live:

```text
$ cd app && ../.venv/bin/python -m pytest -q tests
.........                                                                [100%]
9 passed in 1.35s
```

## Step 2: Storage, tests and error handling
**After chapter 2 · uses lessons 04, 05 and 11** — after this step, every triaged case is stored once in a CSV file under its stable key, a model call that fails in a way a later try can fix is retried, every error has the same shape with a stable `code`, and the page lists the stored cases.

### What you add
- `app/src/delivery_triage/store.py`: the cases file. One CSV row per case, a case id (`DI-00001`), and the stable key (order, item and issue). A case with a key already stored is not written again; the stored case comes back.
- `app/src/delivery_triage/retries.py`: lesson 04's retry rules. Retries 429, 502, 503, 504, timeouts and dropped connections with backoff and jitter. Any other error is raised at once.
- `app/src/delivery_triage/errors.py`: one error shape, `{"detail": ..., "code": ...}`, for every error the API answers.
- `app/src/delivery_triage/api.py`: the triage now stores its case. New routes: `GET /api/issues` (the newest cases) and `GET /api/issues/{case_id}`. `/health` also counts the stored cases.
- `app/src/delivery_triage/models.py`, `triage.py`, `config.py`: the response gets `case_id` and `duplicate`; the model calls go through the retries; two new settings, `TRIAGE_STORE_FILE` and `TRIAGE_MODEL_ATTEMPTS`.
- `app/src/delivery_triage/static/index.html`: the page says whether a case was stored or was already stored, shows error codes, and lists the stored cases with a refresh button.
- `app/tests/test_step2_store_retries_errors.py`: 27 offline tests of the store, the retries and the error responses, with a fake model.
- `app/tests/conftest.py`: every test run gets its own empty cases file, so the course's `data/app/` is never written by the tests.

### The code that matters
The stable key says when two triaged messages are the same case. It is lesson 05's rule (normalise first, then one row per key), with the issue added so a late delivery and a missing item on the same milk stay two cases:

```python
def dedup_key(record: CaseRecord) -> str:
    item = (record.item or "").strip().lower()
    return "|".join([record.order_id.strip().upper(), item, record.issue])
```

The retry rules are the ones lesson 04 taught. Only a failure a later try can fix is retried; a 400 or 422 is raised at once, because it would fail the same way again (lesson 04, step 5):

```python
RETRYABLE_STATUS = {429, 502, 503, 504}

def is_transient(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code in RETRYABLE_STATUS
    return isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError))
```

Each error the API answers goes through one class, so the page and a script see the same shape. The route raises it with a status, a stable code and a plain message (lesson 04 teaches the status codes; the codes are this app's own):

```python
if is_transient(exc):
    raise AppError(503, "model_busy",
                   f"The model was busy or unreachable after {settings.model_attempts} tries. "
                   "Nothing was stored; try again in a minute.") from exc
```

The store keeps the case fields and the check's result, not the customer's message text. That is the smallest data the support team needs (lesson 27 covers data minimisation).

### Run it
Install the app again, because step 2 adds one dependency (tenacity for the retries). Then start the server from `app/src` the same way as step 1. The first triage creates `data/app/issues.csv` in the course folder.

```bash
.venv/bin/python -m pip install -e app
cd app/src
uvicorn delivery_triage.api:app --reload --port 8980
```

Leave the server running. Open http://127.0.0.1:8980/ in a browser. From a second terminal:

```bash
curl -s http://127.0.0.1:8980/health
curl -s http://127.0.0.1:8980/api/issues
```

The model key is the same as step 1 (`GOOGLE_CLOUD_API_KEY`, or `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`, in the course `.env`). Two optional settings are new: `TRIAGE_STORE_FILE` moves the cases file, and `TRIAGE_MODEL_ATTEMPTS` (default 4) sets how many tries a model call gets.

### Test it
The tests run offline. The step 2 tests use a small fake model, and the step 1 tests still replay their recordings. Nothing is written to the course's `data/app/`.

```bash
cd app
../.venv/bin/python -m pytest -q tests
```

### What you should see
In the browser, the page now has a **Stored cases** table under the form. Triage the invented milk message: the result says **Stored as DI-00001**, and the table gets its first row. Triage the same message again and the page says the case **was already stored as DI-00001, so nothing new was written**. An empty message shows the error with its code.

The API gives the same answers. This is the output of the live run for step 2 (the model's wording varies a little between runs; the case id, the order and the check do not):

```text
$ curl -s http://127.0.0.1:8980/health
{"status":"ok","orders_loaded":120,"cases_stored":0}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H 'Content-Type: application/json' \
    -d '{"message":"Hi, I am writing about order BB-1108. The delivery came today but the milk is missing. I paid for four. Can I get a credit?"}'
{"status":"opened","case_id":"DI-00001","duplicate":false,"record":{"order_id":"BB-1108","issue":"missing_item","item":"milk","qty_claimed":4,"summary":"Customer reported four units of milk missing from order BB-1108."},"problems":[]}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H 'Content-Type: application/json' -d '{"message":""}'
{"detail":"The request is not valid: message String should have at least 1 character","code":"invalid_request"}

$ curl -s http://127.0.0.1:8980/api/issues/DI-99999
{"detail":"No case DI-99999. The list of cases is at GET /api/issues.","code":"case_not_found"}

$ curl -s http://127.0.0.1:8980/api/issues
[{"case_id":"DI-00001","created_at":"2026-10-26T05:03:22+00:00","order_id":"BB-1108","issue":"missing_item","item":"milk","qty_claimed":4,"summary":"Customer reported four units of milk missing from order BB-1108.","status":"opened","problems":[]}]

$ curl -s http://127.0.0.1:8980/health
{"status":"ok","orders_loaded":120,"cases_stored":1}
```

The tests pass with no live model calls. The step 2 tests cover the duplicate case, the retries, and each error code:

```text
$ cd app && ../.venv/bin/python -m pytest -q tests
....................................                                     [100%]
36 passed in 1.62s
```

## Step 3: Observability, evals and security
**After chapter 3 · uses lessons 11, 12, 13, 16 and 23** — after this step, every `/api` call needs a service token, each store has its own limits and an order from another store needs a person, every request leaves one trace and JSON log lines with its trace id, and an eval gate blocks a prompt that gets too many labelled cases wrong.

### What you add
- `app/config/tenants.json`: one entry per store with its limit per line (invented numbers, no secrets). Store 09 has a tighter limit, as in lesson 23.
- `app/src/delivery_triage/tenants.py`: the tenant registry. It loads and checks the tenants file, and turns an orders-export store name such as `Store 07` into a tenant id such as `store-07`.
- `app/src/delivery_triage/evals.py`: the eval gate. It reads lesson 11's labelled cases and labels, and passes when enough of them are right. Run on its own, it is a check you can put in a script.
- `app/src/delivery_triage/observability.py`: the JSON log formatter (each line carries the trace id), and the tracer that writes one JSON line per span to `data/app/traces.jsonl`.
- `app/src/delivery_triage/api.py`: every `/api` route needs `Authorization: Bearer <TRIAGE_SERVICE_TOKEN>`. New routes: `GET /api/tenants` and `GET /api/evals/gate`. The triage route takes an optional `tenant` and opens one trace per request.
- `app/src/delivery_triage/orders.py`, `store.py`, `triage.py`, `models.py`: the store check, the stored tenant column (an old cases file gets the column once, on first use), one span per step of a triage, and the new response fields `tenant` and `trace_id`.
- `app/src/delivery_triage/static/index.html`: a token box, a store picker, the trace id of each result, and a **Check the eval gate** button.
- `app/tests/test_step3_observability_security.py`: 22 offline tests of the token, the stores, the traces, the logs and the gate. `conftest.py` now gives the tests their own token and trace file.
- `.env.example`: lists the one new secret, `TRIAGE_SERVICE_TOKEN`, with an empty value (you fill it in your own `.env`).

### The code that matters
The token check compares the presented token with the configured one in constant time. A missing token and a wrong token get the same answer, and nothing is logged about the token itself (lesson 13 teaches why the secret never leaves the server):

```python
if not hmac.compare_digest(presented.encode(), settings.service_token.encode()):
    logger.warning("refused an /api call with a missing or wrong service token")
    raise AppError(401, "unauthorized", "The service token is missing or wrong. ...")
```

The store check gets the tenant as a parameter. An order from another store stops the case before it can open, and the store limit applies to each store's own config (lesson 23). The tenant id is checked against the registry before any model call, so a made-up store never reaches the model:

```python
if tenant is not None and any(store_key(line["store"]) != tenant.tenant_id for line in lines):
    return [f"order {rec.order_id} belongs to another store, not {tenant.tenant_id}"]
```

Each step of a triage gets its own span, so a slow step shows up in the trace (lesson 16). The message text is never put in a span or a log line:

```python
with tracer.start_as_current_span("model.lookup_call"):
    first = call_with_retries(lambda: llm.bind_tools([lookup]).invoke(asked), attempts=attempts, wait=wait)
```

The eval gate is a plain comparison with a bar. A case with no label counts as wrong, so a missing result can never pass the gate (lesson 12 explains why you also check that an automatic grader agrees with a person before you trust it):

```python
failed = sorted(case_id for case_id, want in wanted.items() if got.get(case_id) != want)
pass_rate = (len(wanted) - len(failed)) / len(wanted)
return GateResult(passed=pass_rate >= min_pass_rate, ...)
```

### Run it
First, give the app its service token. Make a long random value, then put it in the course `.env` as `TRIAGE_SERVICE_TOKEN=` (the same value every time you start the app; do not share it):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Install the app again, because this step adds two dependencies (OpenTelemetry), then start the server from `app/src`. The port is the same as before (8980).

```bash
.venv/bin/python -m pip install -e app
cd app/src
uvicorn delivery_triage.api:app --reload --port 8980
```

Leave the server running. In a second terminal, from the course folder, set the same token and call the API. `/health` and the page need no token; the `/api` routes do:

```bash
export TRIAGE_SERVICE_TOKEN='paste the same value as in .env'
curl -s http://127.0.0.1:8980/health
curl -s -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" http://127.0.0.1:8980/api/tenants
```

The eval gate also runs without the server, from `app/src`:

```bash
../../.venv/bin/python -m delivery_triage.evals
```

### Test it
The tests run offline. The model is a small fake here, and the two recorded triage calls from step 1 still replay. The tests use their own token and write their cases and traces to temporary files.

```bash
cd app
../.venv/bin/python -m pytest -q tests
```

### What you should see
In the browser, the page starts with a **Service token** box. Paste the token and the **Store** list fills with 12 stores (store 02 is the default). Triage the milk message for store 02: the result says **Case opened**, and a **Trace** line shows a 32-character id. Choose store 07 and triage the same message: the result says **Needs a person to review** with "order BB-1108 belongs to another store, not store-07", and it is stored as its own case. Click **Check the eval gate**: it says **Passed: 100% of 12 cases right (bar 90%).**

The API gives the same answers. This is the real output of the step 3 run (trace ids and times differ on every run):

```text
$ curl -s http://127.0.0.1:8980/health
{"status":"ok","version":"0.3.0","orders_loaded":120,"cases_stored":0,"service_token_set":true}

$ curl -s http://127.0.0.1:8980/api/issues
{"detail":"The service token is missing or wrong. Send it as 'Authorization: Bearer <token>'.","code":"unauthorized"}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"message":"Hi, I am writing about order BB-1108. The delivery came today but the milk is missing. I paid for four. Can I get a credit?"}'
{"status":"opened","case_id":"DI-00001","duplicate":false,"tenant":"store-02","trace_id":"febe539da730695ddd93b5d3c0d00760","record":{"order_id":"BB-1108","issue":"missing_item","item":"milk","qty_claimed":4,"summary":"Customer reported four units of milk missing from order BB-1108."},"problems":[]}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" \
    -H 'Content-Type: application/json' -d '{"message":"...the same message...","tenant":"store-07"}'
{"status":"needs_review","case_id":"DI-00002","duplicate":false,"tenant":"store-07","trace_id":"074f4ab66631cf57c289bb7ebfdac5d6","record":{"order_id":"BB-1108","issue":"missing_item","item":"milk","qty_claimed":4,"summary":"Customer reported four units of milk missing from order BB-1108."},"problems":["order BB-1108 belongs to another store, not store-07"]}

$ curl -s -X POST http://127.0.0.1:8980/api/triage -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" \
    -H 'Content-Type: application/json' -d '{"message":"Hi, order BB-1108 again.","tenant":"store-99"}'
{"detail":"No such store. The list of stores is at GET /api/tenants.","code":"unknown_tenant"}

$ curl -s -H "Authorization: Bearer $TRIAGE_SERVICE_TOKEN" http://127.0.0.1:8980/api/evals/gate
{"passed":true,"cases":12,"pass_rate":1.0,"min_pass_rate":0.9,"failed":[]}
```

The server log has one JSON line per finished triage, with the same trace id as the response (the customer's words are not in it):

```text
{"ts": "2026-10-26T06:14:37.529+00:00", "level": "info", "logger": "delivery_triage", "msg": "triage finished", "trace_id": "febe539da730695ddd93b5d3c0d00760", "case_id": "DI-00001", "duplicate": false, "status": "opened", "tenant": "store-02", "duration_ms": 2120}
```

The eval gate on its own:

```text
$ cd app/src && ../../.venv/bin/python -m delivery_triage.evals
gate passed
{"passed": true, "cases": 12, "pass_rate": 1.0, "min_pass_rate": 0.9, "failed": []}
```

The tests pass with no live model calls:

```text
$ cd app && ../.venv/bin/python -m pytest -q tests
..........................................................               [100%]
58 passed in 2.19s
```

## Step 4: Finish and run it
**After chapter 3 · uses lessons 05, 06, 11, 12, 13, 16 and 23 (the whole app)** — after this step, one command checks the files and settings and starts the app, the full test suite passes offline, and the README tells you what each screen shows.

### What you add
- `app/src/delivery_triage/__main__.py`: the one start command. Before the server starts it checks the orders file, the tenants file, the service token, the model access and the eval files, and prints one line each with no value. A wrong file stops the start; a missing token or key is a warning. `--check` runs the checks only, `--reload` restarts the server on file changes.
- `app/src/delivery_triage/config.py`: a `setting_is_set()` helper, so the start command can say whether a setting is filled in without printing it.
- `app/pyproject.toml`: a `delivery-triage` command after the install, the same as `python -m delivery_triage`.
- `app/tests/test_step4_run_and_finish.py`: 6 offline tests of the start checks and of the whole flow, from the first health check to the stored list.
- `app/README.md`: the finished README. It says how to start the app, what each part of the page shows, every setting, every error code, the tests and the files.
- `app/GUIDE.md`: this section, and the summary of what you built.

### The code that matters
One command does the start-up checks and then the server. The checks report what is set without showing any value, and only the files that the app cannot work without stop the start:

```python
checks.append(Check(
    "service token", bool(settings.service_token), False,
    "set" if settings.service_token else "not set: the /api routes answer 503 until TRIAGE_SERVICE_TOKEN is set",
))
...
if any(check.blocking and not check.ok for check in checks):
    print("Not started: fix the 'stop' line above, then run the command again.", file=sys.stderr)
    return 1
```

The whole flow is one test, so a change that breaks any step of it is caught (lessons 05, 06, 11 to 13 and 23 all meet here):

```python
opened = client.post("/api/triage", json={"message": MISSING_MILK}).json()
assert opened["status"] == "opened" and opened["case_id"] == "DI-00001" and opened["duplicate"] is False
```

### Run it
Check the settings and start the app. This is the whole command, from the course folder:

```bash
.venv/bin/python -m pip install -e app
.venv/bin/python -m delivery_triage
```

Open http://127.0.0.1:8980/ in a browser. To check the settings without starting the server:

```bash
.venv/bin/python -m delivery_triage --check
```

### Test it
Run the full suite. It runs offline and makes no live model call:

```bash
cd app
../.venv/bin/python -m pytest -q tests
```

### What you should see
In the browser you see one page. At the top, a **Service token** box: paste the token from your course `.env` and the **Store** dropdown fills with 12 stores. Triage the milk message for store 02 and you get a green **Case opened** with "Stored as DI-00001.", and a trace id. Triage it for store 07 and you get an amber **Needs a person to review** with "order BB-1108 belongs to another store, not store-07", stored as DI-00002. **Check the eval gate** says **Passed: 100% of 12 cases right (bar 90%).** The **Stored cases** table lists both, newest first. The README's "What you'll see" section describes each part in the same words.

The start command, run for real (the token comes from your `.env`; the values are never printed):

```text
$ .venv/bin/python -m delivery_triage
Checking the app before it starts:
  ok   orders file: 120 orders
  ok   tenants file: 12 stores
  ok   service token: set
  ok   model access: set
  ok   eval gate files: found
Open http://127.0.0.1:8980/ in your browser. Stop the server with Ctrl+C.
INFO:     Uvicorn running on http://127.0.0.1:8980 (Press CTRL+C to quit)
INFO:     127.0.0.1:59630 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:59638 - "GET /health HTTP/1.1" 200 OK
```

With no `TRIAGE_SERVICE_TOKEN` in the `.env` yet, the check warns and still lets the start go ahead (the page then says what to set). A missing orders file would instead print a `stop` line and exit with status 1, which the test suite checks:

```text
$ .venv/bin/python -m delivery_triage --check
Checking the app before it starts:
  ok   orders file: 120 orders
  ok   tenants file: 12 stores
  warn service token: not set: the /api routes answer 503 until TRIAGE_SERVICE_TOKEN is set
  ok   model access: set
  ok   eval gate files: found
```

The full test suite passes with no live model calls:

```text
$ cd app && ../.venv/bin/python -m pytest -q tests
...............................................................          [100%]
63 passed in 2.41s
```

### What you built
- **Triage with a checked output.** The model only asks for the order and fills a fixed form; plain code decides whether the case opens (lessons 05, 06).
- **Cases stored once.** The stable key (store, order, item, issue) stops duplicates, and the cases file is upgraded in place when a column is added (lesson 05).
- **Retries and clear errors.** Only the failures a later try can fix are retried, and every error has the same shape with a stable code (lesson 04).
- **Access and secrets.** A service token guards every `/api` route, the check is in constant time, and no key or token is printed, stored or logged (lesson 13).
- **Per-customer rules.** Each store has its own limit, an order from another store needs a person, and an unknown store is refused before any model call (lesson 23).
- **Evidence.** One trace per request with a span per step, JSON log lines carrying the trace id, and an eval gate that blocks a change when too many labelled cases are wrong (lessons 11, 12, 16).
- **One command.** The start checks the files and settings, says what is missing, and serves the page (lesson 16's run-it rule, without any container).

The app is local on purpose. Deploying it to a customer environment is the next course's job; this course stops at a working app you can run, test and explain.
