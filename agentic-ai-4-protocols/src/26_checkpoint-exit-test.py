# %% [markdown]
# # 26 · Checkpoint (Exit test): MCP tool or A2A agent?
# Level L4 · Part 5 · professional · ~90 min · builds on 13a, 18, 22, 24

# %% [markdown]
# ## Goal
# By the end you have decided, for six Trackr capabilities, whether each is an MCP tool, an MCP Task or an A2A agent, and you can say why. For the two borderline ones you have built both designs, measured them, and made the call.

# %% [markdown]
# ## Why it matters
# Without a rule, teams make one of two mistakes. Either every capability becomes an agent, or every agent gets flattened into a tool. The table shows what each wrong choice costs in this course.
#
# | Wrong choice | What breaks | Where it is covered |
# |---|---|---|
# | Count open issues as an agent | an extra model call plus a card fetch for one number | lesson 03 |
# | Export a report as a plain tool | one request stays open for minutes | lesson 13a |
# | Vendor security agent as a tool | its steps are hidden in your server, and you cannot ask it back | lesson 18 |
#
# What the rule makes easy: each new capability gets a decision in minutes, with reasons you can defend. You do not need the rule for one server with two tools.

# %% [markdown]
# ## The idea
# Three answers decide most cases. A capability is an **MCP tool** when the caller needs a typed answer from one short call that you own. It is an **MCP Task** when the work is deterministic but takes minutes, so the caller gets a handle and polls. It is an **A2A agent** when another owner must keep its internals opaque, or when it must plan or ask back.
#
# Two capabilities sit on the line: triage and propose a fix. Both need model judgement in one short call, so size and speed cannot pick. Ownership and the output shape decide. You build both designs and measure them, then make the call.
#
# Analogy: a till at a shop gives the same answer every time, so it is a tool. A repair shop takes the job, asks questions and reports back when it is done, so it is an agent.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart TD
#   Q{Another owner, or must plan or ask back?} -->|yes| A[A2A agent]
#   Q -->|no| S{One short call?}
#   S -->|no, minutes| T[MCP Task]
#   S -->|yes| M[MCP tool]
#   M -->|borderline: model judges| B{Typed output, owned here?}
#   B -->|yes| M2[keep the MCP tool]
#   B -->|no| A
# ```

# %% [markdown]
# ## Requirements
# The exit test passes when every line below prints PASS in step 7.
# - [ ] **R1.** Both A2A agents are found from their cards: `triage-agent` and `fix-agent`.
# - [ ] **R2.** Both triage designs label the same four issues (4, 9, 12, 15).
# - [ ] **R3.** Both fix designs propose a fix for issue 12.
# - [ ] **R4.** The six whiteboard verdicts come from one rule, and the two borderline ones are named.
# - [ ] **R5.** Four runs in all, one per design per capability, and at most 5 model calls.
#
# **Make it yours.** Pick a seventh capability (for example "post a status update to chat"). Write its five facts, run the rule, and say whether the measurements would change it.

# %% [markdown]
# ## Build it
# ### 1. Setup (no model)
# The notebook reuses Trackr's data from lesson 03, the triage-agent from lesson 18 and the fix-agent from lesson 22. Nothing here calls a model. The ports are this lesson's: 8261 and 8262, inside 8260 to 8269.

# %%
import sys, json, socket, asyncio, logging
from pathlib import Path
sys.path.insert(0, "..")                         # so llm_setup and llm_replay import
import llm_replay                                # starts in step 5, before the first model call
import httpx, uvicorn
from typing_extensions import TypedDict
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from google.protobuf.json_format import MessageToDict
for name in ("httpx", "httpx._client", "uvicorn", "a2a", "mcp"):   # keep the INFO request, server and card logs out of the output
    logging.getLogger(name).setLevel(logging.WARNING)

APPS = {p: Path(f"../apps/{p}").resolve() for p in ("03", "18", "22")}
for p in APPS.values():
    assert p.exists(), f"missing {p}: run the earlier lesson that writes it first"
sys.path[:0] = [str(APPS["03"]), str(APPS["18"]), str(APPS["22"])]
from trackr_server import ISSUES                 # lesson 03's Trackr data
import batch_triage_agent, fix_agent             # lesson 18's triage-agent, lesson 22's fix-agent
TRIAGE_PORT, FIX_PORT = 8261, 8262
TRIAGE_IDS = [4, 9, 12, 15]
llm = None                                       # set in step 5; None means the scripted fallbacks
print(f"Trackr issues: {len(ISSUES)} | triage-agent port {TRIAGE_PORT} | fix-agent port {FIX_PORT}")

# %% [markdown]
# ### 2. The whiteboard (no model)
# Six capabilities of the ops desk. Decide each one as **MCP tool**, **MCP Task** or **A2A agent**. Ask five questions about each: Does the caller need a typed answer? Is it one short call? Is another owner involved, and must its internals stay opaque? Must it plan or ask back? Does it need model judgement?
#
# 1. count issues for one team
# 2. export a report of all open issues
# 3. triage a batch of issues into bug, feature or question
# 4. propose a fix for one issue
# 5. ask a vendor's security agent whether a change is safe
# 6. render a board of open issues per team

# %%
# your code here: replace each None with "MCP tool", "MCP Task" or "A2A agent"
my_answers = {
    "count issues": None,
    "export a report": None,
    "triage": None,
    "propose a fix": None,
    "ask a vendor's security agent": None,
    "render a board": None,
}

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below. If you left the answers as None, the hidden cell prints 0 of 6.

# %% tags=["solution"]
FACTS = {  # typed output, one short call, other owner or opaque, plans or asks back, needs model judgement
    "count issues":                  (True,  True,  False, False, False),
    "export a report":               (True,  False, False, False, False),
    "triage":                        (True,  True,  False, False, True),
    "propose a fix":                 (True,  True,  True,  False, True),   # typed: the MCP tool returns a Proposal
    "ask a vendor's security agent": (False, False, True, True,  True),
    "render a board":                (True,  True,  False, False, False),
}

def decide(typed, short, other_owner, plans, judgement):
    """The rule. typed and judgement do not change the verdict; they mark the borderline cases.
    A borderline case is one where the measurements tie and the ownership fact (other_owner) decides."""
    if other_owner or plans:
        return "A2A agent"          # another owner keeps it opaque, or it must plan or ask back
    if not short:
        return "MCP Task"           # deterministic but takes minutes: a handle the caller polls
    return "MCP tool"               # one short call, owned here

VERDICT = {name: decide(*facts) for name, facts in FACTS.items()}
BORDERLINE = [name for name, f in FACTS.items() if f[4] and f[1]]   # one short call, but a model judges
for name, verdict in VERDICT.items():
    print(f"{name:30} {verdict}")
print("borderline:", BORDERLINE)
matched = [n for n in VERDICT if my_answers[n] == VERDICT[n]]
print(f"your whiteboard matched {len(matched)} of {len(VERDICT)}")

# %% [markdown]
# ### 3. Serve the two A2A agents and read their cards (no model)
# Each agent runs as a task of this notebook's loop, as in lesson 22. The client sends its local calls through `SocketTransport`, which the recorder skips. The counter `REQUESTS` counts those HTTP requests, so the round trips in step 6 are measured, not guessed.

# %%
REQUESTS = {"n": 0}                                           # HTTP requests to the local A2A agents
_SOCKET_CALL = httpx.AsyncHTTPTransport.handle_async_request  # saved before llm_replay wraps httpx

class SocketTransport(httpx.AsyncBaseTransport):
    """httpx's socket transport, called directly: local calls are counted, not recorded."""
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        REQUESTS["n"] += 1
        return await _SOCKET_CALL(self.inner, request)

    async def aclose(self):
        await self.inner.aclose()

# %% [markdown]
# `Server` serves one ASGI app as a task of this loop. It answers only after its probe path returns 200. The A2A client below reads each card through the same transport.

# %%
class Server:
    """One ASGI app served as a task of this loop. It answers once the probe path returns 200."""
    def __init__(self, app, port: int, probe: str):
        self.port, self.url, self.probe = port, f"http://127.0.0.1:{port}", probe
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "Server":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(transport=SocketTransport(), timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + self.probe)).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass                                      # not up yet
                await asyncio.sleep(0.1)
        raise RuntimeError(f"{self.url}{self.probe} did not answer in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

# %% [markdown]
# The client side: read a card, make a client from it, and send one message per answer. The agents never see the caller's code.

# %%
async def a2a_client_for(url: str):
    """Read the card at url and make a client from it. Returns (card, client)."""
    http = httpx.AsyncClient(transport=SocketTransport(), timeout=60)
    card = await A2ACardResolver(http, url).get_agent_card()
    return card, await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))

# %% [markdown]
# `ask_agent` sends one message and waits for the Task, as lesson 22 does. It returns the artifact text, which is the answer.

# %%
async def ask_agent(client, text: str) -> str:
    """Send one message, wait for the Task, return the artifact text."""
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    task = None
    async for chunk in client.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            task = chunk.task
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED", task.status
    return get_artifact_text(task.artifacts[0])

# %% [markdown]
# Start both agents and read their cards. The card size and the discovery request count are the first measurements.

# %%
triage_server = await Server(batch_triage_agent.build_app(batch_triage_agent.build_card(TRIAGE_PORT)),
                             TRIAGE_PORT, "/.well-known/agent-card.json").start()
fix_server = await Server(fix_agent.build_app(fix_agent.build_card(FIX_PORT)),
                          FIX_PORT, "/.well-known/agent-card.json").start()

agents = {}
for name, server in (("triage", triage_server), ("fix", fix_server)):
    before = REQUESTS["n"]
    card, client = await a2a_client_for(server.url)
    agents[name] = {"card": card, "client": client,
                    "discovery_requests": REQUESTS["n"] - before,
                    "discovery_bytes": len(json.dumps(MessageToDict(card)))}
    print(f"{card.name}: skills {[s.id for s in card.skills]} | card {agents[name]['discovery_bytes']} bytes "
          f"| discovery requests {agents[name]['discovery_requests']}")

# %% [markdown]
# ### 4. The same two capabilities as MCP tools (no model)
# Both designs use the same code for the work: `classify_lines` from lesson 18 and `propose` from lesson 22. Only the protocol around it changes. The tools live on one in-memory MCP server, so no subprocess is needed. Defining and listing the tools calls no model.

# %%
ops = MCPServer("Trackr ops tools")

class Triage(TypedDict):
    id: int
    label: str

class Proposal(TypedDict):
    id: int
    proposal: str

# %% [markdown]
# Two MCP tools on one server. Each one does the same work as its A2A twin: `triage_issues` calls `classify_lines`, and `propose_fix` calls `propose`. The triage tool takes a batch of ids and returns typed rows.

# %%
from mcp.server.mcpserver.exceptions import ToolError

@ops.tool(title="Triage issues", annotations=ToolAnnotations(readOnlyHint=True))
async def triage_issues(ids: list[int]) -> list[Triage]:
    """Label each issue as bug, feature or question. One model call for the whole batch."""
    lines = "\n".join(f"{i['id']}: {i['title']}" for i in ISSUES if i["id"] in ids)
    text, _ = await batch_triage_agent.classify_lines(lines)
    rows = [line.split(":", 1) for line in text.splitlines() if ":" in line]
    return [{"id": int(a), "label": b.strip()} for a, b in rows if a.strip().isdigit()]

@ops.tool(title="Propose a fix", annotations=ToolAnnotations(readOnlyHint=True))
async def propose_fix(issue_id: int) -> Proposal:
    """Propose a fix for one open issue in two sentences. One model call."""
    issue = next((i for i in ISSUES if i["id"] == issue_id), None)
    if issue is None:
        raise ToolError(f"no issue {issue_id}")          # the caller reads this message as a tool error
    text, _ = await fix_agent.propose(f"{issue['id']}: {issue['title']}")
    return {"id": issue_id, "proposal": text}

async def discover(name: str):
    """Discovery for one MCP tool: list_tools is one round trip. Returns (definition bytes, round trips)."""
    async with Client(ops) as c:
        tool = next(t for t in (await c.list_tools()).tools if t.name == name)
    return len(json.dumps(tool.model_dump(mode="json", exclude_none=True))), 1

for name in ("triage_issues", "propose_fix"):
    size, rt = await discover(name)
    print(f"MCP tool {name}: definition {size} bytes | discovery round trips {rt}")

# %% [markdown]
# ### 5. Run both designs for both borderline capabilities (`needs-llm`)
# The model cell starts this notebook's recording. Four runs follow, one per design per capability, and each makes one model call. That makes four calls in all, within the budget of five. A tool call is one round trip (`call_tool`). An A2A answer is one round trip too (`message/send`), counted by `REQUESTS`.

# %% [markdown]
# A thin counter around the real model. It does not change what the model returns. It counts the calls the agents make, so the table can show them, replayed or recorded.

# %%
class CountedModel:
    """The real model with a counter: each ainvoke is one model call, recorded or replayed."""
    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    async def ainvoke(self, *args, **kwargs):
        self.calls += 1
        return await self.inner.ainvoke(*args, **kwargs)


def model_calls() -> int:
    return llm.calls if llm is not None else 0               # no model here: no calls

# %% [markdown]
# Start the recording and wrap the model. This is the only cell that calls `get_llm`. It prints nothing, and the next cells use the same `llm`.

# %% tags=["needs-llm"]
from llm_setup import get_llm
import logging
logging.getLogger("vcr").setLevel(logging.WARNING)           # the recorder logs file paths and the project id
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
llm_replay.start("26_checkpoint-exit-test")                  # first: record or replay this notebook's model calls
llm = CountedModel(get_llm())                                # Gemini by default; the budget is 4 calls
batch_triage_agent.LLM = fix_agent.LLM = llm

# %% [markdown]
# Triage first: the MCP tool, then the A2A agent, on the same four issues. Each design makes one model call.

# %% tags=["needs-llm"]
RUNS = []

async def run_mcp(capability, name, args, discovery):
    """One MCP tool call. Returns the answer and the round trips."""
    calls = model_calls()
    async with Client(ops) as c:
        res = await c.call_tool(name, args)
    out = res.structured_content
    RUNS.append({"capability": capability, "design": "MCP tool", "typed": True,
                 "answer": out.get("result", out), "round_trips": 1,
                 "model_calls": model_calls() - calls,
                 "discovery_bytes": discovery[0], "discovery_rt": discovery[1]})

# %% [markdown]
# The A2A side sends one message and reads one answer. Its round trips are counted by `REQUESTS`.

# %% tags=["needs-llm"]
async def run_agent(capability, agent, text):
    """One A2A message. Returns the artifact text and the HTTP requests the answer took."""
    calls, before = model_calls(), REQUESTS["n"]
    answer = await ask_agent(agents[agent]["client"], text)
    RUNS.append({"capability": capability, "design": "A2A agent", "typed": False,
                 "answer": answer, "round_trips": REQUESTS["n"] - before,
                 "model_calls": model_calls() - calls,
                 "discovery_bytes": agents[agent]["discovery_bytes"],
                 "discovery_rt": agents[agent]["discovery_requests"]})

triage_lines = "\n".join(f"{i['id']}: {i['title']}" for i in ISSUES if i["id"] in TRIAGE_IDS)
await run_mcp("triage", "triage_issues", {"ids": TRIAGE_IDS}, await discover("triage_issues"))
await run_agent("triage", "triage", triage_lines)
for r in RUNS:
    print(f"{r['design']:10} triage: {r['answer']}")

# %% [markdown]
# Both designs agree, but the sample is small.

# %% [markdown]
# Then the fix proposal for issue 12, the same two designs. Two more model calls, so four in all.

# %% tags=["needs-llm"]
issue12 = next(i for i in ISSUES if i["id"] == 12)
await run_mcp("propose a fix", "propose_fix", {"issue_id": 12}, await discover("propose_fix"))
await run_agent("propose a fix", "fix", f"{issue12['id']}: {issue12['title']}")
for r in RUNS[2:]:
    print(f"{r['design']:10} fix: {r['answer']}")

# %% [markdown]
# ### 6. Compare the designs and pass the exit test
# The table prints only what was measured: definition size, round trips, model calls and whether the answer is typed. Latency is left out on purpose, because it changes from run to run. Then the rule gives each verdict, and the requirements are checked.

# %%
print(f"{'capability':12} {'design':10} {'definition B':>12} {'discovery rt':>12} {'answer rt':>9} {'model calls':>11} {'typed':>6}")
for r in RUNS:
    print(f"{r['capability']:12} {r['design']:10} {r['discovery_bytes']:>12} {r['discovery_rt']:>12} "
          f"{r['round_trips']:>9} {r['model_calls']:>11} {str(r['typed']):>6}")
print()
for cap in BORDERLINE:
    print(f"{cap}: the rule says {VERDICT[cap]}")

# %% [markdown]
# ### 7. Requirements
# Each line is checked from the runs above. A FAIL means a run did not happen or a count is off.

# %%
def answer_of(capability: str, design: str):
    """The answer of one run, or None when that run did not happen."""
    return next((r["answer"] for r in RUNS if r["capability"] == capability and r["design"] == design), None)

mcp_triage, a2a_triage = answer_of("triage", "MCP tool"), answer_of("triage", "A2A agent")
mcp_fix, a2a_fix = answer_of("propose a fix", "MCP tool"), answer_of("propose a fix", "A2A agent")
checks = {
    "R1": {agents[k]["card"].name for k in agents} == {"triage-agent", "fix-agent"},
    "R2": mcp_triage is not None and a2a_triage is not None
          and sorted(row["id"] for row in mcp_triage) == TRIAGE_IDS
          and all(any(line.startswith(f"{i}:") for line in a2a_triage.splitlines()) for i in TRIAGE_IDS),
    "R3": mcp_fix is not None and a2a_fix is not None and mcp_fix["id"] == 12 and bool(mcp_fix["proposal"]) and bool(a2a_fix),
    "R4": BORDERLINE == ["triage", "propose a fix"] and len(VERDICT) == 6,
    "R5": len(RUNS) == 4 and model_calls() <= 5,
}
if not RUNS:
    print("R2 to R5 need the model runs: skipped here. Record or replay the lesson to see them.")
for line, ok in checks.items():
    if RUNS or line == "R1":
        print(line, "PASS" if ok else "FAIL")

# %% [markdown]
# Stop both agents and save the recording. This cell runs last, even when the checks above fail.

# %%
await triage_server.stop()
await fix_server.stop()
llm_replay.stop()                                            # last: saves the recording

# %% [markdown]
# ## Reference solution
# Try the whiteboard and the borderline reasoning first. The hidden cell is the reference reading of the measurements. Read it after you have made your own call.

# %% tags=["solution"]
print("triage: MCP tool. Both designs cost one round trip and one model call. The MCP definition is larger (760 bytes against 680), so cost does not decide. Typed labels and a team that owns the triage code do.")
print("propose a fix: A2A agent. The MCP definition is smaller (541 against 657 bytes), and the answers are identical, so the numbers favour the tool. Ownership decides: the fix prompt belongs to another team that changes it on its own release, and the caller should not hold that prompt.")
print("export a report: MCP Task, not A2A. It is deterministic; only its duration asks for a handle (lesson 13a).")

# %% [markdown]
# ## Common mistakes
# A lookup in a tool with no default fails with a bare error, and the caller learns nothing. Return a clear error the caller can read, as `propose_fix` does. The cell below shows the bare version.

# %% tags=["raises-exception"]
issue = next(i for i in ISSUES if i["id"] == 99)            # wrong: no default, and issue 99 does not exist

# %% [markdown]
# The fix gives the lookup a default and a line the caller can read.

# %%
issue = next((i for i in ISSUES if i["id"] == 99), None)
if issue is None:
    print("no issue 99")

# %% [markdown]
# The same mistake through the tool. `propose_fix` checks the id first and raises a `ToolError`, so the caller gets `is_error` and a message it can read. No model is called here.

# %%
async with Client(ops) as c:
    res = await c.call_tool("propose_fix", {"issue_id": 99})
print("is_error:", res.is_error, "|", res.content[0].text)

# %% [markdown]
# ## Key terms
# - **MCP tool** — a typed function the host calls in one short request (lesson 03).
# - **MCP Task** — a handle for deterministic work that takes minutes (lesson 13a).
# - **A2A agent** — a remote agent with its own card, task and internals (lessons 08, 18).
# - **Agent Card** — the JSON an A2A agent publishes so callers can find its skills (lesson 08).
# - **Borderline capability** — one short call that needs model judgement; the rule alone cannot decide it.
# - **Round trip** — one request and its answer, counted per design.
