# %% [markdown]
# # 08 · Checkpoint: the order assistant, v1
# Level L2 · Part 2 · core · ~40 min · builds on 05, 06, 07

# %% [markdown]
# ## Goal
# Ship the first agent you would let near customers: a graph with tools, a step cap, a spend cap, a write gate, a saved conversation
# and a golden-set score. Every piece is one you built in lessons 05 to 07. This lesson puts them together and checks them.

# %% [markdown]
# ## Why it matters
# Each lesson so far taught one part. A real agent needs all of them at once, and the parts interact: the cap must stop the loop the
# gate blocked, and the saved conversation must survive a restart. A checkpoint runs the parts together, so you find the interaction
# before a customer does.

# %% [markdown]
# ## The idea
# The v1 assistant is the graph from lesson 07 with three additions: a **step cap** (`recursion_limit`), a **checkpointer** that
# saves each step under a thread id, and a **score** from the golden set. The loop, the gate and the tools are unchanged.

# %% [markdown]
# ## Picture
# The course helper `graph_view.py` (`show_mermaid`) draws a diagram from text. Read the diagram as the run order: the model reads the
# thread, a tool or the gate runs, and the loop returns to the model until it answers.

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: llm_setup.py, graph_view.py and tut_env.py live there

from graph_view import show_mermaid

show_mermaid("""
flowchart LR
  U(["customer message"]) --> M["model<br/>reads the thread"]
  M -->|reads an order| T["tools<br/>lookup_order"]
  M -->|asks for a refund| G{"approved"}
  G -->|no| R["refuse<br/>the model tells the customer"]
  G -->|yes| W["tools<br/>issue_refund"]
  T --> M
  R --> M
  W --> M
  M -->|answer| A(["reply"])
  C[("checkpointer<br/>one thread id")] -.- M
  classDef model fill:#fde68a,stroke:#b45309
  classDef code fill:#e0f2fe,stroke:#0369a1
  class M model
  class T,W,R,G,C code
""")

# %% [markdown]
# ## Requirements
# The v1 assistant must:
#
# 1. answer order questions by calling `lookup_order`, and never invent a status;
# 2. refuse any refund unless a person approved it, and say so to the customer;
# 3. stop after six graph steps (`recursion_limit`; a model turn and a tool run are each one step), and stop when the spend passes its cap;
# 4. keep the conversation under one thread id, so the saved state can be read back and resumed in the same process;
# 5. score at least the baseline on the golden set (12 of 30, measured in lesson 07), with no unapproved write.

# %% [markdown]
# ## Build it
# **Step 1 · the parts (no call).** The tools, the gate and the golden set come from lessons 06 and 07. The data file is the same.
# This lesson rebuilds them in one place, so the checkpoint runs on its own. `ORDERS` is the world the tools read; `REFUNDS` is the
# list of money that has really moved.

# %%
import json
from pathlib import Path
from typing import Annotated, Literal
import operator

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

DATA = json.loads((Path("../../../data") / "support_eval.json").read_text())
ORDERS = DATA["world"]["orders"]
REFUNDS: list = []  # what the money has really done


class OrderQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(description="The order number the customer wrote: four digits, such as 1093.", pattern=r"^\d{4}$")


@tool(args_schema=OrderQuery)
def lookup_order(order_id: str) -> dict:
    """Look up one customer order: its status and days late. Use it when the customer gives an order number."""
    return ORDERS.get(order_id, {"error": f"no order {order_id}", "next_step": "Ask for the number in the confirmation email."})


@tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund money to the customer's card. Only a person may approve this; the agent must not call it."""
    REFUNDS.append((order_id, amount_usd))
    return f"refunded {amount_usd:.2f} for order {order_id}"


WRITES = {"issue_refund"}
print("tools:", lookup_order.name, "and", issue_refund.name, "· writes that need approval:", sorted(WRITES))

# %% [markdown]
# The state has two fields a person or the code sets, not the model: `approved` and the message list. The gate reads `approved`
# before any write runs. `refuse` writes the refusal the model reads, so it can tell the customer.

# %%
class DeskState(TypedDict):
    messages: Annotated[list, operator.add]
    approved: bool  # set by a person, never by the model


def route_gate(state: DeskState) -> Literal["tools", "refuse", "__end__"]:
    from langgraph.graph import END
    last = state["messages"][-1]
    if not last.tool_calls:
        return END
    if any(c["name"] in WRITES and not state["approved"] for c in last.tool_calls):
        return "refuse"
    return "tools"


def refuse(state: DeskState) -> dict:
    last = state["messages"][-1]
    return {"messages": [ToolMessage(content="refused: a refund needs a person's approval. Tell the customer it is being reviewed.",
                                     tool_call_id=c["id"]) for c in last.tool_calls]}
print("gate, with a plain answer and no tool call:", route_gate({"messages": [AIMessage(content="ok")], "approved": False}))

# %% [markdown]
# **Step 2 · the scripted score (no model call).** The golden set is graded with a scripted stand-in, as in lesson 07. The stand-in is
# **not this assistant**: it looks up any four-digit order it finds and refunds nothing. Its score checks the golden set and the grader.
# `MIN_SCORE = 12` is the baseline lesson 07 measured, written as its own constant so the check compares two different numbers.

# %%
import re
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

TASKS = DATA["tasks"]


def grade(task: dict, end: dict, called: list[str]) -> bool:
    return (not any(t in called for t in task.get("forbidden_tools", []))
            and all(t in called for t in task.get("must_call", []))
            and end == task["expected_end"])


def scripted_agent(request: str):
    return {"refunds": {}, "tickets": []}, (["lookup_order"] if re.search(r"\b\d{4}\b", request) else [])


def score_case(inp: dict) -> dict:
    end, called = scripted_agent(inp["task"]["request"])
    return {"passed": [grade(inp["task"], end, called)]}


score_graph = StateGraph(TypedDict("S", {"passed": Annotated[list, operator.add], "total": int}))
score_graph.add_node("case", score_case)
score_graph.add_conditional_edges(START, lambda s: [Send("case", {"task": t}) for t in TASKS], ["case"])
score_graph.add_edge("case", END)
ran = score_graph.compile().invoke({"passed": [], "total": 0})
SCRIPTED_SCORE = sum(ran["passed"])  # the stand-in's score, not the assistant's
MIN_SCORE = 12  # the baseline lesson 07 measured (12 of 30); the checkpoint must not fall below it
print(f"scripted score: {SCRIPTED_SCORE}/{len(TASKS)} tasks pass · the minimum is {MIN_SCORE}")

# %% [markdown]
# **Step 3 · the agent with its caps and its memory (one question = 2 model calls).** Two course helpers appear here.
# `llm_replay` records the model's answers the first time and replays them later, so the lesson runs offline with no key.
# `get_llm` is the course's model setup (Gemini on Vertex AI). The first call picks `lookup_order`; the second writes the answer
# from the tool's result. The spend cap is checked after each reply, using the token counts that reply carries.

# %% tags=["needs-llm"]
import llm_replay  # course helper: records model answers once and replays them offline
llm_replay.start("08_checkpoint-order-assistant")

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode
from llm_setup import get_llm  # course helper: the shared model setup (Gemini on Vertex AI)
from graph_view import show_graph  # course helper: draws the compiled graph

llm = get_llm()
PRICE_IN, PRICE_OUT, SPEND_CAP_USD = 0.25, 1.50, 0.01  # US$ per million tokens; the cap is US$ per question
model = llm.bind_tools([lookup_order, issue_refund])
STOP_REPLY = "I can't finish this one now. A person will follow up."


def spend_so_far(spent: float, usage: dict) -> float:
    """Add the cost of one model reply (its token counts) to the running total."""
    return spent + (usage["input_tokens"] * PRICE_IN + usage["output_tokens"] * PRICE_OUT) / 1_000_000


class V1State(DeskState):
    spent: float

# %% [markdown]
# The model node asks the model once per turn and checks the spend cap after the reply. `route_v1` ends the run when the spend is over
# the cap; otherwise it sends the message through the gate from Step 1.

# %% tags=["needs-llm"]
def call_model(state: V1State) -> dict:
    reply = model.invoke(state["messages"])
    spent = spend_so_far(state["spent"], reply.usage_metadata)
    if spent > SPEND_CAP_USD:  # the spend cap: the reply is kept, but no tool runs after it
        return {"messages": [reply, AIMessage(content=STOP_REPLY)], "spent": spent}
    return {"messages": [reply], "spent": spent}


def route_v1(state: V1State):
    if state["spent"] > SPEND_CAP_USD:
        return END
    return route_gate(state)


g = StateGraph(V1State)
g.add_node("model", call_model)
g.add_node("tools", ToolNode([lookup_order, issue_refund]))
g.add_node("refuse", refuse)
g.add_edge(START, "model")
g.add_conditional_edges("model", route_v1, {"tools": "tools", "refuse": "refuse", END: END})
g.add_edge("tools", "model").add_edge("refuse", "model")
v1 = g.compile(checkpointer=InMemorySaver())  # the checkpointer: saves every step in this process's memory
show_graph(v1, model_nodes=("model",))

# %% [markdown]
# **Run it.** One question, one thread id and a step cap of six. The first model call picks `lookup_order`; the second writes the answer.

# %% tags=["needs-llm"]
CFG = {"configurable": {"thread_id": "customer-1003"}}  # one thread id = one saved conversation
ask = HumanMessage(content="Order 1003 never arrived. What is its status?")
out = v1.invoke({"messages": [ask], "approved": False, "spent": 0.0},
                config={**CFG, "recursion_limit": 6})  # the step cap: at most 6 graph steps
print("answer:", out["messages"][-1].text)
print("spent in US$:", round(out["spent"], 7), "· money moved:", REFUNDS)
saved = list(v1.get_state_history(CFG))  # every saved checkpoint of this thread, newest first
print("saved checkpoints for this thread:", len(saved), "· model calls in this lesson so far:", llm_replay.calls())

# %% [markdown]
# The saved step count is the number of checkpoints: LangGraph saves the input, one checkpoint before the first step and one after
# each step, so this run (model, tools, model: three steps) leaves five.

# %% [markdown]
# **Step 4 · the caps and the gate, with no model call.** These cells test the caps and the gate with numbers the run already produced,
# and with a hand-built request for the refund. They cost nothing to repeat, and nothing here calls the model.

# %%
# The spend cap, on a copy: the same test call_model makes, with a cap set below what the run spent. SPEND_CAP_USD is unchanged.
COPY_CAP = out["spent"] / 2  # a copy of the cap, set low for this test
copy_stops = out["spent"] > COPY_CAP
print(f"the run spent US${out['spent']:.7f}; the copy's cap is US${COPY_CAP:.7f} · over the copy's cap: {copy_stops}")
if copy_stops:
    print("the customer gets this instead of the answer:", STOP_REPLY)

# %% [markdown]
# **The step cap on a toy loop.** A node that always asks to run again would run for ever. `recursion_limit` stops it with an error,
# and the cell prints only the error's name and first line.

# %%
# The step cap, on a toy loop (no model call): a node that always asks to run again stops at recursion_limit.
def spin(state: dict) -> dict:
    return {"n": state["n"] + 1}


loop = StateGraph(TypedDict("Loop", {"n": int}))
loop.add_node("spin", spin)
loop.add_edge(START, "spin").add_edge("spin", "spin")  # it never reaches END
step_cap_hit = False
try:
    loop.compile().invoke({"n": 0}, config={"recursion_limit": 6})
except Exception as err:  # the step cap stops the run with an error
    step_cap_hit = True
    print(type(err).__name__, "-", str(err).splitlines()[0])

# %% [markdown]
# **The write gate with a hand-built refund.** The request below is written by hand as a stand-in for a model reply, so it is not
# model output. The gate must refuse it, and the refund list must stay empty.

# %%
# The write gate, with a hand-built refund request (a stand-in for a model reply, not model output): the gate must refuse it.
asked = AIMessage(content="", tool_calls=[{"name": "issue_refund", "args": {"order_id": "1003", "amount_usd": 89.5}, "id": "call_demo_1"}])
forced = {"messages": [asked], "approved": False, "spent": 0.0}
print("route:", route_gate(forced))
print("refusal the model reads:", refuse(forced)["messages"][0].content)
print("money moved:", REFUNDS)  # still empty: the refund never ran

# %% [markdown]
# **Step 5 · the saved thread, in the same process (no model call).** `InMemorySaver` keeps the checkpoints in this Python process's
# memory, so a restart (or a new kernel) loses them. For a restart you use a file-backed or database saver instead, such as
# `SqliteSaver` from `langgraph-checkpoint-sqlite` (in the course requirements). The code shape stays the same; only the saver changes.
# Here you resume by thread id: `invoke(None)` sends no new message, so the thread's saved state is the input.

# %%
resumed = v1.invoke(None, config=CFG)  # resumes the thread; the thread has already ended, so no step runs
print("saved messages:", len(v1.get_state(CFG).values["messages"]), "· same answer:",
      resumed["messages"][-1].text == out["messages"][-1].text)
print("checkpoints after resume:", len(list(v1.get_state_history(CFG))), "· money moved:", REFUNDS)

# %% [markdown]
# ## Reference solution
# The cell below is the solution's checks. It reads what the cells above saved: the answer, the money moved, the checkpoints, the
# step and spend caps, and the scripted score against `MIN_SCORE = 12`. Each PASS names one requirement. If one fails, the requirement
# it names is the place to look. The hidden cell also ends the recording: `llm_replay.stop()` is the last line of the lesson.

# %% tags=["solution"]
ran_model = "out" in globals()  # False if the model cell did not run (no key and no recording)
checks = {
    "1 · answers from the tool, not from memory": ran_model and any(getattr(m, "type", "") == "tool" for m in out["messages"]),
    "2 · no refund ran without approval, and the gate refuses one": REFUNDS == [] and route_gate(forced) == "refuse",
    "3 · the step cap and the spend cap each stop a run": step_cap_hit and copy_stops,
    "4 · the thread is saved and resumes by its id": ran_model and len(saved) > 0 and resumed["messages"][-1].text == out["messages"][-1].text,
    "5 · the scripted score is at least MIN_SCORE (12)": SCRIPTED_SCORE >= MIN_SCORE,
}
for name, ok in checks.items():
    print("PASS" if ok else "FAIL", "-", name)
if not ran_model:
    print("note: the model cell did not run, so checks 1 and 4 cannot pass here; run it with the recording to see them.")
llm_replay.stop()  # the last model-related line of this lesson

# %% [markdown]
# ## What just happened
# - The run made 2 model calls (the count printed above) and spent about US$0.00023, under the US$0.01 cap, so the money moved list stayed empty.
# - The copy's cap of half the spend stopped the answer, and the toy loop hit the step cap of 6 with an error.
# - The gate refused a hand-built refund, and no money moved.
# - The scripted score is 12 of 30, at the MIN_SCORE of 12; the thread holds 5 saved checkpoints and resumes with the same answer.

# %% [markdown]
# ## Try it
# Find the smallest spend cap at which the real run stays under the cap. Test 0.00001, 0.0001, 0.001 and 0.01 with a comparison
# against `out["spent"]`, and say which is the first to pass. Raise the cap one step at a time and watch the check change.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
for cap in (0.00001, 0.0001, 0.001, 0.01):
    print(f"cap US${cap:<8} run stays under it: {out['spent'] <= cap}")

# %% [markdown]
# ## Common mistakes
# 1. **Testing the parts and not the whole.** Each part can pass while the combination fails. The checkpoint runs them together.
# 2. **A cap checked only after the reply.** The reply that crosses the cap is already paid for. The cap above keeps that reply and
#    runs no tool after it.
# 3. **Calling the graph with no thread id.** A checkpointer needs a `thread_id` in the config. Without it, the call stops with an error:

# %% tags=["raises-exception"]
try:
    v1.invoke({"messages": [ask], "approved": False, "spent": 0.0})  # no config: no thread id
except Exception as err:
    print(type(err).__name__, "-", str(err).splitlines()[0])

# %% [markdown]
# The fix is the config in the call: `config={"configurable": {"thread_id": "customer-1003"}}`, as in the run above.

# %% [markdown]
# ## Key terms
# - **checkpointer** — the saver that writes the graph's state after each step, under a thread id.
# - **thread id** — the name of one saved conversation; the same id resumes it.
# - **recursion_limit** — the step cap: the most graph steps one run may take before LangGraph stops it with an error.
# - **golden set** — a fixed list of tasks with expected outcomes, rerun on every change.
# - **spend cap** — the most US dollars one question may cost, checked after each model reply.

# %% [markdown]
# ## At work
# - A checkpoint is the release check: a short list of requirements, run on every build. Teams keep it next to the code →
#   lesson 32 (evals in CI).
# - The saved thread is what makes a restart safe; the next lesson uses it for memory → lesson 09.

# %% [markdown]
# ## Recap
# - The v1 assistant is a graph with tools, a step cap, a spend cap, a write gate, a thread and a score.
# - Each requirement has a check that runs without a person.
# - A failed check names the part to fix.
#
# **Interview:** "What must an agent have before it talks to a customer?" Strong answer: "Tools that return facts, caps on steps and
# spend, a gate in front of writes, a saved thread, and a score on a golden set that I can rerun on every change."
