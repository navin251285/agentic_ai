# %% [markdown]
# # 05b · stdio done right: stdout, environment and process lifetime
# Level L2 · Part 2 · core · ~25 min · builds on 05a

# %% [markdown]
# ## Goal
# By the end you can name the three stdio failures and show each one. A stray `print()` on stdout breaks the reply. A subprocess started without `env=` cannot see `TRACKR_DB_PATH`. A server that the host has closed exits, so no orphan is left behind. Then a real model checks the fixed Trackr server (2 calls).

# %% [markdown]
# ## The idea
# With stdio, the host starts the server as a child process and talks to it through two pipes. Stdin carries requests to the server. Stdout carries replies back. Stdout is the protocol channel, so anything else written there is read as a broken message. Logs belong on stderr, which the host does not parse.
#
# The child also gets its environment from the host, not from your shell. An MCP client gives the child a short default environment, so a setting such as a database path is missing unless you pass it in `env=`. And the child lives only as long as the host keeps its stdin open. When the host closes the pipe, a well-behaved server exits.
#
# Analogy: a phone line with one wire. Anything you say into the line reaches the other side, whether or not it was meant for them. Notes for yourself go in a notebook on your desk (stderr), not into the line.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   H[Host] -- requests on stdin --> S[Server subprocess]
#   S -- replies on stdout --> H
#   S -. logs on stderr .-> L[Host log, not parsed]
#   H -- env= passes TRACKR_DB_PATH --> S
#   H -- closes stdin --> X[Server sees EOF and exits]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Stdout is the protocol channel
# This server is written by hand, with no SDK, so you can see the wire. It reads one JSON request per line and answers with one JSON reply per line. Its author added a debug print. The `writefile` cell saves the server to `../apps/05b/raw_server_broken.py`.

# %%
%%writefile ../apps/05b/raw_server_broken.py
"""Hand-written stdio server (no SDK). Broken on purpose: a debug print lands on stdout."""
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    print("debug: got", req["method"], end=" ")   # BUG: stdout is the protocol channel
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"ok": True}}), flush=True)

# %% [markdown]
# The host sends one `ping` request and reads back what the server wrote to stdout. The helper below does that and returns the lines.

# %%
import json, subprocess, sys
from pathlib import Path
APPS = Path("../apps/05b").resolve()
REQUEST = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"

def talk(script, env=None):
    """Send one request to a stdio server. Return its stdout lines and its stderr text."""
    run = subprocess.run([sys.executable, str(APPS / script)], input=REQUEST,
                         capture_output=True, text=True, timeout=10, env=env)
    return run.stdout.splitlines(), run.stderr

broken_lines, broken_err = talk("raw_server_broken.py")
print("stdout lines:", len(broken_lines))
print(repr(broken_lines[0]))

# %% [markdown]
# The debug text and the reply landed on one line. That line is not JSON, so the host cannot read the reply. The request gets no answer. The fix is to send logs to stderr.

# %% [markdown]
# ### 2. Logs go to stderr
# The fixed server writes its debug text to `sys.stderr`. The `writefile` cell saves it as `../apps/05b/raw_server_fixed.py`.

# %%
%%writefile ../apps/05b/raw_server_fixed.py
"""Hand-written stdio server (no SDK). Fixed: the debug text goes to stderr."""
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    print("debug: got", req["method"], file=sys.stderr)   # logs go to stderr
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {"ok": True}}), flush=True)

# %% [markdown]
# Run the fixed server with the same request.

# %%
lines, err = talk("raw_server_fixed.py")
print("reply:", json.loads(lines[0]))
print("stderr got the log:", err.strip())

# %% [markdown]
# The reply is clean JSON, and the log is still visible on stderr. Your MCP SDK server does the same by default, because it routes stray writes away from the protocol. A hand-written server has no such guard.

# %% [markdown]
# ### 3. Pass secrets with `env=`
# Trackr needs a path to its issue file, `TRACKR_DB_PATH`. The server logs to stderr and exits with a clear message when the path is missing. The `writefile` cell saves the server to `../apps/05b/trackr_05b.py`. It has one more tool, `server_pid`, which you will use in step 5.

# %%
%%writefile ../apps/05b/trackr_05b.py
"""Trackr MCP server for lesson 05b: logs to stderr and needs TRACKR_DB_PATH in its environment."""
import json, logging, os, sys
from mcp.server import MCPServer

logging.basicConfig(stream=sys.stderr, level=logging.INFO)   # logs never go to stdout
log = logging.getLogger("trackr")
DB = os.environ.get("TRACKR_DB_PATH")
if not DB:
    log.error("TRACKR_DB_PATH is not set; this server cannot find its issues")
    sys.exit(1)
ISSUES = json.loads(open(DB).read())
log.info("loaded %d issues from %s", len(ISSUES), DB)

mcp = MCPServer("Trackr")

@mcp.tool(title="Count open issues")
def count_open(team: str) -> int:
    """Count open Trackr issues for one team."""
    return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

@mcp.tool(title="Server process id")
def server_pid() -> int:
    """Return the process id of this server, so the host can check it later."""
    return os.getpid()

if __name__ == "__main__":
    mcp.run()

# %% [markdown]
# The issues live in a small JSON file. The cell below writes it to `../data/trackr_05b_issues.json`. It has two open web issues.

# %%
import json
from pathlib import Path
TRACKR_05B = (APPS / "trackr_05b.py").resolve()
DB = Path("../data/trackr_05b_issues.json").resolve()
DB.parent.mkdir(parents=True, exist_ok=True)
ISSUES = [
    {"id": 1, "title": "Login button does nothing on Safari", "team": "web", "status": "open", "severity": "high"},
    {"id": 3, "title": "Dark mode hides the save icon", "team": "web", "status": "closed", "severity": "low"},
    {"id": 9, "title": "Typo on the pricing page", "team": "web", "status": "open", "severity": "low"},
    {"id": 2, "title": "Signup email arrives twice", "team": "api", "status": "open", "severity": "medium"},
    {"id": 4, "title": "App crashes when photo is rotated", "team": "mobile", "status": "open", "severity": "critical"},
    {"id": 5, "title": "Rate limiter blocks health checks", "team": "infra", "status": "open", "severity": "high"},
]
DB.write_text(json.dumps(ISSUES, indent=2))
print("wrote", DB.name, "with", len(ISSUES), "issues")

# %% [markdown]
# Now the host starts Trackr with `env=`. The dictionary holds only what the server needs. The client also keeps its default minimal environment, so the server still starts.

# %%
from mcp import Client
from mcp.client.stdio import StdioServerParameters
params = StdioServerParameters(command=sys.executable, args=[str(TRACKR_05B)],
                               env={"TRACKR_DB_PATH": str(DB)})
async with Client(params) as trackr:
    result = await trackr.call_tool("count_open", {"team": "web"})
    print("open web issues:", result.structured_content["result"])

# %% [markdown]
# The count is 2, as the file says. `TRACKR_DB_PATH` is a path, not a secret, so a literal value in `env=` is fine for this demo. A real token would come from the host's own environment (`os.environ["TRACKR_TOKEN"]`), not from a literal in a committed config file.

# %% [markdown]
# ### 4. A real model checks the fixed server (`needs-llm`)
# The host now gives the model the Trackr tools through `MCPAdapter`. The adapter config carries the same `env=` values. The question needs `count_open`. The model makes one call, the host runs it, and the model writes the answer. That is 2 model calls in total.

# %%
import logging, warnings
from contextlib import AsyncExitStack   # the stack owns the adapter; step 5 closes it
from langchain_core._api import LangChainBetaWarning
from langchain.mcp import MCPAdapter
warnings.filterwarnings("ignore", category=LangChainBetaWarning)   # the adapter is still beta
for noisy in ["httpx", "vcr", "google_genai", "fastmcp"]:   # set after the imports: fastmcp resets them
    logging.getLogger(noisy).setLevel(logging.WARNING)
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
from langchain_core.messages import AIMessage, HumanMessage
CONFIG = {"mcpServers": {"trackr": {"command": sys.executable, "args": [str(TRACKR_05B)],
                                    "env": {"TRACKR_DB_PATH": str(DB)}}}}
stack = AsyncExitStack()   # step 5 closes it
adapter = await stack.enter_async_context(MCPAdapter(CONFIG))
mcp_tools = await adapter.list_tools()
by_name = {t.name: t for t in mcp_tools}
print(sorted(by_name))
QUESTION = HumanMessage("How many open issues does the web team have?")
llm = None   # the model cell sets this; stays None if that cell is skipped

# %% [markdown]
# The first model call asks for a tool. `get_llm` picks the model and starts the recording or the replay.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("05b_stdio-done-right", max_calls=2)
first = await llm.bind_tools(mcp_tools).ainvoke([QUESTION])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])
else:
    print("model reply used; no stand-in needed")

# %% [markdown]
# The host runs the tool through the adapter, and the model writes its answer. This is the second and last call (`needs-llm`).

# %%
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for r in results:
    print("ToolMessage status:", r.status, "| text:", r.text.splitlines()[0])

# %% [markdown]
# The model reads the tool's answer and writes its reply. With one server in the config, the adapter keeps the plain tool name `count_open`. Lesson 05 showed the `{server}_{tool}` names when two servers share one config.

# %% tags=["needs-llm"]
final = await llm.bind_tools(mcp_tools).ainvoke([QUESTION, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool returned.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The tool said:", results[0].text.splitlines()[0])

# %% [markdown]
# ### 5. The host shuts down, and the server does not outlive it
# A server started by a host is a child process. When the host closes the connection, the child should exit. The `server_pid` tool returns the child's process id, so the host can check it after shutdown. `os.kill(pid, 0)` sends no signal. It only tests whether the process exists.

# %%
import os
async with Client(params) as trackr:   # a fresh host, with the same env=
    pid = (await trackr.call_tool("server_pid", {})).structured_content["result"]
    print("server pid captured | connected: yes")
try:
    os.kill(pid, 0)   # the host has closed the connection by now
    print("orphan")
except ProcessLookupError:
    print("no orphan")

# %% [markdown]
# A host can also disappear without closing anything, for example if it crashes. The pipe still closes when the host's process ends. A well-behaved server reads end-of-file on stdin and exits. This run shows it with no requests at all.

# %%
import subprocess as sp
child = sp.Popen([sys.executable, str(TRACKR_05B)], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE,
                 env={"TRACKR_DB_PATH": str(DB)})
child.stdin.close()   # the host went away: end-of-file on stdin
child.wait(timeout=10)
child.stdout.close(); child.stderr.close()
print("Trackr exit code after the host went away:", child.returncode)

# %% [markdown]
# A server that ignores end-of-file is an orphan. This hand-written server never reads stdin, so it never notices the host left. The `writefile` cell saves it as `../apps/05b/raw_server_ignores_eof.py`.

# %%
%%writefile ../apps/05b/raw_server_ignores_eof.py
"""Hand-written stdio server that ignores end-of-file. It keeps running after the host has gone."""
import time
while True:
    time.sleep(1)   # never reads stdin, so it never sees the host leave

# %% [markdown]
# Start it, close its stdin the way a departing host would, and check whether it is still there. Then stop it by hand. The `finally` block makes sure the process does not outlive the notebook.

# %%
import time
bad = sp.Popen([sys.executable, str(APPS / "raw_server_ignores_eof.py")],
               stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
try:
    bad.stdin.close()   # the host went away: end-of-file on stdin
    time.sleep(0.5)     # give the server a moment to start
    try:
        os.kill(bad.pid, 0)
        print("still running after the pipes closed: orphan")
    except ProcessLookupError:
        print("already gone: no orphan")
finally:
    bad.kill()   # the only way out for this server: kill it
    bad.wait(timeout=10)
    bad.stdout.close(); bad.stderr.close()
print("returncode after kill:", bad.returncode)

# %% [markdown]
# The Trackr server exited on end-of-file. The hand-written server did not, so only a kill stopped it. A stdio server must exit when its stdin closes.

# %% [markdown]
# Close the model adapter from step 4, then tell the recorder the lesson is done.

# %%
await stack.aclose()   # close the model adapter from step 4
llm_replay.stop()
print("lesson 05b done: stdout for protocol only, env= for secrets, no orphan after the host closes")

# %% [markdown]
# ## At work
# - Local stdio servers run with the user's own privileges, and a config entry starts a program. In April 2026 a security disclosure reported about ten CVEs in AI tools that let a crafted stdio config run commands. Treat every server entry as code you are running → lesson 29a.
# - Shared servers in production run as remote services under a process supervisor, so the platform decides the process lifetime, not the developer's laptop. The stdio pattern above is for one user's own tools → lesson 06.
# - Teams send logs and traces to a collector, not to the protocol channel. Standard tracing carries one trace id across the protocols → lesson 28.

# %% [markdown]
# ## What just happened
# - The debug text and the reply shared one line, so the reply could not be read. Moving the text to stderr fixed it with no other change.
# - The server failed fast without `TRACKR_DB_PATH`. The fix was `env=` in the parameters. The path is not a secret, so a literal value is fine in this demo. A real token would come from the host's own environment, not from a literal in a committed config file.
# - The model asked for `count_open` with `team: web`, the host ran it, and the answer came from the issue file.
# - After the host closed the adapter, the server process was gone. Trackr also exits when its stdin closes. A hand-written server that ignores stdin stays running as an orphan until something kills it.

# %% [markdown]
# ## Common mistakes
# Writing a debug line to stdout from a hand-written server. The reply is glued to the text, so the line is not JSON. The code below reads the reply from the broken server:

# %% tags=["raises-exception"]
json.loads(broken_lines[0])   # the debug text sits in front of the reply: JSONDecodeError

# %% [markdown]
# Fix: `print(..., file=sys.stderr)` for logs, as step 2 does.
#
# Starting a server without `env=`. The client's default environment does not include `TRACKR_DB_PATH`. The server exits at once, and the client reports a closed connection. The cell below makes that real:

# %% tags=["raises-exception"]
async with Client(StdioServerParameters(command=sys.executable, args=[str(TRACKR_05B)], env={})) as trackr:
    await trackr.list_tools()

# %% [markdown]
# The error shows the failed connection, not the cause. The server's own log line is the place to look. The cell below runs the same server with the same empty environment and prints its last log line. It does not raise, so the lesson keeps running:

# %%
run = sp.run([sys.executable, str(TRACKR_05B)], input="", capture_output=True, text=True, timeout=10, env={})
print("server exit code:", run.returncode)
print("server log:", run.stderr.strip().splitlines()[-1])

# %% [markdown]
# Fix: pass what the server needs in `env=`, as step 3 does. A real token comes from the host's own environment (`os.environ["TRACKR_TOKEN"]`), never a literal in the code or a committed config file.

# %% [markdown]
# ## Try it
# Run `raw_server_fixed.py` with a `ping` and print its exit code. Then run `trackr_05b.py` with `env={"TRACKR_DB_PATH": "../data/nope.json"}` and print the exit code and the last line of its stderr. No model is needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **stdout (protocol channel)** — the pipe that carries the server's replies. Only protocol messages belong on it.
# - **stderr** — the second pipe, for logs. The host shows it but does not parse it as protocol.
# - **env=** — the parameter that sets the environment variables a subprocess gets, such as a database path or a token.
# - **minimal environment** — the small default set of variables a client gives a child process when you pass none.
# - **orphan process** — a child process still running after the program that started it has gone.
# - **end-of-file (EOF) on stdin** — the signal that the other side closed its pipe. A stdio server should exit on it.
# - **process id (pid)** — the number the operating system gives a running process. `os.kill(pid, 0)` tests whether it exists.
