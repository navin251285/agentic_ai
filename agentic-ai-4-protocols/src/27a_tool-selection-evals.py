# %% [markdown]
# # 27a · Tool-selection evals with recorded model calls
# Level L5 · Part 6 · professional · ~35 min · builds on 27, 24

# %% [markdown]
# ## Goal
# By the end you can score a real model on a fixed set of eight requests: did it call the right tool with the right arguments? You can record the model's replies once and replay them in every later run, because your Trackr server runs in-process and is never recorded; step 4 shows the `ignore_localhost` option for an HTTP server. A reworded tool description that lowers the score fails the gate.

# %% [markdown]
# ## Why it matters
# Without an eval, a tool description is judged by reading it. Lesson 27's tests check the tool list and the results, but they never ask which tool the model picks. So a shorter description can send "close this issue" to the wrong tool, and no test fails. Without recording, an eval costs a model call every run and the answer can change between runs. Without a key, nobody else can run it.
#
# What it makes easy: a fixed answer key, one model call per description version, and a score you can compare between two versions. You do not need it for a host with two tools whose names say what they do.

# %% [markdown]
# ## The idea
# A tool-selection eval is a test for the model's choice. You write down each request, the tool it should call and the arguments that must match. Then you show the model the tools and the requests, and you score its reply against the key. The same key works for any description version, so a change to the words shows up as a change in the score.
#
# Recording makes the eval repeatable. The first run stores the model's replies. Later runs replay them, so the score does not move because the model had a different day. Your own server is not part of the recording: it runs in your process and answers each tool call live.
#
# Analogy: a driving test with a fixed route. The examiner does not drive the car, and the route is the same each time, so two cars can be compared.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   K[8 requests + answer key] --> S[Score]
#   D[descriptions_v1 or v2] --> T[Trackr server, live in process]
#   T -->|tool list| M[Model, 1 call per version]
#   M -->|tool calls| T
#   T -->|rejected calls| S
#   M -->|tool calls| S
#   S --> G[Gate: v2 must not score below v1]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Six tools, with descriptions from a file
# The server is `../apps/27a/eval_server.py`. It has six Trackr tools, and each description is read from a file under version control: `descriptions_v1.json` is the reviewed version, and `descriptions_v2.json` is the tidy-up you will test. The tool list comes from the live server, as in lesson 27. Print both versions of one description and read them before you run anything.

# %%
import sys, json, logging
from pathlib import Path
sys.path.insert(0, "../apps/27a")       # eval_server.py: the six tools, with descriptions from a file
from eval_server import build_server
from mcp import Client
logging.getLogger("mcp").setLevel(logging.WARNING)   # the server logs each rejected call at INFO
logging.getLogger("httpx").setLevel(logging.WARNING)  # the model client logs each HTTP request at INFO

APPS = Path("../apps/27a")
async with Client(build_server("v1")) as c:
    tools = (await c.list_tools()).tools
print("tools:", [t.name for t in tools])

v1 = json.loads((APPS / "descriptions_v1.json").read_text())
v2 = json.loads((APPS / "descriptions_v2.json").read_text())
print("v1 close_issue:", v1["close_issue"])
print("v2 close_issue:", v2["close_issue"])
print("v2 saves", sum(len(v1[n]) - len(v2[n]) for n in v1), "characters of descriptions across six tools")

# %% [markdown]
# ### 2. The eight requests and the answer key
# Each request has the tool it should trigger and the arguments that must match. The key is a plain list, so you can review it in a pull request like any other test data. Requests 4 and 6 are the pair a rewrite is most likely to break: close and archive sound alike.

# %%
# (request, tool the model should call, arguments that must match)
PROMPTS = [
    ("How many open issues does the mobile team have?", "count_open", {"team": "mobile"}),
    ("Which open issues mention login?", "search_issues", {"text": "login"}),
    ("Open a new issue for the api team: checkout times out.", "create_issue", {"team": "api"}),
    ("Close issue 7, it is a duplicate of issue 3.", "close_issue", {"issue_id": 7}),
    ("Reopen issue 12, the fix did not ship.", "reopen_issue", {"issue_id": 12}),
    ("Issue 9 was closed last week. Take it off the default board.", "archive_issue", {"issue_id": 9}),
    ("How many open issues does the web team have?", "count_open", {"team": "web"}),
    ("Which open issues mention push?", "search_issues", {"text": "push"}),
]
# All eight requests go in one message, so one model call answers the whole set.
NUMBERED = "Answer each numbered request with one tool call.\n" + "\n".join(
    f"{n}. {request}" for n, (request, _, _) in enumerate(PROMPTS, 1))
print(NUMBERED)

# %% [markdown]
# ### 3. Score a reply against the key
# A call answers a request when its name is the expected tool and every expected argument matches. Text is compared without letter case. The score gives one mark per request, and it returns the calls that answer no request, so you can see the wrong ones.

# %%
def same(call, tool, args):
    """True when the call has the expected tool name and every expected argument."""
    return call["name"] == tool and all(
        str(call["args"].get(key, "")).lower() == str(value).lower() for key, value in args.items())

def score(calls):
    """One mark per request (True or False), and the calls that answer no request."""
    left, marks = list(calls), []
    for _, tool, args in PROMPTS:
        match = next((c for c in left if same(c, tool, args)), None)
        marks.append(match is not None)
        if match is not None:
            left.remove(match)
    return marks, left

# %% [markdown]
# ### 4. Side demo (not part of the eval): `ignore_localhost`
# A recorder such as `vcr` records every HTTP request it sees, including requests to a server on your own machine, and replaying those later would call a server that is no longer running. `ignore_localhost=True` lets localhost requests go out live and keeps them out of the recording. `llm_replay` records only the calls to the model; this step shows the plain `vcr` option on its own, which is what you would use for a localhost HTTP server. It needs no model.

# %%
import http.server, threading, urllib.request, vcr, yaml
logging.getLogger("vcr").setLevel(logging.WARNING)   # vcr logs every request at INFO

class Hello(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"Trackr is up"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):   # keep the notebook output short
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", 9270), Hello)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = "http://127.0.0.1:9270/health"
demo = Path("../data/27a/localhost_demo.yaml")
for ignore in (False, True):
    demo.unlink(missing_ok=True)
    with vcr.use_cassette(str(demo), ignore_localhost=ignore):
        body = urllib.request.urlopen(url).read().decode()
    saved = len(yaml.safe_load(demo.read_text())["interactions"] or []) if demo.exists() else 0
    print(f"ignore_localhost={ignore}: reply {body!r}, requests saved to the recording: {saved}")
demo.unlink(missing_ok=True)
server.shutdown()

# %% [markdown]
# ### 5. Start the recorder and the model (`needs-llm`)
# `llm_replay.start` begins recording or replaying for this notebook. The notebook makes two model calls in total, one per description version. The recording replays with no key. If the model cells are skipped, `llm` stays `None` and the steps below use the saved output.

# %% tags=["needs-llm"]
import sys; sys.path.insert(0, "..")   # llm_setup and llm_replay live in the topic folder
import llm_replay
llm_replay.start("27a_tool-selection-evals")
from llm_setup import get_llm
from langchain_core.messages import HumanMessage
llm = get_llm()

# %% [markdown]
# ### 6. One eval run: list the tools, ask once, check each reply live (`needs-llm`)
# `evaluate` lists the tools from the live server, sends them with the eight requests, and scores the reply. Each returned call is then run on the same server, so a bad argument shows up as a rejected call, not only as a wrong score.

# %%
async def evaluate(version):
    """One model call with this version's descriptions, then a live check of each returned call."""
    async with Client(build_server(version)) as c:
        tools = (await c.list_tools()).tools
        defs = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                  "parameters": t.input_schema}} for t in tools]
        reply = await llm.bind_tools(defs).ainvoke([HumanMessage(NUMBERED)])
        calls = [{"name": x["name"], "args": x["args"]} for x in reply.tool_calls]
        rejected = []
        for call in calls:   # the live server runs each call; a wrong argument fails here
            r = await c.call_tool(call["name"], call["args"])
            rejected.append(r.is_error)
    marks, extra = score(calls)
    return {"marks": marks, "right": sum(marks), "extra": extra, "calls": calls,
            "rejected": sum(rejected), "input_tokens": reply.usage_metadata["input_tokens"]}

results = {}
if llm is not None:
    results["v1"] = await evaluate("v1")
    r = results["v1"]
    print(f"v1: {r['right']} of 8 right, {r['rejected']} calls rejected by the server, {r['input_tokens']} input tokens")
    print("calls that answer no request:", [c["name"] for c in r["extra"]] or "none")
else:
    print("model cell skipped: no recording and no key. Step 8 uses the saved output.")

# %% [markdown]
# ### 7. Reword the descriptions and run again (`needs-llm`)
# Version 2 is a tidy-up to save tokens, as lesson 24 showed: shorter descriptions on every tool. In the rewrite, a copy-paste slip swapped the texts of `close_issue` and `archive_issue`. Nothing else changed, the server still starts, and no test fails. The same eight requests and the same key score it.

# %% tags=["needs-llm"]
if llm is not None:
    results["v2"] = await evaluate("v2")
    r = results["v2"]
    print(f"v2: {r['right']} of 8 right, {r['rejected']} calls rejected by the server, {r['input_tokens']} input tokens")
    print("calls that answer no request:", [c["name"] for c in r["extra"]] or "none")

# %% [markdown]
# ### 8. Read both runs and the gate
# The table shows each request. The gate compares v2 with v1: if v2 scores lower, the change does not ship. When the model cells were skipped, the table uses the output saved from the course run, and it says so.

# %%
if results:
    source = "this run"
else:
    results = json.loads(Path("../data/recorded/27a.json").read_text())
    source = "saved output from the course run (the model cells were skipped)"
print("source:", source)
print(f"{'#':>2} {'expected tool':16} {'v1':>3} {'v2':>3}")
for n, (_, tool, _) in enumerate(PROMPTS):
    mark = lambda run: "yes" if run["marks"][n] else "no"
    print(f"{n + 1:>2} {tool:16} {mark(results['v1']):>3} {mark(results['v2']):>3}")
base, trial = results["v1"], results["v2"]
print(f"v1 {base['right']} of 8 · v2 {trial['right']} of 8 · input tokens saved by v2: {base['input_tokens'] - trial['input_tokens']}")
if trial["right"] < base["right"]:
    print("GATE FAILED: v2 picks the wrong tool for some requests. Keep the v1 text, or fix v2 and run the eval again.")
else:
    print("GATE PASSED: v2 does not score below v1.")

# %% [markdown]
# ## At work
# - Teams keep a tool-selection eval next to the code. A pull request that changes a description runs the same key, so the score change is in the review, the same way a failing unit test is → lesson 32a (shipping tool-description changes like code).
# - Descriptions cost tokens on every turn. Teams trim them to save money, and the eval is what shows whether the trim cost a pick → lesson 24 (tool catalog cost), lesson 40 (progressive discovery).
# - A red eval is only useful when it is repeatable. Recorded replies make the same key give the same score in CI, and the live check of each call catches a server change → lesson 33 (checkpoint: production Trackr).

# %% [markdown]
# ## What just happened
# The eight requests went to the model in one message. The reply had one call per request, and the score counted how many matched the key. The live server then ran each call, so the eval also checks that the server accepts the arguments. Version 2 changed only the words in the descriptions, and the score is the number that tells you whether that change is safe.

# %% [markdown]
# ## Common mistakes
# **Mistake 1: passing the server's tool objects to the model.** `list_tools()` returns MCP `Tool` objects. The model needs plain dictionaries in the function format.

# %% tags=["raises-exception"]
from langchain_core.utils.function_calling import convert_to_openai_tool
async with Client(build_server("v1")) as c:
    raw = (await c.list_tools()).tools
print(convert_to_openai_tool(raw[0]))   # the MCP Tool object, not the dict the model expects

# %% [markdown]
# The fix is the dictionary built in `evaluate`: `{"type": "function", "function": {"name", "description", "parameters"}}`.
#
# **Mistake 2: reading a result before checking `is_error`.** A call with the wrong argument type comes back as a tool error with no structured content. Reading it as a result fails with a `TypeError` that hides the real cause.

# %% tags=["raises-exception"]
async with Client(build_server("v1")) as c:
    r = await c.call_tool("close_issue", {"issue_id": "seven"})   # a string, not an integer
print("is_error:", r.is_error)
print("issue:", r.structured_content["result"])   # no check of is_error first

# %% [markdown]
# The fix is to check the flag first. `evaluate` reads only `is_error` from each call, so it never reads a result from a rejected call.

# %% [markdown]
# ## Production checklist
# - [ ] One fixed answer key, reviewed like test data, with the tool and the arguments for each request.
# - [ ] The model sees the same descriptions that ship. Descriptions live in a file under version control.
# - [ ] The score is compared with the last approved version, and a drop fails the build.
# - [ ] Model replies are recorded once and replayed in CI, with a budget on new calls.
# - [ ] Each returned call also runs on the live server, and rejected calls count as misses.

# %% [markdown]
# ## Try it
# Predict first. Call `close_issue` on the live server with `issue_id` set to `"seven"`, and print `is_error` and the first 60 characters of the error text. Then say which argument the message names. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
async with Client(build_server("v1")) as c:
    r = await c.call_tool("close_issue", {"issue_id": "seven"})
print("is_error:", r.is_error)
print("message:", r.content[0].text[:60])
print("the message names issue_id:", "issue_id" in r.content[0].text)

# %% [markdown]
# ## Key terms
# - **tool-selection eval** — a fixed set of requests, each scored by whether the model calls the expected tool with the expected arguments.
# - **answer key** — the list of requests with the tool and arguments each one should get. The eval scores replies against it.
# - **ignore_localhost** — a `vcr` option: requests to localhost are not recorded or replayed, so a local server stays live.
# - **recorded model call** — a model reply saved once and replayed in later runs, so the same key gives the same score.
# - **gate** — a rule that stops a change when its score falls below the last approved version.

# %%
llm_replay.stop()   # saves the recording, if this run made model calls
print("lesson 27a done: the eval scored the model, the local server stayed live, and the gate compared two descriptions")
