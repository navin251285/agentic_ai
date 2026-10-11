# Scout v3.0.0: design note for track 2 (memory and RAG)
Date 2026-10-09 · package `apps/60/scout` · model `gemini-3.5-flash-lite` (thinking MINIMAL, max 300 output tokens)

## What Scout is
- One agent loop (`loop.py`, unchanged since v2) with these tools: `search_notes`, `calculator`, `write_file`, `days_between`.
- Per task, a guard allows only listed tools, marks note text as untrusted, and sends every write to a person (fail closed). Every step is traced with a run id; budgets per run and per day.

## Contract track 2 must keep
- `run_scout(question, model, tools, guard, tracer, budget)` returns `answer, stop, steps, errors, retries, denied, cost_usd`; `run_tool` never raises; tools are a dict plus `SCHEMAS`.
- `apps/60/tests` (15 tests) pass unchanged; the 12-case golden set stays at or above 90%.

## Measured baseline (keep or beat)
- Eval: 12/12 on the real model; cost per run p50 $0.000238, max $0.000461; model seconds per run p50 1.22, max 1.72.
- Lesson 55 load test (replayed): 50 conversations at once, all answered, under a rate limiter.

## Limits and what track 2 does about them
| Limit | Evidence (this notebook) | Track 2 |
|---|---|---|
| Forgets between runs: each run starts from one message | lesson 60 R4: without history the answer lacked Phobos (20 input tokens); with it, it named Phobos (56) | session memory: keep and resend the conversation per user |
| Long history: a 400 over the window, and trimming forgets the oldest facts | lesson 60 R5: dropped 4 messages, Phobos gone | summaries and long-term memory instead of dropping |
| Search is a substring match over 6 notes in a Python list | lesson 60 R9: hits {'moons': 1, 'number of moons': 0, 'satellites of Mars': 0, 'length of a Martian day': 0}; the eval passed because Gemini searched broad words (6 of 10 queries were 'Mars') | retrieval (RAG): chunking, embeddings, a vector store, retrieval evals |
| Retrieved text is untrusted | lesson 55's attacks; `guard.UNTRUSTED` | every new retriever goes in `UNTRUSTED`; memory writes need the same approval as files |

## Rules for the next change
- A new ability is a new tool plus a grant in `guard.py`; `loop.py` changes only with a design note entry.
- Add golden cases for memory and retrieval before building them, and keep this note's numbers as the floor.
