# Agentic AI 1: LLM foundations and the agent loop

A hands-on course for Python developers. It starts with how a language model behaves from the outside: tokens,
sampling, the context window and statelessness. It then covers calling a real model with streaming, cost
tracking and retries, getting validated structured output, and writing a tool-calling agent loop from scratch,
with no framework. Later parts tune that loop (context, caching, batching), test and evaluate it, make it safe,
and run it in production.

The running example is **Scout**, a research assistant that answers questions from a folder of local notes.

All 60 lessons are written. [SYLLABUS.md](SYLLABUS.md) has the full plan, shorter paths (Essentials, Professional)
and a split into Basic (01–25), Intermediate (26–45) and Advanced (46–60) courses.

## What's here

| Path | Contents |
|---|---|
| [notebooks/](notebooks/) | The lessons. Open them in order. |
| [solutions/](solutions/) | Worked answers to the exercises, as notebooks and plain `.py` files (part 1: lessons 01–06, part 2: 07–18, part 3: 19–25, part 4: 26–35, part 5: 36–45, part 6: 46–55, part 7: 56–60) |
| [data/llm_cassettes/](data/llm_cassettes/) | Recorded model responses, so every lesson runs **without an API key** |
| [data/recorded/](data/recorded/) | Saved results from earlier runs (tokenizer splits, streaming timings, token counts) that lessons read back |
| [data/scout_files/](data/scout_files/) | The notes Scout searches (the `scout_files_NN` folders are per-lesson copies) |
| [data/](data/) (other) | Inputs and saved outputs that later lessons read: traces, audit logs, batch requests |
| [data/tiktoken_cache/](data/tiktoken_cache/) | Tokenizer files, so lesson 03 runs offline |
| [apps/](apps/) | Code the lessons write to disk and run: small scripts (06, 14, 15, 18), the tested Scout package (46, 47, 55) and the capstone (60) |
| [llm_replay.py](llm_replay.py) | Records and replays model calls (used by the notebooks) |
| [env.example](env.example) | Template for your own `.env`, if you want to make live calls |
| [GLOSSARY.md](GLOSSARY.md) | Every term the course uses, with the lesson that introduces it |
| [projects/](projects/) | Portfolio project ideas for the Basic, Intermediate and Advanced courses (Markdown, PDF and JSON) |
| [interview/](interview/) | Interview questions linked to the lessons they draw on |

## Lessons

| # | Lesson | # | Lesson |
|---|---|---|---|
| 01 | What an agent is: a model in a loop | 31 | Context engineering basics |
| 02 | Next-token prediction by hand | 32 | Compaction: when history outgrows the window |
| 03 | Tokens and tokenizers | 33 | Workflows: prompt chaining and routing |
| 04 | Sampling: temperature, top-p and top-k | 34 | Workflows: parallelisation, and workflow vs agent |
| 05 | The context window | 35 | Checkpoint: Scout, a research assistant in ~150 lines |
| 06 | Checkpoint: a chat loop with a fake model | 36 | Streaming inside the agent loop |
| 07 | Your first API call | 37 | A provider-neutral adapter |
| 08 | Roles, history and statelessness | 38 | Running many conversations at once |
| 09 | Server-side conversation state | 39 | Retries without double side effects; resumable runs |
| 10 | Three vendors, three message formats | 40 | Reasoning effort and thinking across tool turns |
| 11 | Streaming responses | 41 | Prompt caching |
| 12 | Counting tokens and cost per turn | 42 | Batch processing |
| 13 | Stop reasons and API errors | 43 | Images and PDFs as input |
| 14 | Rate limits and retries | 44 | Who runs the loop: SDK helpers and vendor-run tools |
| 15 | Provider failure drill | 45 | Checkpoint: benchmark and tune Scout |
| 16 | Running a model locally: Ollama and LM Studio | 46 | Unit-testing the loop with a fake model |
| 17 | Choosing a model: size, price and pinning | 47 | Recorded integration tests |
| 18 | Checkpoint: a streaming CLI chatbot with cost | 48 | Your first evals |
| 19 | Prompting that works | 49 | Logging and tracing an agent run |
| 20 | Structured output: from "please" to JSON Schema | 50 | API keys and data handling |
| 21 | Validating with Pydantic and retrying | 51 | Prompt injection through tools |
| 22 | One tool call, end to end | 52 | Human approval for side-effecting tools |
| 23 | Tool calls on the wire, three ways | 53 | Model versions, retirement and migration |
| 24 | Controlling tools: tool_choice and strict schemas | 54 | Cost controls in production |
| 25 | Parallel tool calls | 55 | Checkpoint: production-ready Scout |
| 26 | The agent loop | 56 | What changes at organisation scale |
| 27 | A tool registry: add tools without touching the loop | 57 | Provider outage and fallback |
| 28 | Tool errors the model can recover from | 58 | Case studies: agents in production |
| 29 | Designing good tools | 59 | The frontier: what changed in the last year |
| 30 | Stopping conditions: step limits, timeouts and cancel | 60 | Capstone: Scout, track 1 complete |

## Getting started

You need Python 3.12 or newer.

```bash
git clone https://github.com/navin251285/agentic_ai.git
cd agentic_ai/agentic-ai-1-foundations
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/      # or open the folder in VS Code
```

Run the notebooks from inside `notebooks/`, because they use relative paths like `../data/` and import
`llm_replay` from the folder above.

- **No API key is needed.** Lessons that call Gemini replay the recorded responses in `data/llm_cassettes/`.
  The recordings were saved with API keys and auth headers removed.
- **To make real calls with your own key:** `cp env.example .env`, put your Gemini on Vertex AI key in
  `GOOGLE_CLOUD_API_KEY`, and set `TUT_LLM_MODE=live` before starting Jupyter. Never commit your `.env`.
- Run each notebook top to bottom. Recorded calls are replayed in the order they were made.
