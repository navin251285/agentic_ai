# Task: Build a step-by-step LangGraph tutorial (calculator-first, LLM-light)

> **Claude Code: skip section 0.** It is instructions for the human. Start at section 1 and do only the part you are asked to do in the prompt.

---

## 0. How to run this in Claude Code (for the human)

Don't ask Claude Code to build everything at once: the context fills with old notebook code and later lessons get sloppier. Build one small piece per session, check it, commit it, `/clear`, and move on. The spec stays in the folder as the reference; `CLAUDE.md` carries the rules into every session.

### Step 1 — Set up the folder (once)

```bash
mkdir langgraph-calculator-tutorial && cd langgraph-calculator-tutorial
git init
# copy this file (BUILD_LANGGRAPH_TUTORIAL.md) into the folder
claude
```

### Step 2 — Make the rules permanent

Paste into Claude Code:

```
Read BUILD_LANGGRAPH_TUTORIAL.md. Create a short CLAUDE.md containing only
section 2 (ground rules) and the lesson template from section 5, plus one line:
"Full spec is in BUILD_LANGGRAPH_TUTORIAL.md — read only the section you're told to."
Don't build anything else yet.
```

### Step 3 — Scaffold only

Press **Shift+Tab** to switch to plan mode (it shows a plan before touching files), then paste:

```
Do sections 3, 4 and 6 of BUILD_LANGGRAPH_TUTORIAL.md: folder layout, requirements.txt,
env.example, .gitignore, llm_setup.py, README skeleton, empty GLOSSARY.md.
Create a venv and install. Then build only notebook 00. Run it and show me
the versions installed.
```

Then add your `.env` with `GOOGLE_CLOUD_API_KEY=...`, run notebook 00 yourself, and commit:

```bash
git add . && git commit -m "setup"
```

### Step 4 — Build one or two lessons per session

Type `/clear`, then paste this prompt, changing only the lesson numbers:

```
Build lesson 02 from section 5 of BUILD_LANGGRAPH_TUTORIAL.md. Follow the lesson
template in CLAUDE.md. Execute the notebook with nbconvert and fix any errors.
Add new terms to GLOSSARY.md and the exercise answer to solutions/. Then stop.
```

If a lesson builds on an earlier graph, add: `Reuse the graph from notebook 05.`

| Session | Lessons | Notes |
| --- | --- | --- |
| 1 | 01 + 02 | |
| 2 | 03 + 04 | |
| 3 | 05 + 06 | |
| 4 | 07 | |
| 5 | 08 + 09 | |
| 6 | 10 + 11 | |
| 7 | 12 | |
| 8 | 13 | big: memory and checkpointers |
| 9 | 14 | big: interrupt |
| 10 | 15 + 16 | |
| 11 | 17 | |
| 12 | 18 | |
| 13 | 19 | uses the LLM |
| 14 | 20 | capstone, uses the LLM |

### Step 5 — Review before each commit

Open the notebook and ask yourself: "Would I understand this if I knew nothing?" If not, tell Claude Code exactly what's unclear, for example:

```
The reducer explanation in lesson 06 is too abstract. Add a before/after example
that prints both states side by side.
```

Then commit: `git add . && git commit -m "lesson 06"`. A bad session can be undone with `git checkout .`.

### Step 6 — Final check (fresh session)

```
Do section 7 of BUILD_LANGGRAPH_TUTORIAL.md (definition of done). Run every
notebook, fix failures, fill in the README lesson table and versions, and
report anything that didn't pass.
```

### Tips

- If a session gets long, `/compact` keeps a summary and frees space; `/clear` between lessons is the cleaner reset.
- Read each lesson and do its exercise before asking for the next. If you spot a misunderstanding early, you can fix it before the remaining lessons are written.

---

You are Claude Code. Build a beginner tutorial that teaches **every core construct of LangGraph** one at a time, using a **calculator** as the running example. The LLM (Gemini via Vertex AI) appears only in a few late lessons; everything else must run **offline with no API key**.

Read this whole file before writing anything. Follow the lesson plan in order. After each lesson, run it and fix it before moving on.

---

## 1. Goals and audience

- Audience: Python beginners who have never used LangGraph. Assume they know functions, dicts and `if` statements, nothing more.
- Goal: after the tutorial, the learner can explain and use: graph, state, node, edge, START/END, compile, invoke, conditional edges, reducers, loops, parallel branches, `Send`, `Command`, input/output schemas, runtime context, checkpointers, threads, state history, time travel, `interrupt`, streaming modes, subgraphs, the long-term store, tools / `ToolNode`, an LLM agent loop, `create_agent`, and the Functional API.
- Teaching rule: **one new idea per lesson**. Concept first in plain English, then the smallest code that shows it, then what happened, then a tiny exercise.
- Running example: a calculator that grows lesson by lesson (add two numbers → pick an operation → keep history → loop → remember across runs → ask a human before dividing by zero → let an LLM pick the tools).

## 2. Ground rules

1. **Target LangGraph 1.x and LangChain 1.x.** Before writing code, check the current docs at https://docs.langchain.com/oss/python/langgraph/overview (and the pages linked below) and confirm every import you use still exists. Do not use anything marked deprecated. In particular:
   - Use `from langchain.agents import create_agent` — **not** `langgraph.prebuilt.create_react_agent` (deprecated in v1).
   - Use `from langchain.messages import ...` for message classes and `from langchain.tools import tool` for tools.
   - Use `input_schema=` / `output_schema=` / `context_schema=` on `StateGraph` (not the old `input=` / `output=` / `config_schema=`).
2. **LLM use is minimal.** Only lessons marked **[LLM]** call Gemini. Every other lesson must run with no network and no key.
3. **Keep cells small.** One idea per code cell, 5–20 lines. Every code cell is preceded by a markdown cell explaining what it does and why.
4. **Show the graph.** In every lesson that builds a graph, print it with `print(graph.get_graph().draw_mermaid())` (text, works offline). Do **not** rely on `draw_mermaid_png()` (it calls a web service). Optionally also render with `IPython.display.Markdown` in a ```mermaid block.
5. **Print, don't assume.** After every `invoke`, print the result so the learner sees exactly what state came back.
6. **No hidden magic.** Don't introduce a helper until the lesson that teaches it. No shared utility code except `llm_setup.py` (below).
7. **Plain language.** Short sentences. Define each term the first time it appears and add it to `GLOSSARY.md`.
8. Never hard-code or commit API keys. `.env` goes in `.gitignore`.

## 3. Project layout to create

```
langgraph-calculator-tutorial/
├── README.md                 # what this is, setup, how to run, lesson index
├── GLOSSARY.md               # every LangGraph term, one or two lines each
├── requirements.txt
├── env.example              # GOOGLE_CLOUD_API_KEY=your-key-here
├── .gitignore                # .env, __pycache__, .ipynb_checkpoints, *.db
├── llm_setup.py              # the ONLY shared code: get_llm()
├── notebooks/
│   ├── 00_setup_and_check.ipynb
│   ├── 01_what_is_a_graph.ipynb
│   ├── ... (one notebook per lesson, numbered as in section 5)
│   └── 20_capstone_calculator_assistant.ipynb
└── solutions/
    └── exercises_solutions.ipynb   # answers to every "Try it" exercise
```

## 4. Environment and LLM setup

`requirements.txt` (verify latest compatible versions, then pin with `>=` lower bounds):

```
langgraph
langchain
langchain-core
langchain-google-genai
langgraph-checkpoint-sqlite
python-dotenv
jupyter
ipykernel
```

`llm_setup.py` must use **exactly** this setup logic (from the learner), wrapped in a function so offline lessons never touch it:

```python
import os
from dotenv import load_dotenv


def get_llm():
    load_dotenv()  # reads GOOGLE_CLOUD_API_KEY from a .env file in this directory, if present

    assert os.environ.get("GOOGLE_CLOUD_API_KEY"), (
        "GOOGLE_CLOUD_API_KEY is not set. Create a .env file in this folder with:\n"
        "  GOOGLE_CLOUD_API_KEY=your-key-here\n"
        "or export it in your shell before launching Jupyter. See README.md."
    )
    print("API key loaded:", bool(os.environ.get("GOOGLE_CLOUD_API_KEY")))

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        vertexai=True,
        api_key=os.environ.get("GOOGLE_CLOUD_API_KEY"),
        max_output_tokens=1024,
        temperature=0,
    )
    return llm
```

Notebooks import it with `sys.path` pointing at the project root. `00_setup_and_check.ipynb` runs the connection test:

```python
llm = get_llm()
print(llm.invoke("Say hello in one short sentence.").text)  # quick connection test
```

`00` must also show the learner how to skip this if they have no key yet: lessons 01–16 don't need it.

## 5. Lesson plan

Each notebook follows this template:

1. **Title + one-sentence goal** ("By the end you can …").
2. **The idea in plain English** (3–6 sentences) + a real-world analogy.
3. **Picture**: a small mermaid diagram of what we're about to build.
4. **Code, step by step** (small cells, each with a markdown explanation above).
5. **What just happened** (bullet recap of the flow, referencing printed output).
6. **Common mistakes** (1–3, each with the error message the learner would see).
7. **Try it** (1–2 exercises; answers in `solutions/`).
8. **Key terms** introduced (links to `GLOSSARY.md`).

### Part A — Core building blocks (no LLM)

**00 Setup and check** — install, `.env`, kernel, optional LLM connection test. Print `langgraph` and `langchain` versions.

**01 What is a graph?** — No LangGraph yet. Explain nodes (steps), edges (arrows), state (the shared notepad). Write the calculator as three plain Python functions called in sequence, then point out what's missing: branching, looping, memory, pausing. Motivate LangGraph.

**02 State** — `TypedDict` state for the calculator: `a: float`, `b: float`, `result: float`. Explain state is a dict every node can read. Briefly show the alternatives (`dataclass`, Pydantic `BaseModel`) and when you'd pick each (Pydantic validates input). No graph built yet beyond printing a state dict.

**03 Nodes** — A node is a plain function `state -> partial update dict`. Write `add_node_fn(state)` returning `{"result": state["a"] + state["b"]}`. Stress: return **only the keys you change**. Call the function directly first (it's just Python), then register it with `builder.add_node("add", add_node_fn)`. Optional final cell: `retry_policy=RetryPolicy(max_attempts=3)` from `langgraph.types`, explained in one line.

**04 Edges, START, END, compile, invoke** — Build the first real graph: `START → add → END`. Then extend to a 3-step pipeline: `parse` (turn `"3 + 4"` into a, op, b) → `calculate` → `format` (`"3 + 4 = 7"`). Show `compile()`, `invoke()`, and `draw_mermaid()`. Explain that compiling checks the wiring (show the error from an edge to a node that doesn't exist).

**05 Conditional edges (routing)** — Router function reads `state["op"]` and returns `"add" | "subtract" | "multiply" | "divide"`. Use `add_conditional_edges("parse", route)` with a `Literal[...]` return type, then show the explicit `path_map` form. Add an `"error"` node for unknown operators. Each operation is its own node so the routing is visible in the diagram.

**06 Reducers (how updates are merged)** — Add `history: Annotated[list[str], operator.add]` so every calculation appends instead of overwriting. Demonstrate side by side: a field **without** a reducer (overwritten) vs **with** one (appended). Then write a custom reducer (e.g. keep only the last 3 entries). Introduce `add_messages` and `MessagesState` here only as a preview ("you'll use this for chat later").

**07 Loops and the recursion limit** — Calculator that repeatedly applies an operation, e.g. "keep doubling until result > 100" or compute a factorial step by step. Conditional edge points back to the same node and to `END` when done. Show `GraphRecursionError` by removing the exit, then fix it, and show `graph.invoke(inputs, {"recursion_limit": 50})`.

**08 Parallel branches (fan-out / fan-in)** — From one input, run `add`, `subtract`, `multiply`, `divide` **in parallel** (four edges from `start_node`), then join in `summary`. Explain supersteps: parallel nodes writing the same key need a reducer (show the `InvalidUpdateError` without one).

**09 Map-reduce with `Send`** — Input is a list of expressions `["1+2", "3*4", "10/5"]`. A conditional edge returns `[Send("evaluate", {"expr": e}) for e in state["exprs"]]`; `evaluate` runs once per item; results collect via a reducer; `total` sums them. Explain `Send` = "run this node once with this specific input".

**10 `Command`: update and route from inside a node** — Rewrite the router from lesson 05 so the `parse` node itself returns `Command(update={...}, goto="multiply")`. Annotate the return type `-> Command[Literal["add", "subtract", ...]]` so the diagram still draws edges. Compare with conditional edges: when to use which.

**11 Input, output and private state schemas** — `StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)`. Input only takes `expression: str`; output only returns `answer: str`; internal fields (`a`, `b`, `op`) stay hidden. Show what `invoke` returns before and after.

**12 Runtime context** — `context_schema` for run-level settings that aren't state, e.g. `decimal_places: int`. Node signature `def format_node(state, runtime: Runtime[Context])` using `from langgraph.runtime import Runtime`; call with `graph.invoke(inputs, context={"decimal_places": 2})`. Explain state = data that changes during the run; context = settings fixed for the run.

### Part B — Memory, control and visibility (no LLM)

**13 Checkpointers and threads (short-term memory)** — Running-total calculator: each call adds to the previous total. Compile with `InMemorySaver` (`from langgraph.checkpoint.memory import InMemorySaver`); use `config = {"configurable": {"thread_id": "alice"}}`. Show two threads keep separate totals. Then:
- `graph.get_state(config)` — current snapshot (`values`, `next`).
- `graph.get_state_history(config)` — every checkpoint, printed as a small table.
- `graph.update_state(config, {...})` — manually fix a value.
- **Time travel**: re-invoke from an earlier `checkpoint_id` and show the result branching.
- Swap to `SqliteSaver` and show the total survives a kernel restart (store the DB file in the project folder; it's git-ignored).

**14 Human-in-the-loop with `interrupt`** — Before dividing, the `divide` node calls `interrupt({"question": "b is 0. Enter a new divisor:", ...})` when `b == 0`. Resume with `graph.invoke(Command(resume=5), config)`. Print `result["__interrupt__"]` to show the pause. Also show an approve/reject version (`Command(resume=True/False)` + `Command(goto=...)`). Teach the rules: needs a checkpointer + thread_id; the node re-runs from the top on resume (demonstrate with a `print` before the interrupt); don't wrap `interrupt()` in a bare `try/except`; keep multiple interrupts in a fixed order; pass JSON-serialisable values. Mention static breakpoints (`interrupt_before=[...]` at compile) as a debugging tool.

**15 Streaming** — Using the lesson 05 graph:
- `stream_mode="values"` — full state after each step.
- `stream_mode="updates"` — what each node changed.
- `stream_mode="custom"` — emit progress from inside a node with `from langgraph.config import get_stream_writer` (e.g. "multiplying 3 × 4…").
- Multiple modes at once: `stream_mode=["updates", "custom"]`.
- Mention `stream_mode="messages"` (LLM tokens) and say it's used in lesson 18. If the installed version provides `graph.stream_events(..., version="v3")`, add one short cell showing it and noting the docs now recommend it for UIs; skip it if not available.

**16 Subgraphs** — Build a small "arithmetic" graph (parse → route → compute) and use the compiled graph as a single node inside a bigger "calculator app" graph (validate input → arithmetic subgraph → format). Cover: shared state keys pass through automatically; when schemas differ, call the subgraph inside a node function and map keys. Show `draw_mermaid` with `xray=True`.

**17 Long-term memory with the store** — Memory that survives across threads: remember each user's preferred decimal places. `InMemoryStore` passed to `compile(store=...)`; nodes access it via `runtime.store` (`put`, `get`, `search` with a namespace like `("users", user_id)`). Contrast clearly with the checkpointer (per-thread vs across threads).

### Part C — Tools and the LLM (minimal LLM use)

**18 Tools and `ToolNode` (no LLM yet)** — Turn calculator operations into tools with `@tool` (docstring + type hints matter; print `add.name`, `add.description`, `add.args`). Call a tool directly with `add.invoke({"a": 2, "b": 3})`. Then run `ToolNode` **without an LLM** by hand-building the AI message an LLM would send:

```python
from langchain.messages import AIMessage
fake_ai = AIMessage(content="", tool_calls=[
    {"name": "add", "args": {"a": 2, "b": 3}, "id": "call_1", "type": "tool_call"},
    {"name": "multiply", "args": {"a": 4, "b": 5}, "id": "call_2", "type": "tool_call"},
])
print(ToolNode(tools).invoke({"messages": [fake_ai]}))
```

Explain `tool_calls`, `ToolMessage`, `tool_call_id`, and `tools_condition`. This lesson shows the whole agent machinery with zero API calls.

**19 [LLM] The agent loop with Gemini** — Use `get_llm()`. Keep calls few and short.
1. `llm_with_tools = llm.bind_tools(tools)`; one invoke on "What is 12.5 times 8?" and print `.tool_calls` (no execution yet).
2. Build the ReAct loop by hand: `MessagesState`, `call_model` node, `ToolNode(tools)`, `add_conditional_edges("model", tools_condition)`, edge `tools → model`. Run one multi-step question ("(3 + 5) × 12, then divide by 4") and `pretty_print()` every message so the learner sees reason → act → observe.
3. Add `InMemorySaver` + a thread so a follow-up ("now add 10 to that") works.
4. Stream with `stream_mode="messages"` to show tokens.
5. Same agent in 5 lines with `create_agent(model=llm, tools=tools, system_prompt=..., checkpointer=...)`; explain it builds the graph from steps 2–3 for you.
Total LLM calls in this lesson: aim for under 10.

**20 [LLM, optional] Capstone: calculator assistant** — Combine: tools, agent loop, SQLite checkpointer, `interrupt` before any division (approve/reject), custom streaming status lines, and a store remembering decimal-place preference. Provide a checklist the learner ticks off as each piece works. Also include a closing section with the **Functional API** (`from langgraph.func import entrypoint, task`) version of the simple non-LLM calculator from lesson 05, to show the same ideas without drawing a graph.

## 6. Supporting files

- **README.md**: one-paragraph intro, prerequisites (Python 3.10+), setup steps (venv, `pip install -r requirements.txt`, copy `env.example` to `.env`, `jupyter notebook`), a lesson table (number, title, concept, needs LLM yes/no), and troubleshooting (missing key, Vertex AI permission errors, `ImportError` from old tutorials using `create_react_agent`).
- **GLOSSARY.md**: alphabetical, every term from section 1, each with a one-line definition and the lesson that teaches it.
- **solutions/exercises_solutions.ipynb**: working answers to every "Try it", grouped by lesson.

## 7. Definition of done (verify before finishing)

1. Create a fresh virtualenv, install `requirements.txt`, and record the exact installed versions of `langgraph`, `langchain`, `langchain-core`, `langchain-google-genai` in the README.
2. Execute every non-LLM notebook top to bottom with **no** `GOOGLE_CLOUD_API_KEY` set:
   `jupyter nbconvert --to notebook --execute --inplace notebooks/0*.ipynb notebooks/1[0-8]*.ipynb`
   All must pass. Fix and re-run until they do.
3. If a key is available, execute lessons 00, 19 and 20 as well. If not, say so clearly in your final report and make sure those notebooks fail early with the friendly assertion message, not a stack trace deep in the code.
4. Notebooks are committed **with outputs**, so learners can read them without running.
5. Grep the repo for `create_react_agent`, `config_schema`, `draw_mermaid_png` and hard-coded keys; none should appear in code (a mention in the README's troubleshooting is fine).
6. Every lesson has all eight template parts from section 5.
7. Final report to the user: lesson list, versions used, anything that didn't run and why.

## 8. Reference docs (check these for current APIs)

- Overview & quickstart: https://docs.langchain.com/oss/python/langgraph/quickstart
- Graph API (state, reducers, Send, Command, schemas, context): https://docs.langchain.com/oss/python/langgraph/graph-api
- Persistence (checkpointers, threads, state history, store): https://docs.langchain.com/oss/python/langgraph/persistence
- Interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- Streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- Subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- Functional API: https://docs.langchain.com/oss/python/langgraph/functional-api
- LangGraph v1 migration (deprecations): https://docs.langchain.com/oss/python/migrate/langgraph-v1
- Google Gemini chat model: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai

If a URL has moved, search the docs site rather than guessing an API.
