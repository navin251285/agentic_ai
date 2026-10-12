# %% [markdown]
# # 24 · Tool catalogs: token cost, selection accuracy and name collisions
# Level L4 · Part 5 · professional · ~40 min · builds on 05

# %% [markdown]
# ## Goal
# By the end you can say what a tool catalog costs in input tokens at 5, 20 and 60 tools, check how often a real model picks the right tool from each catalog, and show that two servers that both publish `search` collide until you namespace them.

# %% [markdown]
# ## Why it matters
# Without thinking about the catalog, a host sends every tool's name, description and input schema with every model call. Five servers with twelve tools each put sixty tool definitions into every turn, even when the question needs one of them. The cost grows with each server you connect, and the model has more look-alike tools to choose from.
#
# Names collide too. Two servers that each publish `search` look like two tools. A host that merges them into one dictionary by name keeps one and drops the other, and nothing raises an error.
#
# What it makes easy: you see the cost before the catalog grows, keep descriptions short, and namespace names so they stay unique. You do not need this for a host with three tools from one server.

# %% [markdown]
# ## The idea
# The tool catalog is the list of tool definitions a host sends with each model call. The model reads each name and description to choose a tool. So the list costs input tokens on every turn, and its wording changes which tool the model picks. Long catalogs with look-alike tools make wrong picks more likely. When two servers publish the same name, the names collide. Namespacing (`{server}_{tool}`, lesson 05) keeps them apart.
#
# Analogy: a menu. A short menu is quick to read and easy to choose from. A sixty-item menu with near-identical dishes costs you time on every visit. Two dishes with the same name on two menus get mixed up at the table.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   S1[Catalog server: 5 to 60 tools] --> H[Host: one list]
#   S2[Runbooks server: search] --> H
#   H -->|every turn: names, descriptions, schemas| M[Model]
#   H -->|merge by bare name| X[One search kept, one lost]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Build a catalog of any size
# `build_catalog(size)` publishes the first `size` tools of one fixed list. The list starts with Trackr's five core tools, then eight near-miss tools that sound like them, then filler tools from other ops areas. The server runs in the same process, so no subprocess is needed. The runbooks server from lesson 05 is the second server.

# %%
import sys, json
sys.path.insert(0, "..")            # so llm_setup and llm_replay import
sys.path.insert(0, "../apps/24")    # build_catalog
sys.path.insert(0, "../apps/05")    # the runbooks server from lesson 05
from catalog_server import build_catalog
from runbooks_server import mcp as runbooks_mcp
from mcp import Client

async with Client(build_catalog(5)) as c:
    print("5 tools:", [t.name for t in (await c.list_tools()).tools])

# %% [markdown]
# ### 2. Count the catalog before any model call
# A model call bills the tool list as input tokens. You can measure it first. `catalog_json` returns the list the host would send: one OpenAI-style function entry per tool, with its name, description and input schema. Characters divided by four is a rough token estimate. The model's own count comes later, from the reply.

# %%
async def catalog_json(size, verbose=False):
    """The list a host sends with each model call: one function entry per tool."""
    async with Client(build_catalog(size, verbose)) as c:
        tools = (await c.list_tools()).tools
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.input_schema}} for t in tools]

for size, verbose in [(5, False), (20, False), (60, False), (60, True)]:
    body = json.dumps(await catalog_json(size, verbose))
    label = f"{size} tools" + (", long descriptions" if verbose else "")
    print(f"{label:28} {len(body):6} characters  about {len(body) // 4} tokens")

# %% [markdown]
# ### 3. Set up the model (`needs-llm`)
# This lesson makes four model calls in total, one for each catalog size and one for the long descriptions. Each call sends the same three requests, so the only thing that changes is the catalog. Three requests go in one message per catalog, so four calls cover what would otherwise take twelve. The three requests are answered by `close_issue`, `count_open` and `reopen_issue`. Each of those tools is in every catalog from 5 tools up.

# %%
from langchain_core.messages import HumanMessage
import llm_replay
PROMPT = ("Answer each numbered request with one tool call.\n"
          "1. Close issue 7, it is a duplicate of issue 3.\n"
          "2. How many open issues does the mobile team have?\n"
          "3. Reopen issue 12, the fix did not ship.")
EXPECTED = {"close_issue", "count_open", "reopen_issue"}
llm = None   # set by the model cell below; stays None if that cell is skipped
print("requests ready; the tools that answer them:", sorted(EXPECTED))

# %% [markdown]
# The model cell calls `get_llm`. It prints the model table, starts the recording or the replay for this lesson, and returns the model. Each lesson has its own recording, so the calls replay with no key.

# %% tags=["needs-llm"]
from llm_setup import get_llm
import logging
logging.getLogger("vcr").setLevel(logging.WARNING)          # the recorder logs file paths and the project id
logging.getLogger("httpx").setLevel(logging.WARNING)        # hide the INFO line that prints the model URL
logging.getLogger("google_genai").setLevel(logging.WARNING) # the Vertex SDK logs the project id
llm = get_llm("24_tool-catalog-cost", max_calls=4)   # one call per catalog below

# %% [markdown]
# ### 4. Ask the model with 5, 20 and 60 tools (`needs-llm`)
# `ask` lists the catalog from the server, sends it with the three requests, and reads back the tool calls. A request counts as right when its tool name appears in the reply. The reply also carries `input_tokens`, which the model counts itself.

# %%
async def ask(size, verbose=False):
    """One model call: the catalog, the three requests, and the tool calls that come back."""
    reply = await llm.bind_tools(await catalog_json(size, verbose)).ainvoke([HumanMessage(PROMPT)])
    names = [call["name"] for call in reply.tool_calls]
    return {"hits": sorted(e for e in EXPECTED if e in names), "names": names,
            "input_tokens": reply.usage_metadata["input_tokens"]}

# %% [markdown]
# Now the calls. Each `ask` is one model call. The cell below makes three of them, one for each catalog size, and keeps each answer.

# %% tags=["needs-llm"]
results = {}
if llm is not None:
    for size in (5, 20, 60):
        results[size] = await ask(size)
        r = results[size]
        print(f"{size:>2} tools: {len(r['hits'])} of 3 right, {r['input_tokens']} input tokens, calls {r['names']}")
else:   # fallback: no model here, so no accuracy and no model token counts
    print("model cells skipped: no recording and no key. The catalog sizes in step 2 still hold.")

# %% [markdown]
# ### 5. The same 60 tools with long descriptions (`needs-llm`)
# Same tools, same three requests. Only the descriptions change: each one gets a paragraph of usage rules, limits and paging notes. Generated API wrappers often copy text like this from the API docs. The model reads all of it on every call.

# %% tags=["needs-llm"]
if llm is not None:
    long = await ask(60, verbose=True)
    print(f"60 tools, long descriptions: {len(long['hits'])} of 3 right, {long['input_tokens']} input tokens")
    if 60 in results:
        print(f"extra input tokens from the padding: {long['input_tokens'] - results[60]['input_tokens']}")

# %% [markdown]
# ### 6. Read the results side by side
# This cell prints one table from the runs above. It prints nothing if the model cells were skipped.
#
# Read it with care. The model got all three requests right at every size, so accuracy did not drop in this run. Three requests are a smoke test, not a measurement. The bill did grow: nearly nine times the input tokens from 5 to 60 tools, and the long descriptions bring the 60-tool catalog to about four times its size (1972 to 7852 tokens). A real accuracy check needs more requests, and more calls than this lesson's budget of four.

# %%
if results:
    print(f"{'tools':>6} {'right of 3':>10} {'input tokens':>13}")
    for size, r in results.items():
        print(f"{size:>6} {len(r['hits']):>10} {r['input_tokens']:>13}")

# %% [markdown]
# ### 7. Two servers, one name: a collision (no model)
# Trackr's catalog and the runbooks server both publish `search`. Listing both servers is fine. Merging them by name is not. The merge below is the shortcut many hosts take, and it loses a tool without an error.

# %%
async with Client(build_catalog(5)) as issues, Client(runbooks_mcp) as runbooks:
    issue_tools = (await issues.list_tools()).tools
    runbook_tools = (await runbooks.list_tools()).tools
both = sorted({t.name for t in issue_tools} & {t.name for t in runbook_tools})
print("both servers publish:", both)
merged = {t.name: t for t in issue_tools + runbook_tools}   # merge by bare name
print(f"tools listed: {len(issue_tools) + len(runbook_tools)}, after the merge: {len(merged)}")
print("the search the model sees is:", merged["search"].description)

# %% [markdown]
# Now namespace each name with its server, as lesson 05's adapter does. Each name is unique again, and the server is still in the name.

# %%
namespaced = {f"{server}_{t.name}": t for server, tools in
              [("issues", issue_tools), ("runbooks", runbook_tools)] for t in tools}
print(f"tools after namespacing: {len(namespaced)}")
print("names that now differ:", sorted(n for n in namespaced if n.endswith("search")))

# %% [markdown]
# ## At work
# - Uber reported context bloat and cost once hundreds of servers were connected. Its gateway moved to progressive discovery and trimmed responses instead of sending every schema → lesson 40.
# - Teams snapshot `tools/list` and fail the test when a name or description changes, because an edit to a description changes the model's input and its bill → lesson 27.
# - A description is text the model reads. One server's description can steer the model toward another server's tool, so long descriptions are also a review item → lesson 29.

# %% [markdown]
# ## What just happened
# - The catalog cost grew with the tool count before the model chose anything: 225 input tokens at 5 tools, 708 at 20 and 1972 at 60. Long descriptions took the 60-tool catalog to 7852. The host pays that on every turn.
# - Each model call read the same three requests. All three expected names came back at every size, so this run shows the cost of a catalog, not a drop in accuracy.
# - Two servers published `search`. A merge by bare name kept one of them and reported no error. Namespacing kept both.

# %% [markdown]
# ## Common mistakes
# After namespacing, the bare name is gone. The host now knows `issues_search` and `runbooks_search`, so a lookup by `search` fails:

# %% tags=["raises-exception"]
print(namespaced["search"].name)   # KeyError: the names are namespaced now

# %% [markdown]
# Fix: look up the prefixed name that the listing printed, such as `namespaced["issues_search"]`.
#
# A second trap is the estimate. Characters divided by four is a rough guide to the catalog's size. Only the `input_tokens` in a model reply is the count the model bills. Use the reply for budgets, and the estimate for a quick check. In step 2 the estimate said about 3954 tokens for 60 tools; the model counted 1972.

# %% [markdown]
# ## Try it
# Use `build_catalog(20)` through an in-process `Client`, as in step 7. Print how many tool names contain the word `issue`, and the names of the three tools with the longest descriptions. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
async with Client(build_catalog(20)) as c:
    tools = (await c.list_tools()).tools
with_issue = [t.name for t in tools if "issue" in t.name]
print(len(with_issue), "names contain 'issue':", with_issue)
longest = sorted(tools, key=lambda t: len(t.description), reverse=True)[:3]
print("longest descriptions:", [t.name for t in longest])

# %% [markdown]
# ## Key terms
# - **tool catalog** — the list of tool definitions (name, description, input schema) a host sends with each model call.
# - **tool-catalog tokens** — the input tokens the catalog adds to every call, whether or not the model uses a tool.
# - **description length** — how many characters each tool's description adds to the catalog; longer text costs more on every turn.
# - **tool-selection accuracy** — the share of requests for which the model names the expected tool.
# - **name collision** — two servers publish the same tool name, so a merge by name keeps one and drops the other.
# - **near-miss tool** — a tool whose name or description sounds like another one, so the model is more likely to pick it by mistake.

# %%
llm_replay.stop()   # saves the recording, if this run made model calls
print("lesson 24 done: catalog cost counted, accuracy checked at 5, 20 and 60 tools, collisions shown")
