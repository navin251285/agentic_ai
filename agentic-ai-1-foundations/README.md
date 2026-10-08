# Agentic AI 1: LLM foundations and the agent loop

A hands-on course for Python developers. It starts with how a language model behaves from the outside: tokens,
sampling, the context window and statelessness. It then covers calling a real model with streaming, cost
tracking and retries, getting validated structured output, and writing a tool-calling agent loop from scratch,
with no framework.

The running example is **Scout**, a research assistant that answers questions from a folder of local notes.

**Status: in progress.** 25 lessons are written (01–30, some numbers still to come). [SYLLABUS.md](SYLLABUS.md)
lists the full plan.

## What's here

| Path | Contents |
|---|---|
| [notebooks/](notebooks/) | The lessons. Open them in order. |
| [solutions/](solutions/) | Worked answers to the exercises, as notebooks and plain `.py` files (part 1: lessons 01–06, part 2: 07–18, part 3: 19–25, part 4: 26–30) |
| [data/llm_cassettes/](data/llm_cassettes/) | Recorded model responses, so every lesson runs **without an API key** |
| [data/recorded/](data/recorded/) | Saved results from earlier runs (tokenizer splits, streaming timings, token counts) that lessons read back |
| [data/scout_files/](data/scout_files/) | The notes Scout searches |
| [data/tiktoken_cache/](data/tiktoken_cache/) | Tokenizer files, so lesson 03 runs offline |
| [apps/](apps/) | Small scripts that lessons 06, 14 and 18 write and then run |
| [llm_replay.py](llm_replay.py) | Records and replays model calls (used by the notebooks) |
| [env.example](env.example) | Template for your own `.env`, if you want to make live calls |
| [GLOSSARY.md](GLOSSARY.md) | Every term the course uses, with the lesson that introduces it |

## Lessons

| # | Lesson | # | Lesson |
|---|---|---|---|
| 01 | What an agent is: a model in a loop | 17 | Choosing a model: size, price and pinning |
| 02 | Next-token prediction by hand | 18 | Checkpoint: a streaming CLI chatbot with cost |
| 03 | Tokens and tokenizers | 19 | Prompting that works |
| 04 | Sampling: temperature, top-p and top-k | 20 | Structured output: from "please" to JSON Schema |
| 05 | The context window | 21 | Validating with Pydantic and retrying |
| 06 | Checkpoint: a chat loop with a fake model | 22 | One tool call, end to end |
| 07 | Your first API call | 25 | Parallel tool calls |
| 08 | Roles, history and statelessness | 26 | The agent loop |
| 09 | Server-side conversation state | 27 | A tool registry: add tools without touching the loop |
| 11 | Streaming responses | 28 | Tool errors the model can recover from |
| 12 | Counting tokens and cost per turn | 29 | Designing good tools |
| 13 | Stop reasons and API errors | 30 | Stopping conditions: step limits, timeouts and cancel |
| 14 | Rate limits and retries | | |

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
