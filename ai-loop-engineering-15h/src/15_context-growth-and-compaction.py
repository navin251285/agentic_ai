# %% [markdown]
# # 15 · Context growth: caching, clearing tool results and compaction
# Level L3 · Part 2 · professional · ~20 min · builds on 12
#
# ## Goal
# Watch the input of one long chat grow with every turn, then keep it bounded by clearing old tool results and compacting old turns into a summary. Use the input-token counts the real model returns. Caching is explained, not measured, in this lesson.
#
# ## Why it matters
# A chat sends everything before it again on each call. Each turn adds to the input, so the total grows faster than the work. Without bounding:
#
# | Without bounding | What goes wrong |
# |---|---|
# | Every turn resends the whole chat | With 500 new tokens a turn, ten turns send 500 × (1+2+...+10) = 500 × 55 = 27,500 input tokens in total (arithmetic). Ten fresh calls send 5,000 |
# | Old pytest output stays in full | The line that matters sits under output from turns that are already fixed |
# | The rules sit in the first user message | A cut that drops old messages drops the rules with them |
#
# With bounding, each call sends the rules, a short summary and the latest tool result. You do not need it for a loop of two or three short turns. Lesson 11 kept each call small by using a fresh context per item.

# %% [markdown]
# ## The idea
# **Three levers, each with one job. Caching makes a repeated prefix cheaper to read, but it does not make the context shorter. Clearing replaces an old tool result with a short marker and needs no model call. Compaction asks the model to write a summary of the old turns, and the summary replaces them. Keep the rules in the system message, because that is the part a cut keeps.**
#
# Analogy: a long meeting with a shared folder of printouts. Clearing crosses out last week's printouts. Compaction swaps the full transcript for the minutes. Caching is the agenda the room keeps on file: it costs less to read again, but it still takes up the table.
#
# Lesson 11 avoided the growth with a fresh context per call. Some loops need one chat, because the model must remember what it already tried. Then the growth has to be bounded.

# %% [markdown]
# ## Picture
# Each turn adds to the history. Before a call, the loop checks the size. If the history is too big, old tool results are cleared and old turns are compacted into a summary.
#
# ```mermaid
# flowchart TD
#   T["Turn n: a module, its test and the pytest result"] --> H["History so far"]
#   H --> C{"Too big for the next call?"}
#   C -->|"no"| M["One model call: input tokens measured"]
#   C -->|"yes"| R["Clear old tool results"]
#   R --> S["Compact: the model writes a summary of old turns"]
#   S --> N["Next call: rules + summary + latest turn"]
#   N --> M
#   M --> T
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the repo and the three turns (no model call)
# `pocket-cart` is the generated shop repo from lesson 07. This lesson uses three modules: money, pricing and tax, with two failing tests each. The one chat works on a copy in `../data/15`, so `../data/pocket-cart` is never edited. The helpers below are lesson 12's, cut down to one test file at a time.

# %%
import os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("15_context-growth-and-compaction")  # records the model calls once, replays them later

SRC = Path("../data/pocket-cart")          # generated once; this lesson only reads it
WORK = Path("../data/15")                  # run-time copies of the repo
PYTHON = os.path.abspath(sys.executable)   # the kernel may give a relative path
TURNS = ["tests/test_money.py", "tests/test_pricing.py", "tests/test_tax.py"]  # one module per turn
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)
chat = WORK / "chat"                       # the repo that the one chat edits
shutil.copytree(SRC, chat)

def pytest(work, *args):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    return subprocess.run([PYTHON, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *args],
                          cwd=work, capture_output=True, text=True, env=env)

def failing(work, test_file):  # the verifier's failing ids for one test file
    out = pytest(work, "--tb=no", "-rf", test_file).stdout
    return [line[len("FAILED "):].split(" - ")[0] for line in out.splitlines() if line.startswith("FAILED ")]

def tool_result(work, test_file):  # the pytest output the loop feeds back: the assertion lines only
    out = pytest(work, "--tb=short", test_file).stdout
    return "\n".join(line for line in out.splitlines() if line.startswith("E "))[:600]

print("failing per turn:", {Path(t).name: len(failing(chat, t)) for t in TURNS})
print("\n".join((chat / TURNS[0]).read_text().splitlines()[:5]))

# %% [markdown]
# ### Step 2: the messages and the two ways to shrink them (no model call)
# A turn is one human message: the module, its test file and the tool result. The reply is the whole new module. `clear_results` replaces the tool results of old turns with a marker, and keeps the latest one. Clearing is string work, so it costs no model call.

# %%
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

ITEM_SYSTEM = ("You fix one module of a small Python shop. The test file is the spec: never change it. "
               "Fix only what the failing test asks. Reply with the complete new text of the module, "
               "then one line 'DONE: yes' or 'DONE: no' for the whole suite. No prose, no code fences.")
CLEARED = "[cleared: pytest output from an earlier turn]"

def module_of(work, test_file):  # tests/test_money.py -> pocket_cart/money.py
    return work / "pocket_cart" / Path(test_file).name.replace("test_", "", 1)

def user_turn(work, test_file):  # one turn: the module, its test file and the tool result
    module = module_of(work, test_file)
    return HumanMessage(content=(f"### MODULE {module.relative_to(work)}\n{module.read_text()}\n"
                                 f"### TEST FILE {test_file}\n{(work / test_file).read_text()}\n"
                                 f"### TOOL RESULT (pytest)\n{tool_result(work, test_file)}\n"))

def apply_reply(work, test_file, reply):  # write the module; return how many tests in the file are still red
    text = reply.text.replace("```python", "").replace("```", "")
    module_of(work, test_file).write_text(re.sub(r"^DONE:.*$", "", text, flags=re.M | re.I).strip("\n") + "\n")
    return len(failing(work, test_file))

def clear_results(history, keep_last=1):  # no model call: old tool results become a short marker
    human = [i for i, m in enumerate(history) if isinstance(m, HumanMessage)]
    out = list(history)
    for i in human[:-keep_last]:
        text = re.sub(r"### TOOL RESULT \(pytest\)\n.*", f"### TOOL RESULT (pytest)\n{CLEARED}", out[i].content, flags=re.S)
        out[i] = out[i].model_copy(update={"content": text})
    return out

# %% [markdown]
# ### Step 3: turns 1 and 2 in one chat (two model calls)
# The model is the course default. `ask` sends the whole history with the new turn, and logs the input tokens that the reply reports. The log is the evidence for the rest of the lesson.
#
# `usage_metadata` is LangChain's usage record for the reply. `input_tokens` is the total input the model read. `input_token_details` is a breakdown of it, and its `cache_read` key is how many of those input tokens came from the provider's cache. For Gemini, LangChain reports `cache_read` inside `input_tokens`, so do not add it on top. The Claude API reports cache reads apart from `input_tokens` (its docs give the total as read + written + input). This recording's `cache_read` is 0 in every call.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env; a recording replays without one
CALLS = []  # one row per model call: label, input tokens, cache reads, output tokens

def ask(history, new, label):  # one call with the whole history so far; logs the real usage
    reply = llm.invoke(history + [new])
    use = reply.usage_metadata
    CALLS.append({"call": label, "input": use["input_tokens"],
                  "cached": use.get("input_token_details", {}).get("cache_read", 0), "output": use["output_tokens"]})
    return reply

history = [SystemMessage(content=ITEM_SYSTEM)]
for n, test in enumerate(TURNS[:2], 1):
    new = user_turn(chat, test)
    reply = ask(history, new, f"turn {n}")
    history += [new, reply]
    print(f"turn {n} {Path(test).name}: still red in this file {apply_reply(chat, test, reply)}")
for row in CALLS:
    print(f"{row['call']:8s} input {row['input']:>5} | cache read {row['cached']} | output {row['output']}")

# %% [markdown]
# ### Step 4: the branch point, three calls (three model calls, five in all)
# Turn 3 runs two ways from the same history. The first way keeps the whole chat (call 3). The second way compacts turns 1 and 2 into a summary, and sends only the rules, the summary and the turn 3 message (calls 4 and 5). Both start from the same repo state, so the two answers are comparable. The summary goes into the human turn, not the system message, because the system message holds the standing rules for every call, while a summary is a model's claim about past work that the next turn should check. The message types before and after the cut are printed in step 5.

# %% tags=["needs-llm"]
branch = WORK / "branch"
shutil.copytree(chat, branch)  # the repo after turn 2, for the bounded run

full_new = user_turn(chat, TURNS[2])
full_reply = ask(history, full_new, "turn 3, full chat")  # call 3: the whole chat
print("full chat, turn 3 tax: still red", apply_reply(chat, TURNS[2], full_reply))

COMPACT = ("Summarise this earlier work on a Python shop repo for the next turn. In at most 60 words: "
           "which modules were fixed, which tests still fail, and the rule that test files never change. Plain text.")
transcript = "\n\n".join(f"{m.type.upper()}:\n{m.content}" for m in history[1:])  # every turn so far, no system message
summary = ask([SystemMessage(content=COMPACT)], HumanMessage(content=transcript), "compaction")  # call 4
print("summary written by the model:", summary.text)

bounded_new = user_turn(branch, TURNS[2])
earlier = HumanMessage(content="### EARLIER TURNS (summary, written by the model)\n" + summary.text
                       + "\n\n" + bounded_new.content)
bounded_reply = ask([SystemMessage(content=ITEM_SYSTEM)], earlier, "turn 3, bounded")  # call 5
print("bounded, turn 3 tax: still red", apply_reply(branch, TURNS[2], bounded_reply))
for row in CALLS[2:]:
    print(f"{row['call']:18s} input {row['input']:>5} | cache read {row['cached']} | output {row['output']}")

# %% [markdown]
# ### Step 5: clearing alone, and a library cut (no model call)
# Clearing alone is an estimate here, because it needs a call to measure. `count_tokens_approximately` from `langchain_core` counts characters, so it is only a guide. It ignores the template and the message overhead, so compare estimates with estimates only, never with the measured numbers. The measured numbers are the ones in the table. `trim_messages`, also from `langchain_core`, is the library's cut: it keeps the newest messages that fit, and keeps the system message when you ask it to. The cell prints the messages before and after each cut, and the cleared message next to the original. Here the cut keeps the system message and the newest human turn, and drops the two earlier turns with their replies. The "half the size" budget is only an example: a real loop sets the budget from the model's context limit or from a spend cap per run.

# %%
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.messages import trim_messages

full_input = history + [full_new]
cleared = clear_results(full_input, keep_last=1)

def tool_part(text):  # the TOOL RESULT section of one turn
    return text.split("### TOOL RESULT (pytest)\n", 1)[1]

print("turn 1, original tool result:\n" + tool_part(full_input[1].content))
print("turn 1, after clearing:\n" + tool_part(cleared[1].content))  # the marker replaces the output; the module and test stay
print(f"estimate, full chat     : {count_tokens_approximately(full_input)} tokens")
print(f"estimate, clearing only : {count_tokens_approximately(cleared)} tokens")
print(f"measured, full chat     : {CALLS[2]['input']} input tokens (call 3)")
print(f"measured, bounded       : {CALLS[4]['input']} input tokens (call 5)")
kept = trim_messages(full_input, max_tokens=count_tokens_approximately(full_input) // 2,
                     token_counter=count_tokens_approximately, strategy="last",
                     include_system=True, start_on="human")
print("trim to half the estimate, before:", [m.type for m in full_input], count_tokens_approximately(full_input))
print("trim to half the estimate, after :", [m.type for m in kept], count_tokens_approximately(kept))
print("the rules survive the cut:", "never change" in kept[0].content)
# compaction, message types before and after: the summary is a human message, the rules stay the system message
print("compaction, before:", [m.type for m in full_input])
print("compaction, after :", [m.type for m in [SystemMessage(content=ITEM_SYSTEM), earlier]])
print("cache reads reported by the API (0 = no hit):", [r["cached"] for r in CALLS])
# the summary is a model claim: check it against the verifier before a turn relies on it
print("summary claims money tests still fail:", "still fail" in summary.text,
      "| pytest says red:", len(failing(branch, TURNS[0])))

# %% [markdown]
# ### Caching: how it works (explained, not measured here)
# This lesson does not turn caching on, and the recording shows no cache reads. **Gemini** caches implicitly: on the 2.5 models it is on by default and needs no code. **Claude** needs a `cache_control` marker: `{"type": "ephemeral"}` at the top level of the request for automatic caching, or on one content block for an explicit breakpoint. Read the provider's prompt-caching page for the minimum prompt length and the exact fields.
#
# A cache hit needs an identical prefix: the tools, the system message and the messages, in that order, byte for byte, up to the marked block. Clearing and compacting edit the history, so the prefix changes from the first edited message on, and the cache misses from there. Caching lowers the price of a repeated prefix. It does not change the context.

# %% [markdown]
# **What the recorded run showed** (one sample, the course's default Gemini model, recorded 2026-10-27). Input tokens grew with each turn: 376 for turn 1, 739 for turn 2 and 1,106 for turn 3 with the whole chat. The compaction call read the old turns (814 tokens) and wrote 43 tokens of summary. The bounded turn 3 call sent 411 tokens, 63% fewer than the full chat, and it still made the tax module pass. Clearing alone was only an estimate: 784 down to 725 tokens, because these tool results are short.

# %% [markdown]
# **The summary was wrong** (it says fixed and still failing in the same breath). It said the money tests still failed, but pytest showed them passing after turn 1. A summary is the model's claim, so check it against the verifier. If the check fails, write the summary again with the verifier's failing list in the prompt, or drop the summary and send the rules and the latest turn. The cache column reads 0 in every call. The prompts were short (376 to 1,106 tokens), and the Gemini docs give a 2,048-token minimum for implicit caching on the 2.5 Flash and Pro models, so check your model's minimum before you expect a hit.

# %% [markdown]
# ## At work
# - Claude Code compacts old turns automatically, has a PreCompact hook, and re-reads CLAUDE.md on each request. Its docs warn that instructions given only early in a chat can be lost in a summary. → lesson 16 keeps the loop's controls in files and hooks, not the first prompt.
# - Prompt caching bills a repeated prefix at a fraction of the input price: `claude-haiku-5-5` lists cache reads at $0.01 per million tokens against $0.10 for input (RESEARCH.md, section 2; the lesson's recorded model is Gemini; the price is Anthropic's). Caching lowers the bill, not the context. → lesson 27 turns the token counts into a budget per run.
# - Token cost usually dominates container cost by an order of magnitude or more, and a chat that resends every turn is where it grows (RESEARCH.md, section 7.6). Teams cap the turns and the spend per run. → lesson 26a adds the durable state that a compacted chat cannot hold.

# %% [markdown]
# ## Common mistakes
# Wrong: the rules live in the first user message. A cut that drops the oldest message drops the rules too.
# The cell below does the cut by hand, and asserts that the rule still exists after it.

# %% tags=["raises-exception"]
first_turn = [HumanMessage(content="Rule: never change a test file. Turn 1: fix money."), AIMessage(content="DONE: yes")]
after_cut = [SystemMessage(content="You fix one module of a small Python shop.")] + first_turn[1:] \
    + [HumanMessage(content="Turn 3: fix tax.")]  # the cut removed the first user message
assert any("never change" in m.content for m in after_cut), "the rule went with the first message"  # AssertionError

# %% [markdown]
# Right: put the rules in the system message, which every call sends, and keep the state that matters outside the chat (the tests, git, the table from lesson 12).
#
# Wrong: a summary is true, so the loop can rely on it. The summary in this recording said the money tests still failed. pytest said they passed. Check the summary against the verifier before the next turn.
#
# Wrong: prompt caching makes the context smaller. It makes the same prefix cheaper to read. The cached prefix is still part of the input the model reads, so the context is the same size.

# %% [markdown]
# ## Try it
# Clearing changes only the old tool results. Print the turn 1 tool result before and after clearing, in characters, and the saving as a percent. Clearing makes no model call, so this lesson cannot show that the model still continues after it. Check that in your own loop with one real call.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
orig = tool_part(full_input[1].content)
clr = tool_part(cleared[1].content)
print(f"turn 1 tool result: {len(orig)} characters, after clearing {len(clr)}, saving {100 * (1 - len(clr) / len(orig)):.0f}%")
# The cleared message is smaller, and it keeps the module and the test file. Whether the model still
# continues from it needs a real call, which this lesson does not make.

# %% [markdown]
# Save the recording. This is the last cell that touches the model layer.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

# %% [markdown]
# ## Recap
# - A chat resends its whole history on each call, so the input grows with every turn.
# - Clearing swaps old tool results for a marker and needs no call. Compaction swaps old turns for a model-written summary and costs one call.
# - Caching makes a repeated prefix cheaper, and only an identical prefix hits. It does not shrink the context. Clearing and compacting change the prefix, so the cache misses from the first edit on.
# - Keep the rules in the system message. A cut or a summary that drops the first user message drops the rules with it.
# - Measure the input tokens of each call from the reply's usage, and do not guess them.
#
# **Interview:** How do you keep a long agent loop's context from growing without limit, and what do you lose? Strong answer: clear old tool results, compact old turns with a model-written summary, keep the rules in the system message, and count the input tokens per turn. Compaction loses detail, so the facts that matter (tests, git, the table) live outside the chat.
