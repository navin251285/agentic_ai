# %% [markdown]
# # 18 · Delegating over A2A: when to call a tool and when to hand off
# Level L3 · Part 4 · core · ~35 min · builds on 05, 08

# %% [markdown]
# ## Goal
# By the end you have an orchestrator with two tools. One is an MCP tool it controls, `read_open_count`. The other is a delegation tool, `classify_issues`, that sends issues 4, 9 and 15 to a remote A2A agent. One model call picks the tool, one remote model call classifies the batch, and the artifact that comes back is the answer. You can say which capability is a tool and which is an agent.

# %% [markdown]
# ## The idea
# An orchestrator has two kinds of help. For work it controls, such as counting issues or closing one, it calls an MCP tool: a plain function with a schema that runs the same way every time. For work that judges, plans or belongs to another team, it delegates to an A2A agent. The remote agent is a black box. The orchestrator sends one message with the issue titles and reads back the artifact. The artifact is a tool result, so it can be the final answer, and no second model call is needed to repeat it.
#
# Analogy: a manager with a database and a consultant. The database answers exact questions. The consultant gets a brief and returns a written report, and the manager passes that report on without rewriting it.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as User
#   participant O as Orchestrator (model)
#   participant T as Trackr (MCP)
#   participant A as triage-agent (A2A, opaque)
#   U->>O: Classify issues 4, 9 and 15
#   O->>O: model call 1: asks for classify_issues
#   O->>T: read the titles (MCP, no model)
#   O->>A: one message with three lines
#   A->>A: model call: the remote's only call
#   A-->>O: artifact with three labels
#   O-->>U: the artifact is the answer, no third call
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 4. If you can answer all of these, skip to lesson 22 (the checkpoint).
# 1. Your own code has a deterministic, schema'd function. A partner's agent plans for minutes. Which one is an MCP tool and which is an A2A agent, and why?
# 2. Where does a client find an A2A agent's card, and what does the card leave out?
# 3. Where does an A2A agent's answer go: a return value, or an artifact on a task?
# 4. A run must pause until a person approves a change. What does the server send, and what does the client send to resume? (lesson 19)
# 5. What does an Agent Skill's SKILL.md tell the agent, and when is it loaded? (lesson 21)

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the example
# The running example is the Trackr team desk. Trackr is the lesson 03 server, the same one lesson 05 used. The triage-agent for this lesson is a new file: it takes a whole batch of issues and answers with one model call. The port is fixed to 9118, so lesson 08's agent on 9108 can keep running.

# %%
import sys
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
TRACKR = Path("../apps/03/trackr_server.py").resolve()
assert TRACKR.exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/18").mkdir(parents=True, exist_ok=True)   # the triage-agent file goes here
sys.path.insert(0, str(Path("../apps/18").resolve()))
PORT = 9118                                    # fixed localhost port for this lesson
llm = None                                     # filled by the model cell; stays None if that cell is skipped
print("Trackr server:", TRACKR.name, "| triage-agent port:", PORT)

# %% [markdown]
# ### 2. The orchestrator opens its own MCP connection to Trackr
# The orchestrator's code reads Trackr over MCP. It starts Trackr as a subprocess with `StdioServerParameters`, the same as lesson 05. A notebook runs each cell in its own task, so the connection is held by a small helper that keeps it open in one task until the last cell closes it. Trackr has no "get one issue" tool, so the code reads the open issues with `search_issues` and an empty text, which matches every title.

# %%
import asyncio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

class HeldClient:
    """One MCP connection that stays open across cells: it lives in its own task until close()."""
    async def start(self, params: StdioServerParameters) -> Client:
        self.ready, self.done = asyncio.Event(), asyncio.Event()
        self.task = asyncio.create_task(self._hold(params))
        await self.ready.wait()
        return self.client

    async def _hold(self, params: StdioServerParameters) -> None:
        async with Client(params) as client:
            self.client = client
            self.ready.set()
            await self.done.wait()

    async def close(self) -> None:
        self.done.set()
        await self.task

held = HeldClient()
trackr = await held.start(StdioServerParameters(command=sys.executable, args=[str(TRACKR)]))
tools = await trackr.list_tools()
print("Trackr tools:", [t.name for t in tools.tools])
open_now = await trackr.call_tool("search_issues", {"text": ""})
print("open issues over MCP:", len(open_now.structured_content["result"]), "| is_error:", open_now.is_error)

# %% [markdown]
# ### 3. Write the batch triage-agent
# The agent is a new file, `batch_triage_agent.py`, read it in full. It has the same parts as lesson 08: a card, an `AgentExecutor` and a Starlette app. Two things differ. The message holds several `id: title` lines, and the executor makes one model call for all of them. With no model, a keyword rule answers and the artifact is named `scripted`.

# %%
%%writefile ../apps/18/batch_triage_agent.py
"""Lesson 18: triage-agent for a batch. It reads one 'id: title' line per issue and answers in ONE model call."""
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

LLM = None   # the notebook sets a real model here; None means the scripted fallback

def build_card(port: int) -> AgentCard:
    return AgentCard(
        name="triage-agent",
        description="Classifies Trackr issues, one line per issue, as bug, feature or question.",
        version="1.0.0",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{port}/",
                                             protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(id="classify_issues", name="Classify issues",
                           description="Reads 'id: title' lines and answers '<id>: <label>' for each line.",
                           tags=["triage"], examples=["4: App crashes when photo is rotated"],
                           input_modes=["text/plain"], output_modes=["text/plain"])],
    )

def scripted_label(line: str) -> str:
    """Keyword rule with no model. Its answers are labelled 'scripted'."""
    t = line.lower()
    if any(w in t for w in ("crash", "error", "fails", "late", "drain", "does nothing")):
        return "bug"
    if any(w in t for w in ("add", "support", "would be nice")):
        return "feature"
    return "question"

async def classify_lines(text: str) -> tuple[str, str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if LLM is None:
        return "\n".join(f"{line.split(':')[0]}: {scripted_label(line)}" for line in lines), "scripted"
    prompt = ("Classify each issue as exactly one word: bug, feature or question.\n"
              "Reply with one line per issue, in the form '<id>: <label>', and nothing else.\n" + text)
    reply = await LLM.ainvoke(prompt)          # one model call for the whole batch
    return reply.text.strip(), "model"

class BatchTriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:       # the Task must exist before any status update
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        answer, source = await classify_lines(get_message_text(context.message))
        await updater.add_artifact(parts=[new_text_part(answer)], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

def build_app(card: AgentCard) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=BatchTriageExecutor(),
                                    task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])

# %% [markdown]
# ### 4. Serve the agent and let the client find it from its card
# The helper below serves an ASGI app as a task in this notebook's event loop. Lesson 08 used a thread. Here one loop runs the agent, the client and the model, so the model client is never used from two loops. The helper polls the card URL until the agent answers. The client then resolves the card and creates an A2A client from it. The orchestrator never imports the agent's code.

# %%
import socket, asyncio
import httpx, uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
import batch_triage_agent

# %% [markdown]
# The class below is the helper. It starts the agent, waits for its card, and stops it. Nothing in it is specific to triage.

# %%
class AgentServer:
    """One ASGI app served as a task of this notebook's event loop."""
    def __init__(self, app, port: int):
        self.port, self.url = port, f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "AgentServer":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + "/.well-known/agent-card.json")).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass                       # not up yet
                await asyncio.sleep(0.1)
        raise RuntimeError("the agent did not answer its card URL in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

# %% [markdown]
# Now start the agent on its port, then fetch its card the way any client does. The client gets the URL and the skills from the card, and nothing else.

# %%
card = batch_triage_agent.build_card(PORT)
agent = await AgentServer(batch_triage_agent.build_app(card), PORT).start()
async with httpx.AsyncClient(timeout=60) as http:
    found = await A2ACardResolver(http, agent.url).get_agent_card()
a2a_client = await create_client(agent=found, client_config=ClientConfig(streaming=False))
print("found:", found.name, "| URL:", found.supported_interfaces[0].url, "| skills:", [s.id for s in found.skills])

# %% [markdown]
# ### 5. The orchestrator's MCP tool: a function it controls
# A count is a deterministic, schema'd function over data the orchestrator owns. That is the MCP side of the decision. The tool calls Trackr's `count_open` through the MCP client, and the model sees only the tool's name, description and schema. The `@tool` decorator from LangChain turns the function into a tool the model can choose.

# %%
from langchain_core.tools import tool

@tool
async def read_open_count(team: str) -> int:
    """Count the open Trackr issues for one team: web, api, mobile or infra. Use it for plain counts."""
    reply = await trackr.call_tool("count_open", {"team": team})
    assert not reply.is_error, reply.content[0].text
    return reply.structured_content["result"]

# %% [markdown]
# ### 6. The delegation tool: hand the judgement to the remote agent
# `classify_issues` reads the titles through MCP, then sends them in one A2A message. The remote agent is opaque. The orchestrator sees only the card's skills and the artifact that comes back. The function returns the artifact text, and that text becomes the tool result.

# %%
async def open_titles(ids: list[int]) -> list[tuple[int, str]]:
    """Read the open issues over MCP and keep the ones asked for, in the order asked."""
    reply = await trackr.call_tool("search_issues", {"text": ""})
    by_id = {row["id"]: row["title"] for row in reply.structured_content["result"]}
    return [(i, by_id[i]) for i in ids if i in by_id]

@tool
async def classify_issues(issue_ids: list[int]) -> str:
    """Send these open Trackr issues to triage-agent, which classifies each as bug, feature or question. Use it for judgement, not for counting."""
    rows = await open_titles(issue_ids)
    text = "\n".join(f"{i}: {title}" for i, title in rows)
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    task = None
    async for chunk in a2a_client.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            task = chunk.task
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED"
    return get_artifact_text(task.artifacts[0])

# %% [markdown]
# ### 7. The orchestrator model chooses (`needs-llm`)
# The model sees both tools, and a system message says to use a tool for each step. Its first reply should ask for `classify_issues` with the three ids. That is the orchestrator's one model call. `get_llm` starts the recording or the replay for this lesson. The same model object then serves the triage-agent, so the remote's call is recorded too. It is the second and last call.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm
llm = get_llm("18_a2a-delegation", max_calls=2)
batch_triage_agent.LLM = llm                   # the remote agent answers with the same model
QUESTION = HumanMessage("Classify issues 4, 9 and 15 as bug, feature or question.")
SYSTEM = SystemMessage("You are the Trackr orchestrator. Use one tool for each step. Do not classify issues yourself.")
first = await llm.bind_tools([read_open_count, classify_issues]).ainvoke([SYSTEM, QUESTION])
print("orchestrator asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. The stand-in is labelled.

# %%
from langchain_core.messages import AIMessage
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "classify_issues", "args": {"issue_ids": [4, 9, 15]}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): orchestrator asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The orchestrator runs the tool it chose. The tool reads the titles over MCP, sends one A2A message, and waits for the Task. If the model cell ran, the triage-agent makes its one model call here. Its artifact comes back as the tool result.

# %%
call = next(c for c in first.tool_calls if c["name"] == "classify_issues")
result = await classify_issues.ainvoke(call)
print("tool status:", result.status)
print(result.text)

# %% [markdown]
# The artifact is the answer. The orchestrator does not send it back to the model for a third call, because nothing in it needs rewriting. If the model was skipped, the labels above come from the keyword rule.

# %%
if batch_triage_agent.LLM is None:
    print("(no model here: the labels above are the scripted keyword rule)")
print("final answer has", len(result.text.splitlines()), "lines, one per issue sent:", len(call["args"]["issue_ids"]))

# %% [markdown]
# ### 8. The decision, in one table
# Use the same test on every new capability. Ask whether it is a function you control with a fixed schema, or a worker that plans, takes minutes, asks questions or belongs to someone else.
#
# | The job | Pick | Why |
# |---|---|---|
# | Count open mobile issues | MCP tool | Deterministic, schema'd, you own the data |
# | Close issue 9 | MCP tool with a confirmation | A write you control; it needs an annotation and a check |
# | Classify a batch of issues | A2A agent | A judgement, opaque to you, one artifact back |
# | Draft and fix a bug | A2A agent | Long, multi-step, may ask the requester questions |

# %% [markdown]
# ## At work
# - Production teams expose stable actions as MCP tools and put judgement behind agents that other teams own. Agent cards are signed so a caller can check who answered → lesson 37.
# - The in-memory task store used here loses a delegated job when the process restarts. Production agents keep tasks in a database → lesson 32.
# - Real delegated jobs take minutes and ask follow-up questions, so they need streaming and input-required states, not one blocking call → lesson 09.
# - Once many agents are reachable, a gateway and a registry decide which orchestrator may call which agent → lesson 40.

# %% [markdown]
# ## What just happened
# - The orchestrator's model made one choice: `classify_issues` with three ids. It did not read titles or call the remote agent itself.
# - The orchestrator's code read the titles over MCP, sent one message, and waited for the Task to complete.
# - The triage-agent made one model call for all three lines. The orchestrator saw only the artifact.
# - The artifact came back as a tool result and was the answer, so no third model call happened.

# %% [markdown]
# ## Common mistakes
# `search_issues` returns a list, and the MCP SDK wraps a list under `"result"` in `structured_content`. Indexing the dictionary with `0` fails:

# %% tags=["raises-exception"]
ids_only = (await trackr.call_tool("search_issues", {"text": ""})).structured_content[0]   # KeyError: 0
print(ids_only)

# %% [markdown]
# Fix: read `structured_content["result"]`, then loop over the rows. The wrapper is the same for every list-valued tool.
#
# A second trap is silent. If you ask the delegate for an id that is not open, `open_titles` drops it and the batch is smaller than you asked. Check that the artifact has one line per id you sent.

# %% [markdown]
# ## Try it
# Use the `trackr` client from step 2. Call `count_open` for the team `mobile`, then call `search_issues` with the text `"push"`. Print both results. Check `is_error` on both calls. No model is needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **delegation tool** — a tool in the orchestrator's list whose code hands a task to another agent over A2A and returns that agent's artifact as the tool result.
# - **remote agent as a black box** — an agent the orchestrator can call and read, but not look inside. It sees only the card and the artifact.
# - **artifact back into the conversation** — the remote's output returned as a tool result. It can be the final answer, so the model needs no extra call to repeat it.
# - **MCP vs A2A decision** — use an MCP tool for a deterministic, schema'd function you control. Use an A2A agent for work that plans, takes long, asks questions, or belongs to another owner.

# %% [markdown]
# Close the connections and stop the agent. Then tell the recorder the lesson is done.

# %%
import llm_replay
await agent.stop()
await a2a_client.close()
await held.close()            # closes the Trackr connection and stops the subprocess
llm_replay.stop()             # saves the recording if a model ran; a no-op otherwise
print("lesson 18 done: MCP for what the orchestrator controls, A2A for the opaque agent")
