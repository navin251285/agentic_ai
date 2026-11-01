# %% [markdown]
# # 01 · Why agentic AI, and what an agent is (and is not)
# Level L1 · Part 1 · core · ~15 min · builds on none

# %% [markdown]
# ## Goal
# Tell an agent from a chatbot and from a fixed workflow, by drawing each one as a graph and running it on the same customer
# message. Then say when not to build an agent.

# %% [markdown]
# ## Why it matters
# A support desk with no model at all needs a rule for every question someone thought of. The next customer writes the question
# differently, and the rule misses. Look at the graph below: a single rule catches one phrasing and drops the rest.

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: llm_setup.py, graph_view.py and tut_env.py live there

import re

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from graph_view import show_graph  # course helper: draws a compiled graph as a picture

ORDERS = {
    "1042": {"status": "out for delivery", "carrier": "Parcelco"},
    "1077": {"status": "delivered", "carrier": "Parcelco"},
    "1093": {"status": "lost in transit", "carrier": "Rapid Post"},
}
customers = [
    "Where is my order 1042?",
    "My parcel 1093 never came. Can I get my money back?",
    "Is order 1077 the one I sent back last week?",
    "wher is my ordr 1042",
]

# %% [markdown]
# **A graph in one sentence.** A LangGraph graph is nodes (plain Python functions) joined by edges, and every node reads and
# returns a state dict, here `{"message": ..., "reply": ...}`. The desk below is a graph with one node, `rules`, and no model.

# %%
class Desk(TypedDict):
    message: str
    reply: str


def rules(state: Desk) -> dict:
    """A desk with no model: one hand-written rule per question someone thought of."""
    text, found = state["message"].lower(), re.search(r"\b(\d{4})\b", state["message"])
    if found and "where is my order" in text:
        order = ORDERS.get(found.group(1))
        return {"reply": f"Order {found.group(1)} is {order['status']}." if order else "I can't find that order."}
    return {"reply": "Sorry, I didn't understand. Try: 'where is my order 1042?'"}


rules_app = StateGraph(Desk).add_node("rules", rules).add_edge(START, "rules").add_edge("rules", END).compile()
show_graph(rules_app)  # one node, no model: every new question needs another rule

# %% [markdown]
# Now run the desk on the four customer messages. It answers only the ones that match its one rule.

# %%
handled = 0
for message in customers:
    reply = rules_app.invoke({"message": message, "reply": ""})["reply"]
    handled += not reply.startswith("Sorry")
    print(f"customer: {message}\n  desk:     {reply}")
print(f"\nHandled {handled} of {len(customers)} messages with one rule.")

# %% [markdown]
# Each missed phrasing is a lost customer. Each new question is another branch. Without a model, the code grows with every
# question people can ask.

# %% [markdown]
# ## The idea
# An **agent** is three parts in a loop: a **model** that reads the request and decides the next step, **tools** that your code
# runs (look up an order, open a ticket, issue a refund), and **instructions** that give its role and limits. The model asks for
# a tool, your code runs it, and the result goes back. The model never runs anything itself. The loop ends when the model answers.
#
# Analogy: a support agent with a phone, a shelf of procedures and the manager's rules. They decide the next lookup from what they
# find. A workflow is the same person following a fixed checklist.

# %% [markdown]
# ## Picture
# The three graphs below differ in one thing: where the decision sits. Amber nodes call the model. Blue nodes are code.
# `show_mermaid` is a course helper that draws a diagram written in Mermaid text.

# %%
from graph_view import show_mermaid

show_mermaid("""
flowchart LR
  subgraph C["Chatbot: one reply, no tools"]
    c1["model<br/>writes words only"] --> c2(["reply"])
  end
  subgraph W["Workflow: fixed steps"]
    w1["lookup<br/>code"] --> w2["summarise<br/>model"] --> w3(["reply"])
  end
  subgraph A["Agent: the model picks each step"]
    a1["model<br/>asks for a tool or answers"] -->|asks| a2["tools<br/>code runs the lookup"]
    a2 --> a1
    a1 -->|answers| a3(["reply"])
  end
  classDef model fill:#fde68a,stroke:#b45309
  classDef code fill:#e0f2fe,stroke:#0369a1
  class c1,w2,a1 model
  class w1,a2 code
""")

# %% [markdown]
# ## Degrees of autonomy
# Autonomy is how much of the decision the model makes, instead of your code.
#
# | Level | What the model decides | Use it when |
# |---|---|---|
# | 0. One call | The words of one reply | drafting, summarising, classifying |
# | 1. Workflow | Nothing about the path; code chains the steps | the steps are known in advance |
# | 2. Agent | Which tool to call next, and when to stop | the path depends on what it finds |
#
# Two levels sit between these rows and are taught later: a **router**, where the model picks one of a few fixed branches
# (lesson 11), and **multi-agent** systems, where one agent hands work to another (lesson 24).
#
# Start at the lowest level that works. Each step the model decides adds cost, latency and variance.

# %% [markdown]
# ## Step by step
# **Step 1 · setup (one model for the lesson).** The model comes from `llm_setup.get_llm()`, the course's model setup. Its key is
# read from `.env`, and `llm_replay` (a course helper that saves model answers the first time they are asked) replays them later,
# so later runs need no key.

# %% tags=["needs-llm"]
import llm_replay  # course helper: records and replays model calls (not part of LangGraph)
llm_replay.start("01_why-agentic-ai")

from langchain.agents import create_agent
from langchain_core.tools import tool
from llm_setup import get_llm  # course helper: the course model setup

llm = get_llm()
QUESTION = "My parcel for order 1093 never came. Can you check it and tell me what to do?"

# %% [markdown]
# **Step 2 · the chatbot (1 model call).** One node, no tools. The model can only write words, so any action it describes never
# happens. Read the reply for claims about actions: they are invented.

# %% tags=["needs-llm"]
chat = StateGraph(Desk)
chat.add_node("chat", lambda s: {"reply": llm.invoke(
    "You are the support desk for Brightside Outfitters, an outdoor-gear shop. Answer in two sentences.\n\n"
    f"Customer: {s['message']}").text})
chat_app = chat.add_edge(START, "chat").add_edge("chat", END).compile()
show_graph(chat_app, model_nodes=("chat",))
print("chatbot:", chat_app.invoke({"message": QUESTION, "reply": ""})["reply"])

# %% [markdown]
# **Step 3 · the agent (2 model calls: the request, then the answer).** `create_agent` builds the loop from the agent graph in the
# Picture section: the model, the tools node, and the way back. The tool reads the order rows; the model writes its answer from
# the result. The system prompt says a refund is decided by a person, because the agent has no refund tool.

# %% tags=["needs-llm"]
@tool
def get_order(order_id: str) -> str:
    """Look up one Brightside order by its 4-digit number and return its status."""
    order = ORDERS.get(order_id)
    return f"Order {order_id}: {order['status']}, carrier {order['carrier']}." if order else f"No order {order_id}."


agent = create_agent(model=llm, tools=[get_order],
                     system_prompt="You are the Brightside Outfitters support desk. Use tools for order facts. "
                                   "You cannot issue refunds: say that a person will review the case.")
show_graph(agent, model_nodes=("model",))
result = agent.invoke({"messages": [{"role": "user", "content": QUESTION}]}, config={"recursion_limit": 6})
for m in result["messages"][1:]:
    for call in getattr(m, "tool_calls", []) or []:
        print("the model asks for:", call["name"], call["args"])
    if m.type == "tool":
        print("the tool returns:", m.content)
print("agent:", result["messages"][-1].text)
llm_replay.stop()  # the last model call of this lesson

# %% [markdown]
# ## At work
# - Teams start with the simplest system that works. Anthropic's "Building effective agents" makes the same point: use workflows
#   for known steps, and add an agent loop only where the path cannot be known in advance → lesson 15 (patterns).
# - An agent loop has no natural end. Production loops carry step and spend caps, because a looping agent keeps billing → lesson 05.
# - Interviewers open with this distinction: "workflow or agent, and what are the parts of an agent?"

# %% [markdown]
# ## What just happened
# - The rules desk handled 1 of 4 messages ("Handled 1 of 4 messages with one rule."). Every other phrasing got the "Sorry" reply.
# - The chatbot's reply says it "initiated a trace with the carrier" and offers "a replacement or refund". It had no tool, so no
#   trace was opened and no refund or replacement was arranged. Those words are invented.
# - The agent asked for `get_order` with `1093`. The tool returned "lost in transit, carrier Rapid Post", and the answer was built
#   from that result.
# - The agent did not promise a refund: it says "a member of our staff will review your case".

# %% [markdown]
# ## Common mistakes
# 1. **"More autonomy is always better."** Many production systems are workflows with one model step, and that is the right answer.
# 2. **"An agent is just a bigger chatbot."** The difference is tools and a loop. Without tools, the model can only describe an action.
# 3. **"A framework makes it an agent."** The loop fits in about twenty lines of plain Python (lesson 05). The framework is a convenience.
# 4. **"`create_agent` works without a model."** It does not. The model is the first required argument. The cell below shows the
#    real error (name and first line only), and the fix follows it.

# %% tags=["raises-exception"]
from langchain.agents import create_agent

try:
    create_agent(tools=[], system_prompt="You are the support desk.")  # the model argument is missing
except TypeError as err:
    print(type(err).__name__, "|", str(err).splitlines()[0])

# %% [markdown]
# **Fix:** pass the model first, as Step 3 does: `create_agent(model=llm, tools=[get_order], system_prompt=...)`.

# %% [markdown]
# ## Try it
# A shop FAQ bot answers from a fixed list of 30 questions and never looks anything up. Is it a chatbot, a workflow or an agent?
# Write the answer as a string in `classify_faq_bot`, with a one-line reason. No model call is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def classify_faq_bot() -> str:
    return "workflow or router: the answers are fixed and no tool or loop is needed, so it is not an agent"


print(classify_faq_bot())

# %% [markdown]
# ## Key terms
# - **Agent** — a model, tools and instructions in a loop: the model picks the next step, and your code runs the tool it asks for.
# - **Chatbot** — a model call with no tools and no loop; it answers from its words alone.
# - **Workflow** — a fixed sequence of steps in code; the model may fill in some of them.
# - **Tool** — a function your code runs when the model asks for it.
# - **Graph** — nodes joined by edges, run over a shared state.
# - **Node** — one function in a graph, such as `rules` or `chat`.
# - **Edge** — a link that says which node runs next.
# - **State** — the dict every node reads and returns, such as `message` and `reply`.

# %% [markdown]
# ## Recap
# - A rule-based desk needs a branch for every phrasing; an agent lets the model pick the next step from the results.
# - An agent is a model, tools and instructions in a loop. The model asks; your code runs.
# - Use a workflow when the steps are known. Put an approval step on anything that moves money.
#
# **Interview:** "Workflow or agent, and what are the components of an agent?" Strong answer: "A workflow fixes the steps in code;
# an agent lets the model choose them in a loop with tools and instructions. I start with a workflow and add the loop only where the
# path depends on what the model finds."
