# %% [markdown]
# # 02 · Your first model call: messages, usage, cost and streaming
# Level L1 · Part 1 · core · ~20 min · builds on 01
#
# ## Goal
# Make one model call through the course helper `get_llm()`, read its usage and cost, and stream a second reply as it is written.
#
# ## Why it matters
# Without a helper, one model call means you build the request yourself in the provider's wire format, send it over HTTP, dig the reply text out of nested JSON, and count tokens by hand to learn what it cost. Each provider uses its own field names, so a change of model can mean a change of code. You do not need the raw format every day. You do need the usage and cost of every call, because cost is what a loop runs out of first.
#
# The first code cell starts the recording layer. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("02_first-model-call")  # records the model calls once, replays them later

# %% [markdown]
# ## The idea
# **A model call sends a list of messages and gets one reply back, with a receipt for the tokens it used.** Each message has a role. The `system` message sets the rules, the `user` message is the request, and the `assistant` message is what the model said before. The reply holds the text and a usage record: input tokens you sent and output tokens that came back. A token is a small piece of text, roughly three-quarters of a word. Cost is the token counts times the price per million tokens.
#
# Analogy: a letter to a desk clerk. The system message is the desk's policy binder, the user message is the customer's letter, and the reply is the clerk's written answer with a receipt that counts the words read and written.
#
# ## Picture
# The request holds the rules and the question. The reply holds the answer and the receipt. The receipt sets the cost.
#
# ```mermaid
# flowchart LR
#   S["system: the desk's rules"] --> R[Request]
#   U["user: the customer's message"] --> R
#   R -->|one call| M[Model]
#   M --> A["reply text"]
#   M --> K["usage: input and output tokens"]
#   K --> C["cost = tokens x price per million"]
# ```

# %% [markdown]
# ## Step by step
# 1. Connect with `get_llm()`. Step 1 below says what it returns.
# 2. Send one request with `invoke`. It waits for the whole reply.
# 3. Read the usage and turn it into dollars.
# 4. Stream a second reply: print each piece as it arrives, then join the pieces.

# %% [markdown]
# ### Step 1: connect
# `get_llm()` returns a LangChain chat model. It reads the key from `.env` and sets `temperature=0` for you. It takes LangChain message objects (`HumanMessage`, `SystemMessage`) and translates them into each provider's wire format, so you never write a provider's raw request shape yourself. The newest Claude models do not accept `temperature`, `top_p` or `top_k`, so this lesson never sets them.
#
# The model is the course default. A live run can use another model through `TUT_LLM_MODEL` in `.env`. While a recording replays, the notebook uses the default model the recording was made with. Anthropic and other providers are optional and untested in this lesson. Add a price row first.

# %% tags=["needs-llm"]
import llm_replay
from llm_setup import DEFAULT_MODELS, get_llm
from tut_env import env

# A recording was made with the default model, so a replay asks for that model.
# A live run uses TUT_LLM_MODEL from .env when it is set.
MODEL = DEFAULT_MODELS["gemini"] if llm_replay.is_replaying() else env("TUT_LLM_MODEL", DEFAULT_MODELS["gemini"])
llm = get_llm(model=MODEL)  # the key comes from .env
print("TUT_LLM_MODEL set in .env:", bool(env("TUT_LLM_MODEL")))
# Print the model name only when it is the course default; a .env override is never printed.
shown = llm.model if llm.model == DEFAULT_MODELS["gemini"] else "your TUT_LLM_MODEL (not shown)"
print("model:", shown)

# %% [markdown]
# ### Step 2: one call
# The `system` message tells the model how to answer. `invoke` sends the list of messages and returns one reply.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content="You are the support desk for Brightside Outfitters. Answer in two short sentences."),
    HumanMessage(content="A customer says their jacket arrived torn after one wash and asks for a refund. What should the desk check first?"),
]
reply = llm.invoke(messages)  # reply.text is the answer; step 3 reads its usage
print(reply.text)

# %% [markdown]
# ### Step 3: usage and cost
# Every reply carries `usage_metadata`, a dict with `input_tokens` and `output_tokens`. Ignore `input_token_details` for now. The prices below are the Gemini Developer API list prices for standard paid-tier text, read on 2026-10-27. Vertex AI has its own price page; these are close, but check yours. Prices change, so check them again before you rely on them. Audio input costs more; this lesson uses text only.

# %%
from llm_setup import DEFAULT_MODELS
# USD per 1M text tokens. Gemini Developer API list prices, standard paid tier
# (ai.google.dev/gemini-api/docs/pricing, read 2026-10-27). Vertex AI has its own price page: check yours.
PRICES = {
    DEFAULT_MODELS["gemini"]: {"input": 0.10, "output": 0.40},  # the course default model
}

def call_cost(usage, price):
    """Dollars for one call: input tokens and output tokens, each at its own price per 1M tokens."""
    return (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000

price = PRICES[llm.model]  # keyed on the model actually used; KeyError means no price row yet: add one first
usage = reply.usage_metadata  # a dict: input_tokens and output_tokens
print("usage:", usage)
print(f"cost of this call: ${call_cost(usage, price):.6f}")
print(f"1,000 calls like this one: ${1000 * call_cost(usage, price):.4f}")

# %% [markdown]
# ### Step 4: streaming
# `stream` yields the reply in small chunks while the model writes. Print each chunk as it arrives and join the chunks into one message. The usage is summed from the chunks. Chunk boundaries and the number of chunks vary by run, so compare totals, not chunk counts.

# %% tags=["needs-llm"]
messages2 = [
    SystemMessage(content="You are the support desk for Brightside Outfitters. Answer in two short sentences."),
    HumanMessage(content="Write the reply to the customer who reported the torn jacket. Say the desk is checking the order."),
]
full = None
chunks = 0
for chunk in llm.stream(messages2):
    print(chunk.text, end="", flush=True)
    full = chunk if full is None else full + chunk  # chunks add up to one message
    chunks += 1
print()
print("chunks received (varies by run):", chunks)
print("usage:", full.usage_metadata)
print(f"cost of the streamed call: ${call_cost(full.usage_metadata, price):.6f}")

# %% [markdown]
# ## At work
# - Teams log input and output tokens on every model call and compute cost per run and cost per successful task. A failed run is still paid for, so cost per success is the number that matters. → lesson 27 (observability and cost)
# - Batch APIs price work that can wait lower; Anthropic lists -50% on batch requests. An overnight eval loop is a candidate. → lesson 27 (observability and cost) <!-- RESEARCH.md section 3, cost engineering -->
# - Teams version the model id together with the prompt, tools and verifier in one config bundle and roll it out by shadow run or canary. → lesson 29b (identity, audit and rollout)

# %% [markdown]
# ## Common mistakes
# 1. **Reading usage from the wrong object.** The usage record is `usage_metadata` on the reply. A reply has no `usage` field.

# %% tags=["raises-exception"]
reply.usage  # AttributeError: the reply has no attribute 'usage'

# %% [markdown]
# Fix: read `reply.usage_metadata`, as in step 3.
#
# 2. **Changing the model and forgetting the price table.** The cost function needs a price for every model it sees.

# %% tags=["raises-exception"]
PRICES["gemini-unknown-model"]  # KeyError: no price for this model

# %% [markdown]
# Fix: add the model and its prices to `PRICES`, with the date you read them.

# %% [markdown]
# ## Try it
# A larger model costs $0.30 per 1M input tokens and $2.50 per 1M output tokens. Use the token counts from the streamed call (`full.usage_metadata`) and the `call_cost` function with those prices. Print the cost and how many such calls fit in $1. Do not call the model.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
larger = {"input": 0.30, "output": 2.50}
cost_larger = call_cost(full.usage_metadata, larger)
print(f"cost on the larger model: ${cost_larger:.6f}")
print("calls like this one that fit in $1:", int(1 / cost_larger))

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - `get_llm()` gives you a chat model; the key stays in `.env`.
# - A call sends messages (`system`, `user`, `assistant`) and returns text plus `usage_metadata`.
# - Cost = input tokens x input price + output tokens x output price, per 1M tokens. Check the price date.
# - `stream` gives the same reply in chunks; the usage is summed from them.
# - Words to keep: **token**, **message role**, **usage**, **streaming**.
#
# **Interview:** "How do you know what a model call costs?" A strong answer: read the usage on every response, multiply input and output tokens by the current price per million, and log cost per run so you can compute cost per successful task.
