# LangGraph Calculator Tutorial

A beginner course that teaches every core idea in [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview),
one idea per notebook. The running example is a calculator that grows lesson by lesson: it starts by adding two
numbers, then picks an operation, keeps a history, loops, remembers across runs, asks a human before dividing by zero,
and finally lets an LLM pick the tools. Lessons 01–18 run offline with no API key. Only lessons 19 and 20 (and an
optional test in 00) call Gemini on Vertex AI.

## Prerequisites

- Python 3.10 or newer
- Basic Python: functions, dicts and `if` statements
- For lessons 19–20 only: a Google Cloud API key with Vertex AI access

## Setup

```bash
cd langgraph-calculator-tutorial
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Register the venv as a Jupyter kernel so notebooks can find the packages
python -m ipykernel install --user --name langgraph-tutorial --display-name "Python (langgraph-tutorial)"

# Only needed for the LLM lessons: add your key
cp .env.example .env    # then edit .env and paste your key

jupyter notebook
```

Open `notebooks/00_setup_and_check.ipynb` first and choose the **Python (langgraph-tutorial)** kernel. If you use
JupyterLab (for example on Vertex AI Workbench), open the folder there and pick the same kernel.

## Lessons

| # | Notebook | Concept | Needs LLM |
|---|---|---|---|
| 00 | [Setup and check](notebooks/00_setup_and_check.ipynb) | Install, kernel, `.env`, optional LLM test | Optional |
| 01 | [What is a graph?](notebooks/01_what_is_a_graph.ipynb) | Nodes, edges, state, and why LangGraph | No |
| 02 | [State](notebooks/02_state.ipynb) | `TypedDict` state (and `dataclass` / Pydantic) | No |
| 03 | [Nodes](notebooks/03_nodes.ipynb) | A node is a function returning a partial update | No |
| 04 | [Edges, START, END, compile, invoke](notebooks/04_edges_start_end_compile_invoke.ipynb) | Your first runnable graph | No |
| 05 | [Conditional edges](notebooks/05_conditional_edges.ipynb) | Routing to one node or another | No |
| 06 | [Reducers](notebooks/06_reducers.ipynb) | How updates are merged (`operator.add`, custom) | No |
| 07 | [Loops and the recursion limit](notebooks/07_loops_and_recursion_limit.ipynb) | Cycles and `GraphRecursionError` | No |
| 08 | [Parallel branches](notebooks/08_parallel_branches.ipynb) | Fan-out / fan-in and supersteps | No |
| 09 | [Map-reduce with `Send`](notebooks/09_map_reduce_with_send.ipynb) | Run a node once per item | No |
| 10 | [`Command`](notebooks/10_command.ipynb) | Update state and route from inside a node | No |
| 11 | [Input, output and private schemas](notebooks/11_input_output_private_schemas.ipynb) | `input_schema` / `output_schema` | No |
| 12 | [Runtime context](notebooks/12_runtime_context.ipynb) | `context_schema` and `Runtime` | No |
| 13 | [Checkpointers and threads](notebooks/13_checkpointers_and_threads.ipynb) | Short-term memory, history, time travel | No |
| 14 | [Human-in-the-loop](notebooks/14_human_in_the_loop_interrupt.ipynb) | `interrupt` and `Command(resume=...)` | No |
| 15 | [Streaming](notebooks/15_streaming.ipynb) | `values`, `updates`, `custom` stream modes | No |
| 16 | [Subgraphs](notebooks/16_subgraphs.ipynb) | A compiled graph used as a node | No |
| 17 | [Long-term memory](notebooks/17_long_term_memory_store.ipynb) | The store, shared across threads | No |
| 18 | [Tools and `ToolNode`](notebooks/18_tools_and_toolnode.ipynb) | Tool calls without an LLM | No |
| 19 | [The agent loop with Gemini](notebooks/19_agent_loop_with_gemini.ipynb) | `bind_tools`, ReAct loop, `create_agent` | Yes |
| 20 | Capstone: calculator assistant *(not written yet)* | Everything together + Functional API | Yes (optional) |

Answers to every "Try it" exercise are in [solutions/exercises_solutions.ipynb](solutions/exercises_solutions.ipynb).
Every term is defined in [GLOSSARY.md](GLOSSARY.md).

## Versions used

Built and tested with Python 3.12 and the versions below. These are also exactly what a fresh virtualenv installs
from `requirements.txt` (checked on 2026-10-04). Lessons 00–18 ran top to bottom in that fresh environment with no
API key; lesson 19 ran with a key.

| Package | Version |
|---|---|
| langgraph | 1.2.12 |
| langchain | 1.4.3 |
| langchain-core | 1.6.6 |
| langchain-google-genai | 4.4.0 |
| langgraph-checkpoint-sqlite | 3.1.1 |

## Troubleshooting

- **`AssertionError: GOOGLE_CLOUD_API_KEY is not set`**: you ran an LLM lesson without a key. Create `.env` from
  `.env.example` and restart the kernel. Lessons 01–18 don't need a key.
- **`ModuleNotFoundError: No module named 'langgraph'`**: the notebook is using the wrong kernel. Pick
  **Python (langgraph-tutorial)** from the kernel menu.
- **`403 PERMISSION_DENIED` or "Vertex AI API has not been used in project"**: your key's project doesn't have the
  Vertex AI API enabled, or the key isn't allowed to call it. Enable the API in the Google Cloud console and check the
  key's API restrictions.
- **`ImportError` for `create_react_agent`** (from older tutorials): it is deprecated in LangGraph 1.x. Use
  `from langchain.agents import create_agent` instead, as lesson 19 shows.

## Secrets

Never commit `.env` or any key. `.env` is in `.gitignore`.
