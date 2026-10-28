# %% [markdown]
# # 27 · Observability and cost: traces, loop metrics and per-run budgets
# Level L6 · Part 4 · core · ~25 min · builds on 26b
#
# ## Goal
# Trace one loop run as a span tree: one child span per iteration, each with the attribute `loop.iteration`. Then compute cost per success from the spans, and keep customer text out of every span.
#
# ## Why it matters
# Lesson 26b stops a runaway fleet. It cannot say which run burned the money, or why. Without traces and cost numbers, this is what the team sees:
#
# | Without this | What goes wrong |
# |---|---|
# | No span per iteration | A failed run shows one line. Nobody knows which call spent the money |
# | Cost only on the invoice | The bill arrives at month end. Failed runs are paid for and never counted as failures |
# | Customer text in logs | The raw message from a customer is copied into every log and every dashboard |
#
# With a span per iteration and a cost on every span, one failed run shows its calls, its tokens and its stop reason. You do not need this for one run you watch on your screen.

# %% [markdown]
# ## The idea
# **A trace is a tree of spans. The root span is one loop run; each iteration is a child span with `loop.iteration`; each model call and each tool call is a span under its iteration. Every model reply carries token counts, so cost is a sum over spans. Cost per success is the whole spend, failed runs included, divided by the runs that succeeded. Spans keep numbers and names, never the customer's words.**
#
# Analogy: a delivery company's route log. Each van has one trip (the root), each stop is a line (an iteration), and each stop lists the fuel it used. The fuel bill divided by the parcels delivered is the cost per parcel, and the trips that came back with the parcel still on board count in the fuel bill too.

# %% [markdown]
# ## Picture
# One run is one tree. The reply cap is checked on the iteration span before its tools run, so a capped run has no tool spans after the cap.
#
# ```mermaid
# flowchart TD
#   R["invoke_agent support-desk<br/>loop.run_id, loop.stop_reason, loop.cost_usd"] --> I1["iteration: loop.iteration = 1"]
#   R --> I2["iteration: loop.iteration = 2"]
#   I1 --> C1["chat: gen_ai.usage.input_tokens / output_tokens"]
#   I1 --> T1["execute_tool issue_refund"]
#   I2 --> C2["chat: gen_ai.usage.*"]
# ```

# %% [markdown]
# ## Step by step
# 1. Start the recording layer. It makes no model call.
# 2. Set up the two tools and the price of one model call (Step 1 below). The orders are the two cases of lesson 26b.
# 3. Set up the tracer: one root span per run, one span per iteration, one span per model call and per tool call (Step 2).
# 4. Run two loops with the real model (Step 3). One succeeds. The other has a cap of one reply, so its refund tool never runs.
# 5. Print the span tree (Step 4), then check the attributes for customer text (Step 5).
# 6. Compute cost per success (Step 6).

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("27_observability-and-cost")  # records the model calls once, replays them later

# %% [markdown]
# ### Step 1: the tools and the price (setup from earlier lessons)
# This is the setup from lessons 03 to 05 and 26b, shortened: two invented orders and two tools. Nothing here calls the model. The price is the list price of the model the course uses by default, read in lesson 02 on 2026-10-27.

# %%
# setup from earlier lessons (03 to 05, 26b): two orders and two tools, shortened
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

ORDERS = {"BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0},  # generated: lesson 26b's cases
          "BS-1063": {"customer": "C-30", "item": "Water bottle", "paid_usd": 45.0}}
REFUNDS = []  # state outside the model: a refund is written here

@tool
def get_order(order_id: str) -> str:
    """Look up one order: item and amount paid."""
    return str(ORDERS[order_id])

@tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS = {t.name: t for t in (get_order, issue_refund)}
SYSTEM = ("You are the support desk for Brightside Outfitters. Look up the order, then refund what was paid "
          "for a damaged item. Never refund more than was paid. Answer in one sentence when done.")
PRICE = {"input": 0.10, "output": 0.40}  # USD per 1M tokens: gemini-2.5-flash-lite list price, read 2026-10-27
def call_cost(input_tokens, output_tokens):
    return (input_tokens * PRICE["input"] + output_tokens * PRICE["output"]) / 1_000_000

# %% [markdown]
# ### Step 2: the tracer
# A **span** is one timed step with a name and attributes (key-value facts). OpenTelemetry is the open standard for writing spans. A **span processor** receives each span when it ends and passes it to an **exporter**, which ships it somewhere. Here the exporter is a list in memory, so the lesson runs offline. Lesson 28 ships the same spans over **OTLP**, the open wire protocol that trace viewers read. The span names follow the GenAI conventions of OpenTelemetry (https://github.com/open-telemetry/semantic-conventions-genai), which are still in Development: the names may change, so pin the library and record the schema version your dashboards read.

# %%
# a provider makes tracers; the processor hands each span to the exporter when the span ends
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

EXPORTER = InMemorySpanExporter()  # the spans stay in memory: no server, no network
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
tracer = provider.get_tracer("support-desk-loop")
print("tracer ready; finished spans so far:", len(EXPORTER.get_finished_spans()))

# %% [markdown]
# ### Step 3: one model step, one span
# The model is the only gated part. One reply is one `chat` span with the token counts on it. The span carries counts, never the message text.

# %% tags=["needs-llm"]
from llm_setup import get_llm, DEFAULT_MODELS

llm = get_llm(model=DEFAULT_MODELS["gemini"]).bind_tools(list(TOOLS.values()))

def model_step(messages):
    with tracer.start_as_current_span("chat") as chat:
        reply = llm.invoke(messages)
        usage = reply.usage_metadata
        chat.set_attribute("gen_ai.operation.name", "chat")
        chat.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
        chat.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])
    return reply, call_cost(usage["input_tokens"], usage["output_tokens"])

# %% [markdown]
# ### Step 3 (continued): the tool span and the loop
# Each tool call gets its own `execute_tool` span. The span keeps the tool's name, never its arguments.

# %%
def run_tool(call):
    with tracer.start_as_current_span(f"execute_tool {call['name']}") as ts:
        ts.set_attribute("gen_ai.operation.name", "execute_tool")
        ts.set_attribute("gen_ai.tool.name", call["name"])
        return str(TOOLS[call["name"]].invoke(call["args"]))

# %% [markdown]
# Each reply is one iteration span. The reply cap is checked after the reply and before its tools run, as in lesson 05.

# %% tags=["needs-llm"]
def run_traced(run_id, text, max_turns):
    """One loop run. Returns (stop reason, cost in USD)."""
    messages, cost = [SystemMessage(content=SYSTEM), HumanMessage(content=text)], 0.0
    with tracer.start_as_current_span("invoke_agent support-desk") as root:
        root.set_attribute("loop.run_id", run_id)
        for i in range(1, max_turns + 1):  # the reply cap is also the iteration ceiling
            with tracer.start_as_current_span("iteration") as it:
                it.set_attribute("loop.iteration", i)
                reply, step_cost = model_step(messages)
                cost += step_cost
                messages.append(reply)
                stop = "answered" if not reply.tool_calls else "turn_cap" if i >= max_turns else None
                if stop:
                    it.set_attribute("loop.stop_reason", stop)
                    break
                for call in reply.tool_calls:
                    messages.append(ToolMessage(content=run_tool(call), tool_call_id=call["id"]))
        else:
            stop = "iteration_ceiling"  # not reached with these caps; keeps the stop reason from being None
        root.set_attribute("loop.stop_reason", stop)
        root.set_attribute("loop.cost_usd", round(cost, 6))
    return stop, cost

# %% [markdown]
# Run A has the full cap. Run B may use one reply only, so the cap stops it before its refund. Two runs make three model calls in total.

# %% tags=["needs-llm"]
RUNS = {}
RUNS["R-A"] = run_traced("R-A", "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. "
                         "Order BS-1042 paid 120 USD. Refund the damage.", max_turns=6)
RUNS["R-B"] = run_traced("R-B", "Customer C-30 says the water bottle from order BS-1063 leaks. "
                         "Order BS-1063 paid 45 USD. Refund the damage.", max_turns=1)
for rid, (stop, cost) in RUNS.items(): print(rid, "| stop:", stop, "| cost USD:", f"{cost:.6f}")
print("refunds written:", REFUNDS)

# %% [markdown]
# **No key, or the model cells skipped?** The spans come from the model's replies, so there is nothing to trace. The cells below say so and do nothing. No output is made up.

# %%
if not RUNS: print("no model runs in this session: the trace cells need the recording or a key (needs-llm)")

# %% [markdown]
# ### Step 4: read the span tree
# Each run prints as a tree. The root has the stop reason and the cost. Each iteration has its number, and a stop reason on the iteration that stopped. The chat spans have the token counts that the cost comes from.

# %%
def print_tree(run_id):  # the spans of this run only; each child is printed under its parent
    spans = EXPORTER.get_finished_spans()
    def walk(s, depth):
        print("  " * depth + s.name, dict(s.attributes))
        kids = [c for c in spans if c.parent and c.parent.span_id == s.context.span_id]
        for c in sorted(kids, key=lambda c: c.start_time):
            walk(c, depth + 1)
    walk(next(s for s in spans if s.attributes.get("loop.run_id") == run_id), 0)

if RUNS:
    print_tree("R-A")
    print()
    print_tree("R-B")

# %% [markdown]
# ### Step 5: keep customer text out of spans
# Spans are copied to dashboards, vendors and support tickets. The rule is the allow-list: a span carries only the keys below. The value check runs over every span of every run, but it is only a backstop for a name typed into an allowed key.

# %%
ALLOWED = {"loop.run_id", "loop.iteration", "loop.stop_reason", "loop.cost_usd",
           "gen_ai.operation.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.tool.name"}

def pii_problems(spans):  # the allow-list is the rule; the value check is only a backstop
    return [(s.name, k, "key not allowed" if k not in ALLOWED else "customer text")
            for s in spans for k, v in s.attributes.items()
            if k not in ALLOWED or "Customer" in str(v) or "@" in str(v)]

if RUNS: print("problems in the traces:", pii_problems(EXPORTER.get_finished_spans()) or "none")

# %% [markdown]
# ### Step 6: cost per success
# Spend is the sum of the chat spans: token counts times the price. Cost per success is the spend of all runs, the failed ones too, divided by the runs that stopped `answered`.

# %%
def cost_per_success(spans):
    spend = sum(call_cost(s.attributes["gen_ai.usage.input_tokens"], s.attributes["gen_ai.usage.output_tokens"])
                for s in spans if s.attributes.get("gen_ai.operation.name") == "chat")
    stops = [s.attributes["loop.stop_reason"] for s in spans if s.attributes.get("loop.run_id") is not None]
    successes = stops.count("answered")
    print(f"total spend USD {spend:.6f} over {len(stops)} runs, successes {successes}")
    return spend / successes if successes else None

if RUNS:
    r = cost_per_success(EXPORTER.get_finished_spans())
    print(f"cost per success (USD): {f'{r:.6f}' if r else 'n/a'}")

# %% [markdown]
# ## At real scale
# - **Traces are only as complete as the export.** Export is batched (5 s traces, 60 s metrics by default), so a killed process loses its buffer. → lesson 28
# - **Content is opt-in for a reason.** Claude Code telemetry keeps prompts and tool content off until `OTEL_LOG_USER_PROMPTS=1` turns them on. Use that flag in staging only, for the runs you debug.
# - **Failed runs are the bill.** Watch cost per success. Caps per run, per tenant and per organisation are enforced at the gateway (the proxy every model call goes through), so one tenant cannot spend the whole month's budget. → lesson 28a serves the loop as a service; per-tenant limits and gateway keys are in lesson 29a.

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One run you read yourself | Print the span tree from the in-memory exporter | No backend to run |
# | Many runs in production | Export spans over OTLP to a trace viewer (lesson 28) | Search, alerts and history |
# | Any span attribute | Allow-list the keys; store ids and counts, not text | Spans are copied to dashboards and vendors |
# | Nightly check on a changed prompt | Pilot on 50 cases, then the full set; the checker on the small model | Cost grows with cases times calls |
# | Loop runs on every commit | Run it only when the prompt, tools or model change | Same answer, new bill |
# | Cost per success rising, success flat | Read the failed runs first: find their stop reason | Failed runs are the hidden cost |

# %% [markdown]
# ## What just happened
# Run A made two model replies: the first called `issue_refund`, the second gave the answer, and the run stopped `answered`. Run B stopped after its one allowed reply, which asked for a refund. Its cap stopped the loop before that refund ran, so nothing was written for it, but the one reply was paid for. The spans show the same story: the root carries the stop reason, each iteration carries its number, and cost per success counts the failed run's spend. The customer's words never reached a span.

# %% [markdown]
# ## Common mistakes
# Putting the customer's words into a span attribute is the easiest mistake, and the check in Step 5 catches it. This cell writes that mistake on purpose. It uses its own exporter, so the run's spans stay clean, and it runs the same check. The error is expected.

# %% tags=["raises-exception"]
MISTAKE = InMemorySpanExporter()
bad_provider = TracerProvider()
bad_provider.add_span_processor(SimpleSpanProcessor(MISTAKE))
with bad_provider.get_tracer("mistake").start_as_current_span("iteration") as bad:
    bad.set_attribute("customer.message", "Customer C-17 says the jacket is torn")  # wrong: raw customer text
assert not pii_problems(MISTAKE.get_finished_spans()), "this error is expected: customer text reached a span"

# %% [markdown]
# The fix is the allow-list: store the run id, the iteration and the counts. The customer's text stays in the database that owns it. The bad span lived in its own exporter, so the run's spans are still clean:

# %%
if RUNS: print("problems in the run spans:", pii_problems(EXPORTER.get_finished_spans()) or "none")

# %% [markdown]
# ### Cost control for unattended loops
# Cost grows with cases times calls times tokens. Price a nightly run before you schedule it.

# %% [markdown]
# ## Try it
# A nightly check runs 1,000 cases. Each case makes 2 checker calls, each with 1,500 input tokens and 200 output tokens, at the price above. Write `nightly_usd(cases, calls, in_tok, out_tok)` that returns the dollars for one nightly run. Predict the answer first.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def nightly_usd(cases, calls, in_tok, out_tok):
    return cases * calls * call_cost(in_tok, out_tok)

per_night = nightly_usd(1000, 2, 1500, 200)
print(round(per_night, 4), "USD per nightly run;", round(per_night * 365), "USD a year;",
      round(nightly_usd(50, 2, 1500, 200), 2), "USD for a pilot on 50 cases")

# %% [markdown]
# In the answer above, a nightly run of 1,000 cases costs 0.46 USD, about 168 USD a year, so pilot on 50 cases (0.02 USD) and run the full set only when the prompt, tools or model change.

# %% [markdown]
# This last code cell saves the recording of the model calls.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Key terms
# - **span** — one timed step of a run, with a name and attributes (lesson 27).
# - **trace** — the tree of spans for one run; the root span is the run.
# - **`loop.iteration`** — the iteration number on each iteration span. A course attribute, not a standard one.
# - **GenAI conventions** — OpenTelemetry names for model and tool spans and their token counts. Still in Development.
# - **allow-list** — the only keys a span may carry. Anything else is refused.
# - **cost per success** — total spend, failed runs included, divided by the successful runs.
# - **per-run budget** — the cap on replies for one run, checked before its tools run.

# %% [markdown]
# **Interview:** How do you know which step of an agent run cost the money, and what the run cost per success? Strong answer: a span per run and per iteration with token counts on the model spans; cost summed over the spans, failed runs included; cost per success as the total over the successes; an allow-list so no customer text reaches a span; and caps per run that stop the loop before its tools run.
