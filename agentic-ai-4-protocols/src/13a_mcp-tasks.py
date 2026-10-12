# %% [markdown]
# # 13a · Long-running work: the MCP Tasks extension
# Level L3 · Part 3 · professional · ~35 min · builds on 13, 07b, 09

# %% [markdown]
# ## Goal
# By the end you start a Trackr export as a task, poll it to completion, and cancel a second export part way through. You compare the MCP task handle with the A2A task from lesson 09. A real model starts the export with one call and summarises it with a second call.

# %% [markdown]
# ## Why it matters
# Lesson 13 made a 20-second reindex report progress, but the request stayed open the whole time. A job that takes four minutes ties up one connection for four minutes. Proxies and clients cut idle connections, and a client that restarts loses the reply it was waiting for. Without a task, the only choices are to hold the connection or to start the job again.
#
# The cell below is that version, in plain Python. The client waits one second, then gives up. The export keeps running, and nobody holds its result.

# %%
import concurrent.futures as cf
import time

def export_in_process(seconds=3):
    time.sleep(seconds)                  # the whole export, before any reply
    return "csv ready"

pool = cf.ThreadPoolExecutor(max_workers=1)
future = pool.submit(export_in_process)
try:
    print(future.result(timeout=1))      # the caller waits one second
except cf.TimeoutError:
    print("the caller gave up after 1 s; the export is still running")
print("the export finished later:", future.result())
pool.shutdown()

# %% [markdown]
# The Tasks extension fixes this. The server answers at once with a handle, and the client asks for the result when it is ready. The handle is a durable id, so a client that restarts can ask again, and the client can cancel the job with `tasks/cancel`. Jobs that finish in about 1 second or less do not need a task: a plain call is simpler.

# %% [markdown]
# ## The idea
# A **task handle** is a claim ticket. The server answers the `tools/call` at once with a `CreateTaskResult`: a `taskId`, a `status` of `working`, a `pollIntervalMs` (how long to wait between checks) and a `ttlMs` (how long the task lives, counted from creation; `null` means no limit). The client calls `tasks/get` until the status is terminal: `completed`, `failed` or `cancelled`. `tasks/cancel` asks for a stop, and the server may still finish.
#
# The extension is opt-in on every request, through `_meta`. A server that sees no opt-in never returns a handle. Analogy: a laundry ticket. You get a number at once, you check back, and the ticket has an expiry date.

# %% [markdown]
# `input_required` is the other status: the server needs more input from the user. The client sends that input with `tasks/update`, and the task goes back to `working`. This lesson does not run that path, so the demo has only polling and cancel. `notifications/tasks` is the push alternative to polling.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant H as Host (client)
#   participant S as Trackr export server
#   H->>S: tools/call export_issues (_meta: tasks opt-in)
#   S-->>H: CreateTaskResult: taskId, status working, pollIntervalMs
#   loop until the status is terminal
#     H->>S: tasks/get (taskId)
#     S-->>H: status and statusMessage
#   end
#   S-->>H: status completed, result (the CSV)
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start the recording and the helpers
# The first code cell starts `llm_replay`, as in every model lesson. Every HTTP call in this notebook goes through the recorder, including the calls to the local server, so the polling replays in the same order. The stop is the last cell.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("13a_mcp-tasks")   # record once, replay everywhere

# %% [markdown]
# Next come the settings. The port and the URL are local. The two `_meta` values differ in one thing: `NO_OPT_IN` has an empty list of extensions, and `OPT_IN` names the Tasks extension.

# %%
import json, subprocess, atexit
from pathlib import Path
import httpx

PORT = 9130
URL = f"http://127.0.0.1:{PORT}/mcp"
TASKS_ID = "io.modelcontextprotocol/tasks"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
NO_OPT_IN = {VERSION_KEY: "2026-07-28", CAPS_KEY: {}}
OPT_IN = {VERSION_KEY: "2026-07-28", CAPS_KEY: {"extensions": {TASKS_ID: {}}}}
TERMINAL = {"completed", "failed", "cancelled"}
Path("../data/13a").mkdir(parents=True, exist_ok=True)   # run-time files (the log) live here
print("opt-in id:", TASKS_ID)

# %% [markdown]
# ### 2. The server: a hand-written JSON-RPC worker
# The `mcp` 2.3 package ships Task models, but their names follow an older experimental shape (a `task` wrapper, `ttl`, `pollInterval`), and it has no loop that runs a task in the background. So this server writes the wire format by hand, with the standard library only. Its field names follow the official 2026-07-28 Tasks extension spec (SEP-2663, https://github.com/modelcontextprotocol/ext-tasks). The server's own choices are the `export_issues` tool, its batch sizes and status texts, and the internal `cancel` flag, which never goes on the wire. Read the file once. The `export_issues` tool returns a handle when the client opted in, and runs the export in a thread, one batch at a time. Before each batch the thread checks the cancel flag.

# %%
%%writefile ../apps/13a/trackr_export_server.py
"""Trackr export server (lesson 13a): export_issues returns a task handle to clients that opt in.
Hand-written JSON-RPC over HTTP, standard library only."""
import csv, io, itertools, json, sys, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TASKS_ID = "io.modelcontextprotocol/tasks"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
BATCHES, BATCH_SECONDS = 6, 0.5              # 6 batches of 0.5 s: a 3-second export
TTL_MS, POLL_MS = 600_000, 300
TEAMS = ("web", "api", "mobile", "infra")
TITLES = ["login fails on Safari", "slow search", "export times out", "typo on help page",
          "badge count wrong", "crash on upload", "dark mode colours", "API rate limit too low"]
ISSUES = [(f"TRK-{n}", TITLES[(n - 1) % len(TITLES)], TEAMS[n % 4],
           "open" if n % 3 else "closed", ("low", "med", "high")[n % 3]) for n in range(1, 21)]
EXPORT_TOOL = {"name": "export_issues", "title": "Export issues as CSV",
               "description": "Export Trackr issues as CSV, optionally for one team. Takes about 3 seconds.",
               "inputSchema": {"type": "object", "required": ["format"],
                               "properties": {"format": {"type": "string", "enum": ["csv"]},
                                              "team": {"type": "string", "enum": list(TEAMS)}}}}
TASKS = {}                                   # taskId -> state, in this process only
LOCK = threading.Lock()
COUNTER = itertools.count(1)

class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def export_csv(team):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "team", "status", "severity"])
    w.writerows(i for i in ISSUES if team is None or i[2] == team)
    return buf.getvalue()

def run_task(task_id, team):
    """The worker: one batch at a time, checking the cancel flag before each batch."""
    for batch in range(1, BATCHES + 1):
        time.sleep(BATCH_SECONDS)
        with LOCK:
            t = TASKS[task_id]
            if t["cancel"]:
                t.update(status="cancelled", statusMessage=f"stopped after batch {batch - 1} of {BATCHES}")
                print(f"stopped {task_id} after batch {batch - 1}: no more work", file=sys.stderr, flush=True)
                return
            t.update(statusMessage=f"exporting batch {batch} of {BATCHES}", lastUpdatedAt=now())
    text = export_csv(team)
    with LOCK:
        TASKS[task_id].update(status="completed", statusMessage="export ready", lastUpdatedAt=now(),
                              result={"content": [{"type": "text", "text": text}], "isError": False})
    print(f"finished {task_id}", file=sys.stderr, flush=True)

def call_tool(params):
    if params.get("name") != "export_issues":
        raise RpcError(-32602, f"unknown tool {params.get('name')}")
    args = params.get("arguments") or {}
    team = args.get("team")
    if args.get("format") != "csv" or team not in (None, *TEAMS):
        raise RpcError(-32602, "format must be csv; team must be a known team")
    caps = (params.get("_meta") or {}).get(CAPS_KEY) or {}
    if TASKS_ID not in (caps.get("extensions") or {}):
        time.sleep(BATCHES * BATCH_SECONDS)   # no opt-in: the whole export runs before the reply
        return {"resultType": "complete", "content": [{"type": "text", "text": export_csv(team)}], "isError": False}
    task_id = f"task-{next(COUNTER)}"
    with LOCK:
        TASKS[task_id] = {"status": "working", "statusMessage": "queued", "createdAt": now(),
                          "lastUpdatedAt": now(), "cancel": False, "result": None}
        t = TASKS[task_id]
    threading.Thread(target=run_task, args=(task_id, team), daemon=True).start()
    return {"resultType": "task", "taskId": task_id, "status": "working", "createdAt": t["createdAt"],
            "lastUpdatedAt": t["lastUpdatedAt"], "ttlMs": TTL_MS, "pollIntervalMs": POLL_MS}

# %% [markdown]
# The second half of the server answers the polls and the cancel, and runs the HTTP handler. It appends to the same file.

# %%
%%writefile -a ../apps/13a/trackr_export_server.py
def task_view(task_id):
    with LOCK:
        t = TASKS.get(task_id)
        if t is None:
            raise RpcError(-32602, f"unknown taskId {task_id}")
        view = {"resultType": "complete", "taskId": task_id, "status": t["status"],
                "statusMessage": t["statusMessage"], "createdAt": t["createdAt"],
                "lastUpdatedAt": t["lastUpdatedAt"], "ttlMs": TTL_MS, "pollIntervalMs": POLL_MS}
        if t["status"] == "completed":
            view["result"] = t["result"]
        return view

def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "server/discover":
        return {"capabilities": {"tools": {}, "extensions": {TASKS_ID: {}}},
                "serverInfo": {"name": "trackr-export", "version": "1.0.0"}}
    if method == "tools/list":
        return {"tools": [EXPORT_TOOL]}
    if method == "tools/call":
        return call_tool(params)
    if method == "tasks/get":
        return task_view(params.get("taskId"))
    if method == "tasks/cancel":
        with LOCK:
            t = TASKS.get(params.get("taskId"))
            if t is None:
                raise RpcError(-32602, "unknown taskId")
            if t["status"] == "working":
                t["cancel"] = True             # cooperative: the worker stops at its next batch
        return {"resultType": "complete"}      # CancelTaskResult: an empty acknowledgement
    raise RpcError(-32601, f"method not found: {method}")

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            reply = {"jsonrpc": "2.0", "id": msg.get("id"), "result": handle(msg)}
        except RpcError as e:
            reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": e.code, "message": str(e)}}
        body = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):   # keep the log to the task lines
        pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()

# %% [markdown]
# The notebook starts the server on port 9130. Its log goes to `../data/13a/export.log`, and the server writes one line when a task finishes or stops.

# %%
logf = open("../data/13a/export.log", "w")
proc = subprocess.Popen([sys.executable, str(Path("../apps/13a/trackr_export_server.py").resolve()), str(PORT)],
                        stdout=logf, stderr=subprocess.STDOUT)
def stop_server():
    if proc.poll() is None:
        proc.terminate()
atexit.register(stop_server)
print("export server starting on port", PORT)

# %% [markdown]
# ### 3. Wait until the server answers
# The cell calls `server/discover` until the server replies, for up to 20 seconds. If it does not start, the cell points at the log.

# %%
deadline = time.monotonic() + 20
while True:
    try:
        httpx.post(URL, json={"jsonrpc": "2.0", "id": 0, "method": "server/discover"}, timeout=5)
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("the export server did not start: read ../data/13a/export.log")
        time.sleep(0.2)
print("export server is up")

# %% [markdown]
# ### 4. The helpers: the opt-in travels with each request
# Every request has its own `_meta`. `rpc` sends one JSON-RPC request and returns its `result`. The opt-in is the `tasks` id in `clientCapabilities.extensions`, and it appears only on the requests that want a task. `wait_for_end` polls `tasks/get` and waits the number of milliseconds the server asked for.

# %%
_ids = iter(range(1, 1000))

def rpc(method, params=None, meta=None):
    """One JSON-RPC request. Raises if the server replies with an error."""
    body = {"jsonrpc": "2.0", "id": next(_ids), "method": method,
            "params": {**(params or {}), "_meta": meta or NO_OPT_IN}}
    reply = httpx.post(URL, json=body, headers={"MCP-Protocol-Version": "2026-07-28"}, timeout=30).json()
    if "error" in reply:
        raise RuntimeError(f"{reply['error']['code']}: {reply['error']['message']}")
    return reply["result"]

def export_args(team=None):
    return {"format": "csv", **({"team": team} if team else {})}

print("helpers ready: rpc, export_args")

# %% [markdown]
# `wait_for_end` is the polling loop. It counts its polls, so the summary can report them.

# %%
LAST_POLLS = 0

def wait_for_end(task_id, show=True):
    """Poll tasks/get, honouring pollIntervalMs, until the status is terminal."""
    global LAST_POLLS
    last, LAST_POLLS = None, 0
    while True:
        view = rpc("tasks/get", {"taskId": task_id})
        LAST_POLLS += 1
        if show and (view["status"], view.get("statusMessage")) != last:
            print(f"{view['status']:<10} {view.get('statusMessage') or ''}")
        last = (view["status"], view.get("statusMessage"))
        if view["status"] in TERMINAL:
            return view
        time.sleep(view["pollIntervalMs"] / 1000)

print("helpers ready: wait_for_end")

# %% [markdown]
# ### 5. The extension is advertised, and the opt-in is per request
# `server/discover` lists the extension. The client names it on the requests that want a task.

# %%
caps = rpc("server/discover")["capabilities"]
print("server advertises:", sorted(caps["extensions"]))
print("this client opted in:", TASKS_ID in OPT_IN[CAPS_KEY]["extensions"])

# %% [markdown]
# ### 6. Without the opt-in: one reply, after the whole export
# The same tool call, without the opt-in, does not return a handle. The server runs the export first and then replies with the CSV. The client waits for all of it.

# %%
reply = rpc("tools/call", {"name": "export_issues", "arguments": export_args("web")}, NO_OPT_IN)
rows = reply["content"][0]["text"].strip().splitlines()
print(f"without the opt-in: one reply with {len(rows) - 1} web rows and no task")

# %% [markdown]
# ### 7. With the opt-in: a handle at once
# The same call, with the opt-in, returns a `CreateTaskResult`. The `resultType` is `"task"`, and the reply has no `content` field. Keep the handle: its `taskId` is the only thing you need to find the job again.

# %%
handle = rpc("tools/call", {"name": "export_issues", "arguments": export_args("web")}, OPT_IN)
print({k: handle[k] for k in ("resultType", "taskId", "status", "ttlMs", "pollIntervalMs")})

# %% [markdown]
# ### 8. Poll to completion and read the result
# `wait_for_end` polls until the status is terminal and prints one summary line. When the status is `completed`, the `result` field holds what the call would have returned without the extension.

# %%
done = wait_for_end(handle["taskId"], show=False)
csv_text = done["result"]["content"][0]["text"]
lines = csv_text.strip().splitlines()
print(f"completed after {LAST_POLLS} polls: {len(lines) - 1} web rows | header: {lines[0]}")

# %% [markdown]
# **Aside: push instead of poll.** A server that supports `notifications/tasks` pushes the same task view over the `subscriptions/listen` stream from lesson 07b, so the client need not poll. This server only answers polls.

# %% [markdown]
# ### 9. Cancel a second export part way through
# Cancelling is a request, not a switch. The client sends `tasks/cancel` and gets an empty acknowledgement. The worker notices at its next batch and stops. The printed status right after the cancel is still `working`; the final status is `cancelled`, and its message says where it stopped.

# %%
second = rpc("tools/call", {"name": "export_issues", "arguments": export_args()}, OPT_IN)
view = rpc("tasks/get", {"taskId": second["taskId"]})
while "batch 2 of" not in (view.get("statusMessage") or "") and view["status"] not in TERMINAL:
    time.sleep(0.2)                          # let two batches finish before the cancel
    view = rpc("tasks/get", {"taskId": second["taskId"]})
print("before cancel:", view["status"], "|", view["statusMessage"])

# %% [markdown]
# Now send the cancel. The reply is an empty acknowledgement. The status read right after it is still `working`, and `wait_for_end` then returns the final status.

# %%
print("cancel reply:", rpc("tasks/cancel", {"taskId": second["taskId"]}))
right_after = rpc("tasks/get", {"taskId": second["taskId"]})
print("right after the cancel:", right_after["status"], "|", right_after["statusMessage"])
final = wait_for_end(second["taskId"])
print("final:", final["status"], "|", final["statusMessage"])

# %% [markdown]
# ### 10. A real model starts the export (`needs-llm`)
# The host lists the tools, and the model chooses one. The model is called once, and it must answer with a tool call. The host then runs that call with the opt-in, and polls it to the end. The list of tools comes from `tools/list`, so the model sees the same schema that the server publishes.

# %%
tools_for_model = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": t["inputSchema"]}}
                   for t in rpc("tools/list")["tools"]]
ask = None        # filled by the model cell; stays None if that cell is skipped
summary = None    # filled by the summary cell
print("tools the model sees:", [t["function"]["name"] for t in tools_for_model])

# %% [markdown]
# The model is called once, with the tool list. It must answer with a tool call, not text.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage
from llm_setup import get_llm
llm = get_llm()
ask = llm.bind_tools(tools_for_model).invoke([HumanMessage("Export the web team's issues as CSV. Start the export now.")])
print("model asks for:", [(c["name"], c["args"]) for c in ask.tool_calls])

# %% [markdown]
# If the model cell was skipped, the host makes the same call itself. No model is involved in that path, so the rest of the lesson still runs.

# %%
if ask is not None and ask.tool_calls:
    call = ask.tool_calls[0]
else:
    call = {"name": "export_issues", "args": export_args("web")}
    print("no model: the host starts the export itself")
run = rpc("tools/call", {"name": call["name"], "arguments": call["args"]}, OPT_IN)
print("handle:", run["taskId"], run["status"])
done2 = wait_for_end(run["taskId"], show=False)
csv2 = done2["result"]["content"][0]["text"]
print("export rows:", len(csv2.strip().splitlines()) - 1)

# %% [markdown]
# ### 11. The model summarises the result (`needs-llm`)
# The second and last model call reads the CSV that the task returned. The model sees only the tool result, which is untrusted text. Lesson 30 covers what that means.

# %% tags=["needs-llm"]
summary = llm.invoke(f"This CSV is a Trackr export. In one sentence, say how many issues it lists and which severities appear.\n\n{csv2}")
print(summary.text)

# %% [markdown]
# If the summary cell was skipped, this cell prints a local count of the rows and severities instead. Either way the row count is the same.

# %%
if summary is None:   # the model cell was skipped: say what it would have summarised
    rows2 = csv2.strip().splitlines()[1:]
    print("no model: the export has", len(rows2), "rows; the severities are", sorted({r.split(",")[-1] for r in rows2}))

# %% [markdown]
# ### 12. Stop the server and the recorder
# The last code cell stops the server and then the recorder, which saves the recording.

# %%
stop_server()
proc.wait(timeout=10)
logf.close()
llm_replay.stop()   # saves the recording
print("server stopped")

# %% [markdown]
# ### 13. MCP Tasks next to A2A tasks
# Both use a handle, a state and a poll, for different problems.
#
# | | MCP Tasks (this lesson) | A2A task (lesson 09) |
# |---|---|---|
# | What it is | the handle for one tool call (`CreateTaskResult`) | one agent's unit of work, with its own messages and artifacts |
# | Who creates it | a server, only for a `tools/call` from a client that opted in | an agent, for each `SendMessage` |
# | States | `working`, `input_required`, `completed`, `failed`, `cancelled` | eight `TASK_STATE_*` values, including `REJECTED` and `AUTH_REQUIRED` |
# | Follow it | `tasks/get` polling; `notifications/tasks` over `subscriptions/listen` (lesson 07b) | `GetTask`; `SubscribeToTask` stream |
# | Cancel | `tasks/cancel`, cooperative: the final status may differ | `CancelTask`, moves the task to `CANCELED` unless it has ended |
# | Remembers the conversation | no: one call | yes: `contextId` groups the turns |
#
# Rule of thumb: a tool that runs a long job gets an MCP task. An agent that does a job with its own steps and questions gets an A2A task.

# %% [markdown]
# ## At work
# - **Long calls outlive the connection, not the job.** Clients and proxies cut idle connections. The Python MCP client waits 300 s on a read, and a bare `httpx2` client (the client library behind mcp 2.x) gives up after 5 s. A four-minute export becomes a handle plus polls. Production timeouts are in lesson 33.
# - **Store the taskId before you poll.** A handle that dies with the client's memory cannot be resumed. Production clients save the id with the job, so a restart can poll again (→ lesson 33).
# - **Honour `pollIntervalMs` and `ttlMs`.** Polling faster than the server asks is a load problem. A task past its `ttlMs` may be gone, so an export not read in time has to be started again. Test the polling loop as in lesson 27.

# %% [markdown]
# ## What just happened
# The server answered each long call with a handle, and the host polled the handle until it ended. The task that completed returned the same CSV the plain call returns. The cancelled task stopped at its next batch and reported where. The model made two calls: one to start the export and one to summarise it. Everything else went over plain JSON-RPC.

# %% [markdown]
# ## Common mistakes
# **Mistake 1: reading the handle as the result.** A `CreateTaskResult` has no `content`. The job has not run yet. The key error below is the one you get.

# %% tags=["raises-exception"]
print(handle["content"][0]["text"])

# %% [markdown]
# The fix is to poll with `wait_for_end` and read `result` only after the status is `completed`.
#
# **Mistake 2: polling faster than the server asks.** Polling faster than `pollIntervalMs` adds load to the server and does not finish the task sooner.
#
# **Mistake 3: treating cancel as a switch.** `tasks/cancel` returns at once, and the job may still run or finish first. Step 9 printed `working` right after the cancel and `cancelled` later, so read the status until it is terminal, as `wait_for_end` does.

# %% [markdown]
# ## Try it
# Write `is_done(view)` so that it returns True only when a `tasks/get` view has a terminal status (`completed`, `failed` or `cancelled`). A `working` or `input_required` view returns False.

# %%
# your code here
def is_done(view):
    """True when view's status is terminal. view is one tasks/get reply."""
    pass

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def is_done(view):
    return view.get("status") in TERMINAL

print(is_done({"status": "working"}), is_done({"status": "input_required"}), is_done({"status": "cancelled"}))

# %% [markdown]
# ## Key terms
# - **CreateTaskResult** — the reply that replaces a tool result with a task handle: `resultType` `"task"`, `taskId`, `status`, `ttlMs`, `pollIntervalMs` (lesson 13a).
# - **MCP Tasks** — the extension `io.modelcontextprotocol/tasks`: a server returns a handle for a long call, and the client polls it with `tasks/get` or cancels it with `tasks/cancel` (lesson 13a).
# - **pollIntervalMs** — the server's suggested wait between `tasks/get` calls, in milliseconds (lesson 13a).
# - **ttlMs** — the task's lifetime from creation, in milliseconds; `null` means no limit (lesson 13a).
