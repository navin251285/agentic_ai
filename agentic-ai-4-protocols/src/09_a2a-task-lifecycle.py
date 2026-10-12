# %% [markdown]
# # 09 · A2A tasks: lifecycle, multi-turn and streaming
# Level L2 · Part 2 · professional · ~40 min · builds on 08

# %% [markdown]
# ## Goal
# By the end you can drive one A2A task through its `TASK_STATE_*` states. You will pause a task for an answer with `INPUT_REQUIRED`, continue it in the same context, follow it by polling and by streaming, cancel it, and read a Task error as a `google.rpc.Status` with an `ErrorInfo`.

# %% [markdown]
# ## Why it matters
# Lesson 08 used one request and one answer. Real triage is not that simple. Without a task lifecycle, the same job looks like this:
#
# | Without task states | With task states (this lesson) |
# |---|---|
# | One HTTP reply. A triage that takes four minutes hits the client's timeout. | The agent returns a Task with an id at once. The client polls or streams it. |
# | The agent needs one more fact. It guesses or fails. | `INPUT_REQUIRED`: the agent asks, and the client answers in the same context. |
# | A runaway job cannot be stopped. | `CancelTask` moves the task to `CANCELED`. |
# | Each follow-up starts from zero. | `contextId` groups the turns, so the second answer sees the first. |
#
# You do not need this for a call that answers in a second. A plain function is enough then, or an MCP tool (lesson 03).

# %% [markdown]
# ## The idea
# A **Task** is a ticket with a state. It is like a repair ticket at a garage. It has one number (`taskId`), and all the talk about the same job shares one file (`contextId`). The ticket moves through states: it is `WORKING`, then it is `INPUT_REQUIRED` while the garage waits for the customer, then `COMPLETED`.
#
# Two kinds of end state matter. **Terminal** states (`COMPLETED`, `FAILED`, `CANCELED`, `REJECTED`) end the ticket. **Interrupted** states (`INPUT_REQUIRED`, `AUTH_REQUIRED`) pause it, and a new message with the same `taskId` restarts it. The client reads states from the Task and from a stream of `StreamResponse` events.

# %% [markdown]
# ## Picture
# ```mermaid
# stateDiagram-v2
#   [*] --> SUBMITTED
#   SUBMITTED --> WORKING
#   WORKING --> INPUT_REQUIRED: needs one more fact
#   INPUT_REQUIRED --> WORKING: client answers, same taskId
#   WORKING --> COMPLETED: artifact added
#   WORKING --> FAILED
#   WORKING --> CANCELED: CancelTask
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the example
# The running example is the Trackr triage again. Issue 4 has no severity in its title, so the agent must ask for one. The setup cell loads the issues and sets the port for this lesson (8090). Nothing here calls a model.

# %%
import sys, json
from pathlib import Path
sys.path.insert(0, "..")                       # so llm_setup and llm_replay import
Path("../apps/09").mkdir(parents=True, exist_ok=True)   # the server file goes here
sys.path.insert(0, str(Path("../apps/09").resolve()))
ISSUES = json.loads(Path("../data/trackr_05b_issues.json").read_text())
by_id = {i["id"]: i for i in ISSUES}
PORT = 8090                                    # fixed localhost port for this lesson
print(by_id[4]["title"], "| port", PORT)

# %% [markdown]
# ### 2. List the eight states and sort them
# The `TaskState` enum has nine values: `UNSPECIFIED` plus the eight you can see. The cell prints each one and marks it as terminal, interrupted or active. Only the terminal ones end the ticket.

# %%
from a2a.types import TaskState
TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}
INTERRUPTED = {"TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}
for name in TaskState.keys():
    kind = "unspecified" if name.endswith("UNSPECIFIED") else "terminal" if name in TERMINAL else "interrupted" if name in INTERRUPTED else "active"
    print(f"{name:28} {kind}")

# %% [markdown]
# ### 3. Write the executor with an interrupt
# The executor is in a file, as in lesson 08. It has three new parts. It reads every user message of the context, so the second turn sees the first. When no severity is given, it sets the task to `INPUT_REQUIRED` and returns. When a severity is there, it completes the task. The `cancel` method ends the task as `CANCELED`.

# %%
%%writefile ../apps/09/triage_agent.py
"""Lesson 09: the triage-agent with a task lifecycle. It asks for a severity (INPUT_REQUIRED),
reads the earlier turns of the same context, completes with an artifact and can be cancelled."""
import re
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Role
from starlette.applications import Starlette

LABELS = ("bug", "feature", "question")
LLM = None   # the notebook sets a real model here; None means the scripted fallback

def build_card(port: int) -> AgentCard:
    return AgentCard(
        name="triage-agent",
        description="Classifies a Trackr issue and asks for its severity when it is missing.",
        version="1.1.0",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{port}/", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(id="classify_issue", name="Classify an issue", description="Asks for severity, then answers bug, feature or question.",
                           tags=["triage"], examples=["App crashes when photo is rotated"], input_modes=["text/plain"], output_modes=["text/plain"])],
    )

def find_severity(text: str) -> str | None:
    """The severity the user typed, as in 'severity: high', or None."""
    found = re.search(r"severity:\s*(low|medium|high)", text.lower())
    return found.group(1) if found else None

def scripted_label(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("crash", "error", "fails", "does nothing")):
        return "bug"
    if any(w in t for w in ("add", "support", "would be nice")):
        return "feature"
    return "question"

async def classify(text: str) -> tuple[str, str]:
    if LLM is None:
        return scripted_label(text), "scripted"
    reply = await LLM.ainvoke("Classify this Trackr issue as exactly one word: bug, feature or question.\nIssue: " + text)
    words = reply.text.strip().lower().split()
    word = words[0].strip(".,:") if words else ""
    return (word if word in LABELS else "unknown"), "model"

def conversation_text(context: RequestContext) -> str:
    """Every user message in this context so far, oldest first."""
    earlier = list(context.current_task.history) if context.current_task is not None else []
    turns = [m for m in earlier if m.role == Role.ROLE_USER]
    if context.message.message_id not in {m.message_id for m in earlier}:
        turns.append(context.message)
    return "\n".join(get_message_text(m) for m in turns)

class TriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:   # first message of a new task
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        text = conversation_text(context)
        label, source = await classify(text)
        severity = find_severity(text)
        if severity is None:               # pause: the client must answer in this context
            ask = f"It looks like a {label}. How severe is it? Reply with: severity: low, medium or high."
            await updater.requires_input(message=updater.new_agent_message([new_text_part(ask)]))
            return
        await updater.add_artifact(parts=[new_text_part(f"{label}, severity {severity}")], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

def build_app(card: AgentCard) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=TriageExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])

# %% [markdown]
# The executor sends each update to the same `EventQueue`. An interrupt is one call, `requires_input`, and the question is an agent message. The task stays in `INPUT_REQUIRED` until the next message arrives. Note that the executor does not check the task id itself. The SDK routes a message with a known `taskId` to the right task.

# %% [markdown]
# ### 4. A real model behind the executor (`needs-llm`)
# This cell gives the executor a real model. Each turn that runs the classifier makes one call. The notebook plans four calls: issue 4 (ask), issue 4 (answer), issue 9 (streamed) and issue 1 (cancelled). That is within the limit of five. If the cell is skipped, the scripted keyword rule runs instead.

# %% tags=["needs-llm"]
import triage_agent
from llm_setup import get_llm
llm = get_llm("09_a2a-task-lifecycle", max_calls=4)
triage_agent.LLM = llm
print("model set for the triage-agent executor")

# %% [markdown]
# If the model cell was skipped, `LLM` stays `None` and the executor falls back to the keyword rule. The next cell says which one runs.

# %%
import triage_agent
if triage_agent.LLM is None:
    print("no model here: the executor uses the scripted keyword rule (artifact name 'scripted')")

# %% [markdown]
# ### 5. Start the agent and the client

# %% [markdown]
# The helper below runs an app in a thread of this notebook. It is a small file, so you can read it. It waits until the card answers. Threads keep the model calls in this process, so the recorder sees them.

# %%
%%writefile ../apps/09/server_thread.py
"""Lesson 09: run one ASGI app in a thread of the notebook process and stop it at the end."""
import socket, threading, time
import httpx, uvicorn

class ServerThread:
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
                pass                           # not up yet
            time.sleep(0.1)
        raise RuntimeError("the agent did not answer its card URL in time")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

# %% [markdown]
# Now start the agent, resolve its card and make the two clients. The client finds the agent from the card, as in lesson 08. One client is for normal calls, and one is for streams.

# %%
import httpx
from server_thread import ServerThread
from a2a.client import A2ACardResolver, ClientConfig, create_client
from triage_agent import build_app, build_card
agent = ServerThread(build_app(build_card(PORT)), PORT).start()
async with httpx.AsyncClient(timeout=60) as http:
    found = await A2ACardResolver(http, agent.url).get_agent_card()
print("resolved:", found.name, "| streaming:", found.capabilities.streaming)
client = await create_client(agent=found, client_config=ClientConfig(streaming=False))
streamer = await create_client(agent=found, client_config=ClientConfig(streaming=True))

# %% [markdown]
# ### 6. Turn 1: the agent asks for severity
# The first message has the issue title and no severity. The helper below sends a message and keeps the last Task it gets. The reply is `INPUT_REQUIRED`. The question is in the task's status message, not in an artifact. The `contextId` and `taskId` you need for turn 2 are on the Task.

# %%
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import CancelTaskRequest, GetTaskRequest, ListTasksRequest, Role, SendMessageRequest, SubscribeToTaskRequest, TaskState

def state_name(task) -> str:
    return TaskState.Name(task.status.state)

async def send(text: str, context_id: str = "", task_id: str = "") -> object:
    ids = {k: v for k, v in (("context_id", context_id), ("task_id", task_id)) if v}
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER, **ids))
    last = None
    async for chunk in client.send_message(request):
        if chunk.WhichOneof("payload") == "task":
            last = chunk.task
    return last

first = await send(by_id[4]["title"])
print("turn 1:", state_name(first), "| context", first.context_id[:8], "| task", first.id[:8])
print("agent asks:", get_message_text(first.status.message))

# %% [markdown]
# ### 7. Turn 2: answer in the same context
# The second message has the same `contextId` and `taskId`. This tells the server to continue the same ticket. The task moves back to `WORKING`, then to `COMPLETED`. The answer comes from a model call that reads both turns.

# %%
answer = await send("severity: high", context_id=first.context_id, task_id=first.id)
artifact = answer.artifacts[0]
print("turn 2:", state_name(answer), "| answered by:", artifact.name, "|", get_artifact_text(artifact))

# %% [markdown]
# ### 8. Poll the task and list the context
# `GetTask` reads one task, with its history if you ask for it. `ListTasks` lists the tasks of a context. Both are polls: they read the state and do not change it. Use them when a client cannot keep a stream open.

# %%
got = await client.get_task(GetTaskRequest(id=first.id, history_length=10))
print("get_task:", state_name(got), "| history roles:", [Role.Name(m.role) for m in got.history])
listed = await client.list_tasks(ListTasksRequest(context_id=first.context_id))
print("list_tasks:", len(listed.tasks), "task(s) in this context")

# %% [markdown]
# ### 9. Stream a task as it runs
# A stream sends one `StreamResponse` for each event. Each event holds one of: a task, a message, a status update or an artifact update. This request has the severity already, so the task never pauses. Read the events in order. Each status update carries a state, and each artifact update carries the artifact.

# %%
issue9 = by_id[9]["title"] + "\nseverity: low"
async for event in streamer.send_message(SendMessageRequest(message=new_text_message(issue9, role=Role.ROLE_USER))):
    kind = event.WhichOneof("payload")
    if kind == "status_update":
        print("statusUpdate:", TaskState.Name(event.status_update.status.state))
    elif kind == "artifact_update":
        print("artifactUpdate:", get_artifact_text(event.artifact_update.artifact))
    else:
        print("event:", kind)

# %% [markdown]
# ### 10. Reattach from a second client, then cancel
# Issue 1 pauses for severity. A client that lost its stream can reattach with `SubscribeToTask`. Here a second process does it: `resubscribe.py` is a small client with no model and no shared state. It prints the first event, which is the task itself, and exits. Subscribing needs a streaming client and a task that has not ended. Then this cell cancels the task. `CANCELED` is terminal, but the task is still there to read.

# %%
%%writefile ../apps/09/resubscribe.py
"""Lesson 09: a second client process reattaches to a paused task with SubscribeToTask."""
import asyncio, sys
import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.types import SubscribeToTaskRequest, TaskState

async def main(url: str, task_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as http:
        card = await A2ACardResolver(http, url).get_agent_card()
    client = await create_client(agent=card, client_config=ClientConfig(streaming=True))
    async for event in client.subscribe(SubscribeToTaskRequest(id=task_id)):
        state = TaskState.Name(event.task.status.state) if event.WhichOneof("payload") == "task" else "-"
        print("reattached, first event:", event.WhichOneof("payload"), "|", state)
        break                                  # the first event is enough; stop reading
    await client.close()

asyncio.run(main(sys.argv[1], sys.argv[2]))

# %% [markdown]
# Now the reattach runs. The cell sends the paused task's id to the second process, and prints what it gets back. Then it cancels the task.

# %%
import subprocess
waiting = await send(by_id[1]["title"])
print("waiting:", state_name(waiting))
proc = subprocess.run([sys.executable, "../apps/09/resubscribe.py", agent.url, waiting.id],
                      capture_output=True, text=True, timeout=60)
print(proc.stdout.strip() or proc.stderr[-300:])
canceled = await client.cancel_task(CancelTaskRequest(id=waiting.id))
print("cancel:", state_name(canceled))
print("still readable:", state_name(await client.get_task(GetTaskRequest(id=waiting.id))))

# %% [markdown]
# ### 11. Read the errors on the wire
# The JSON-RPC binding sends errors as an `error` object with a code, a message and details. The details follow the `google.rpc.Status` model. The first detail is a `google.rpc.ErrorInfo`, with a machine-readable `reason` and a `domain`. This cell sends a raw request with the `A2A-Version` and `A2A-Extensions` headers and asks for a task id that does not exist. This agent uses no extension, so its reply has no `A2A-Extensions` header.

# %%
async with httpx.AsyncClient(timeout=30) as http:
    reply = await http.post(agent.url + "/",
                            headers={"A2A-Version": "1.0", "A2A-Extensions": "https://example.com/ext/severity/v1"},
                            json={"jsonrpc": "2.0", "id": 1, "method": "GetTask", "params": {"id": "no-such-task"}})
print("http status:", reply.status_code, "| A2A-Extensions in reply:", reply.headers.get("a2a-extensions"))
error = reply.json()["error"]
print("code:", error["code"], "| message:", error["message"])
print("ErrorInfo:", error["data"][0]["reason"], "|", error["data"][0]["domain"])

# %% [markdown]
# ## At work
# - A production triage agent can wait hours for a human. It keeps the task in `INPUT_REQUIRED` and stores the context in a database, so any replica can pick the answer up → lesson 32.
# - Orchestrators call other agents with this same lifecycle. They poll or stream, and they cancel a task that runs too long → lesson 18.
# - When a remote agent needs a user's sign-in it moves to `AUTH_REQUIRED`. The sign-in itself is the OAuth client flow in lesson 16.

# %% [markdown]
# ## What just happened
# - The first message created a task in `WORKING`. The agent asked a question, and the task stopped in `INPUT_REQUIRED` with the same `taskId`.
# - The second message, with the same ids, continued that task. The second model call read both turns. The artifact is the final answer.
# - Polling and streaming read the same task. The stream sent the status and artifact events, and a late client could reattach with `SubscribeToTask`.
# - Cancelling moved the task to `CANCELED`. Errors come back as a JSON-RPC `error` with an `ErrorInfo` whose `reason` names the failure.

# %% [markdown]
# ## Common mistakes
# Cancelling a task that has already ended is an error. Here `first` is `COMPLETED`, so the cancel below fails:

# %% tags=["raises-exception"]
await client.cancel_task(CancelTaskRequest(id=first.id))   # first is COMPLETED: a terminal task cannot be cancelled

# %% [markdown]
# Fix: check the state first and cancel only a task that is not terminal. A message sent without the `taskId` is another mistake: it starts a new task and does not answer the question.
#
# A state is an enum, not a string. Compare with `TaskState.TASK_STATE_COMPLETED`, not with `"completed"`. The 0.3 names are lower case, and the 1.x names are upper case with the `TASK_STATE_` prefix.

# %% [markdown]
# ## Try it
# Without a server and without a model, write `needs_user(task)`. It returns `True` when the task is `INPUT_REQUIRED` or `AUTH_REQUIRED`, and `False` otherwise. Test it on a `WORKING` task and on an `INPUT_REQUIRED` task built in the cell.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
from a2a.types import Task, TaskStatus
def needs_user(task) -> bool:
    return task.status.state in (TaskState.TASK_STATE_INPUT_REQUIRED, TaskState.TASK_STATE_AUTH_REQUIRED)
print(needs_user(Task(status=TaskStatus(state=TaskState.TASK_STATE_WORKING))))
print(needs_user(Task(status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED))))

# %% [markdown]
# ## Key terms
# - **TaskState** — the enum of a task's states: eight named values plus `UNSPECIFIED`, all with the `TASK_STATE_` prefix.
# - **terminal state** — a state that ends a task: `COMPLETED`, `FAILED`, `CANCELED` or `REJECTED`.
# - **interrupted state** — a state that pauses a task until the client answers: `INPUT_REQUIRED` or `AUTH_REQUIRED`.
# - **contextId** — the id that groups the turns of one conversation.
# - **taskId** — the id of one task. A message with a known `taskId` continues that task.
# - **StreamResponse** — one streamed event: a task, a message, a status update or an artifact update.
# - **CancelTask** — the operation that moves a non-terminal task to `CANCELED`.
# - **google.rpc.Status** — the error envelope; its `ErrorInfo` detail carries a machine-readable `reason`.
# - **A2A-Extensions** — the HTTP header that asks for, or confirms, the extensions used in a call.

# %% [markdown]
# Stop the agent, close both clients and tell the recorder the lesson is done.

# %%
import llm_replay
agent.stop()
await client.close()
await streamer.close()
llm_replay.stop()        # saves the recording if a model ran; a no-op otherwise
print("lesson 09 done: one task through its states, one stream, one cancel")
