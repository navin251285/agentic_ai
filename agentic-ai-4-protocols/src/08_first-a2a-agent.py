# %% [markdown]
# # 08 · Your first A2A agent: Agent Card, executor and client
# Level L2 · Part 2 · core · ~35 min · builds on 05

# %% [markdown]
# ## Goal
# By the end you have written an Agent Card by hand, served it at `/.well-known/agent-card.json`, and run a `triage-agent` whose executor asks a real model to classify Trackr issue 4 as bug, feature or question. A client finds the agent from its card alone, sends one message, and reads the answer from the Task's artifact.

# %% [markdown]
# ## The idea
# MCP connects an agent to tools. A2A connects an agent to another agent, and that agent stays **opaque**: you can call it and read what it publishes, but not its prompts, model or tools. It publishes an **Agent Card**, a JSON document with its name, URL and skills. Clients find the card at `/.well-known/agent-card.json`.
#
# The agent's logic lives in an **AgentExecutor**. The SDK calls its `execute` method for each message. The executor writes its answer as an **Artifact** made of **Parts**. A **Message** is one turn of talk. A **Task** records the work and its state, such as `COMPLETED`.
#
# Analogy: a restaurant. The card is the menu and the address. The executor is the kitchen. The client orders from the menu and never sees the kitchen.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client (a2a-sdk)
#   participant S as triage-agent (server)
#   participant M as Model
#   C->>S: GET /.well-known/agent-card.json
#   S-->>C: Agent Card: name, URL, skills
#   C->>S: SendMessage: Message with one text Part
#   S->>M: classify the issue
#   M-->>S: bug
#   S-->>C: Task COMPLETED, Artifact "bug"
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the example
# The running example is Trackr issue 4, "App crashes when photo is rotated". The agent reads the title and answers bug, feature or question. The first cell gives the notebook its imports and loads the issue. The model is picked later, so this cell needs no key.

# %%
import sys, json
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
Path("../apps/08").mkdir(parents=True, exist_ok=True)   # the server files go here
sys.path.insert(0, str(Path("../apps/08").resolve()))
ISSUES = json.loads(Path("../data/trackr_05b_issues.json").read_text())
ISSUE = next(i for i in ISSUES if i["id"] == 4)
PORT = 9108                                    # fixed localhost port for this lesson
print(ISSUE["id"], ISSUE["title"], "|", ISSUE["team"], "| port", PORT)

# %% [markdown]
# ### 2. Write the Agent Card by hand
# The card is a protobuf message from the `a2a-sdk` 1.x types. The file below builds it in plain code. It names the agent, gives the URL and protocol binding it answers on, and lists one skill. The card does not hold the prompt or the model. Those stay inside the agent.

# %%
%%writefile ../apps/08/triage_card.py
"""Lesson 08: the triage-agent's Agent Card, built as an A2A AgentCard (protobuf) by hand."""
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

PORT = 9108

def build_card(port: int = PORT) -> AgentCard:
    return AgentCard(
        name="triage-agent",
        description="Classifies a Trackr issue title as bug, feature or question.",
        version="1.0.0",
        supported_interfaces=[AgentInterface(
            url=f"http://127.0.0.1:{port}/",      # where the JSON-RPC calls go
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(
            id="classify_issue",
            name="Classify an issue",
            description="Reads an issue title and answers bug, feature or question.",
            tags=["triage", "classification"],
            examples=["App crashes when photo is rotated"],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        )],
    )

# %% [markdown]
# The next cell imports the card and prints it as JSON, the way it goes on the wire. `MessageToDict` turns the protobuf into a plain dictionary. Read the field names: the wire uses camelCase, so `supported_interfaces` shows as `supportedInterfaces`.

# %%
import socket, threading, time
import httpx, uvicorn
from starlette.applications import Starlette
from a2a.server.routes import create_agent_card_routes
from google.protobuf.json_format import MessageToDict
from triage_card import build_card
card = build_card()
print(json.dumps(MessageToDict(card), indent=2)[:900])

# %% [markdown]
# ### 3. Serve the card alone and fetch it
# A server is needed to publish the card. The helper below runs any ASGI app in a thread of this notebook. It polls the card URL until the server answers, so no fixed `sleep` is needed. The first app has only the card route, with no executor yet. The client-side fetch uses plain `httpx`, so you can see the raw JSON.

# %%
class ServerThread:
    """One ASGI app in a thread of this notebook (model calls stay in this process)."""
    def __init__(self, app, port: int):
        self.port, self.url = port, f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout: float = 15.0) -> "ServerThread":
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", self.port)) != 0, f"port {self.port} is already in use"
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if httpx.get(self.url + "/.well-known/agent-card.json", timeout=1).status_code == 200:
                    return self
            except httpx.TransportError:
                pass                              # not up yet
            time.sleep(0.1)
        raise RuntimeError("the agent did not answer its card URL in time")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

# %% [markdown]
# Now run the server with the card route only, fetch the card, and stop the server.

# %%
card_only = ServerThread(Starlette(routes=create_agent_card_routes(card)), PORT).start()
reply = httpx.get(card_only.url + "/.well-known/agent-card.json")
print("status:", reply.status_code, "| type:", reply.headers["content-type"].split(";")[0])
print("name:", reply.json()["name"], "| skills:", [s["id"] for s in reply.json()["skills"]])
card_only.stop()

# %% [markdown]
# The card is now public, and anyone who knows the URL can read it. No agent logic runs yet. The card alone is enough for a client to learn the name, the URL and the skills.

# %% [markdown]
# ### 4. Write the AgentExecutor
# The executor is the agent. The SDK calls `execute` once per incoming message. It starts work, classifies the issue, adds the answer as an artifact and completes the task. The model is a module variable `LLM`, set by the next model cell. If no model is set, the executor uses a keyword rule instead, and it names the artifact `scripted`. So the artifact's name always says who answered.

# %%
%%writefile ../apps/08/triage_agent.py
"""Lesson 08: the triage-agent. An AgentExecutor that classifies one issue, and the A2A app that serves it."""
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCard
from starlette.applications import Starlette

LABELS = ("bug", "feature", "question")
LLM = None   # the notebook sets a real model here; None means the scripted fallback

def scripted_label(text: str) -> str:
    """Keyword fallback with no model. Its answers are labelled 'scripted'."""
    t = text.lower()
    if any(w in t for w in ("crash", "error", "fails", "does nothing")):
        return "bug"
    if any(w in t for w in ("add", "support", "would be nice")):
        return "feature"
    return "question"

async def classify(text: str) -> tuple[str, str]:
    if LLM is None:
        return scripted_label(text), "scripted"
    reply = await LLM.ainvoke("Classify this issue as exactly one word: bug, feature or question.\nIssue: " + text)
    words = reply.text.strip().lower().split()
    word = words[0].strip(".,:") if words else ""
    return (word if word in LABELS else "unknown"), "model"

class TriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:   # first message: the Task must exist before any status update
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        label, source = await classify(get_message_text(context.message))
        await updater.add_artifact(parts=[new_text_part(label)], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

def build_app(card: AgentCard) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=TriageExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])

# %% [markdown]
# The executor is in a file, so you can read it in full. Three things to notice: the executor never returns a value, it writes to an `EventQueue` through a `TaskUpdater`; the answer is an artifact, not a return value; and `build_app` puts the card route and the JSON-RPC route on one Starlette app.

# %% [markdown]
# ### 5. A real model behind the executor (`needs-llm`)
# This cell gets the course's default model and gives it to the executor. `get_llm` starts the recording or the replay for this lesson. The lesson makes one model call, the classification, inside the agent. The client makes no model call. If the cell is skipped, `LLM` stays `None` and the scripted fallback runs.

# %% tags=["needs-llm"]
import triage_agent
from llm_setup import get_llm
import llm_replay
llm = get_llm("08_first-a2a-agent", max_calls=1)
triage_agent.LLM = llm
print("model set for the triage-agent executor")

# %% [markdown]
# If the model cell was skipped, the executor is still `None` and the next cells use the fallback. Nothing else changes.

# %%
import triage_agent
if triage_agent.LLM is None:
    print("no model here: the executor will use the scripted keyword rule (artifact name 'scripted')")

# %% [markdown]
# ### 6. Start the full agent
# Now the agent gets its executor, a task store and both routes. The card route is the same as before. The JSON-RPC route at `/` takes the messages. `InMemoryTaskStore` keeps tasks in this process's memory, which is fine for a lesson.

# %%
from triage_agent import build_app
agent = ServerThread(build_app(card), PORT).start()
print("triage-agent is up at", agent.url, "| card at /.well-known/agent-card.json")

# %% [markdown]
# ### 7. The client finds the agent from its card
# The client never imports the agent. It asks the card URL for the card, then creates a client from that card. `A2ACardResolver` does the fetch. `create_client` picks the transport the card names (`JSONRPC` here) and returns a client.

# %%
from a2a.client import A2ACardResolver, ClientConfig, create_client
async with httpx.AsyncClient(timeout=60) as http:
    found = await A2ACardResolver(http, agent.url).get_agent_card()
print("resolved:", found.name, "| URL:", found.supported_interfaces[0].url, "| skills:", [s.id for s in found.skills])
client = await create_client(agent=found, client_config=ClientConfig(streaming=False))

# %% [markdown]
# ### 8. Send one message and read the artifact
# A message has a role and a list of parts. The role is an enum, `Role.ROLE_USER`. The client sends one text part with the issue title. It gets back the Task. The loop below keeps the last Task it receives. Then it reads the state and the artifact. The artifact's name tells you who answered, the model or the scripted rule.

# %%
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
request = SendMessageRequest(message=new_text_message(ISSUE["title"], role=Role.ROLE_USER))
task = None
async for chunk in client.send_message(request):
    if chunk.WhichOneof("payload") == "task":
        task = chunk.task
artifact = task.artifacts[0]
print("state:", TaskState.Name(task.status.state))
print("answered by:", artifact.name, "| label:", get_artifact_text(artifact))

# %% [markdown]
# If the model cell was skipped, this same cell still runs, because the agent falls back to the scripted rule. It prints `answered by: scripted`. The label should match the model's answer for this issue.

# %% [markdown]
# ## At work
# - Production agents publish a card at the well-known path, and other teams read the skills from it. Cards are cached with ETag and Cache-Control, and signed so a client can detect a spoofed card → lesson 37.
# - The in-memory task store used here loses every task when the process restarts or a second replica takes the call. Production agents use a database task store and a shared event stream behind a load balancer → lesson 32.
# - One word is the easy case. Real agents take minutes and ask follow-up questions, so they need the full Task lifecycle: input-required, multi-turn and streaming → lesson 09.

# %% [markdown]
# ## What just happened
# - The card was served at a fixed path, so a client found the agent's name, URL and skills without any code from the agent.
# - The executor wrote its answer as an artifact on a Task. The executor set the Task to `WORKING`, then to `COMPLETED`. The client read the artifact from the finished task.
# - The client never saw the prompt, the model or the keyword rule. It saw only the card and the replies. That is what opaque means.
# - One model call happened, inside the agent. The client made none, and the card does not change what the model sees.

# %% [markdown]
# ## Common mistakes
# The card is not at `/agent.json` or any other path you invent. Clients look only at `/.well-known/agent-card.json`. A wrong path is a 404, and `raise_for_status()` turns it into an error:

# %% tags=["raises-exception"]
wrong = httpx.get(agent.url + "/agent.json")
wrong.raise_for_status()           # 404: the card lives at /.well-known/agent-card.json

# %% [markdown]
# Fix: fetch `/.well-known/agent-card.json`, or let `A2ACardResolver` build that path for you.
#
# The role of a message is an enum. A string such as `"user"` is the 0.3 style and fails in the 1.x SDK:

# %% tags=["raises-exception"]
new_text_message("App crashes when photo is rotated", role="user")

# %% [markdown]
# Fix: pass `Role.ROLE_USER`, the 1.x enum name.

# %% [markdown]
# ## Try it
# Build a second Agent Card in memory, without a server and without a model. Call it `severity-agent` with one skill `rate_severity` and URL `http://127.0.0.1:9109/`. Use the same `AgentInterface` and `AgentSkill` types as the card in step 2. Print its name, its URL and its skill ids. Then check that the two cards have different names.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **Agent Card** — the public JSON document an A2A agent publishes: name, URL, protocol binding, skills and capabilities.
# - **/.well-known/agent-card.json** — the fixed path where a client finds an agent's card.
# - **AgentExecutor** — the server class with `execute` and `cancel`. It holds the agent's logic and is called once per message.
# - **Message** — one turn of talk in A2A. It has a role (`ROLE_USER` or `ROLE_AGENT`) and a list of parts.
# - **Part** — one piece of content in a message or artifact: text, data, a file or a URL.
# - **Artifact** — the output of an A2A task: a named list of parts that the executor adds.
# - **A2A Task** — the record of one piece of work, with a state such as `TASK_STATE_COMPLETED`.

# %% [markdown]
# Stop the agent, close the client and tell the recorder the lesson is done.

# %%
import llm_replay
agent.stop()
await client.close()
llm_replay.stop()        # saves the recording if a model ran; a no-op otherwise
print("lesson 08 done: a card, an executor and a client; the agent stayed opaque")
