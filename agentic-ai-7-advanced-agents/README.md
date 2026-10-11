# Agentic AI 7: Computer-use, coding and long-horizon agents

**Status: approved (syllabus v1, 2026-10-11) · in progress.** Lessons 00–13 are written. Lessons 14–21 (the rest of
the Basic course) and the Intermediate and Advanced lessons are still to come. The full plan is in
[SYLLABUS.md](SYLLABUS.md).

## Why this track is needed

Early agents answered questions. Newer agents work on their own for many steps: they click through a website, read
and edit a code repository, run the tests and keep going until the job is done. Most of what goes wrong is not the
model's wording. It is the loop around it: the agent misreads a screen, edits the wrong file, forgets what it has
already tried, or runs up a large bill. This track teaches how to build those loops so they work unattended, and
how to tell when they don't.

## Where it fits

Each track builds on the one before it:

```
chat ──► tool calls ──► one agent loop ──► protocols ──► multi-agent ──► production
 (1)         (1)            (1)              (4)           (5)            (6)
                                         │
                                         └──► THIS TRACK (7): agents that use a computer and a codebase,
                                              over many steps, with checkpoints, budgets and checks
```

- **Track 1, Foundations:** the model, tokens and a tool-calling loop written from scratch. This track assumes it.
- **Tracks 2–6:** this track assumes them, or an equivalent ability to write a tool-calling loop, use MCP, and run
  evals, tracing and guardrails. The syllabus names protocols (track 4), multi-agent systems (track 5) and
  production (track 6).
- **This track:** the agent works on a screen or a repo, not only through tool calls. It needs to see, act and check
  the result again and again.

## A basic example

The running example is **Pocket Tracker**: a small issue tracker (FastAPI + SQLite + pytest) with a few seeded bugs.
It runs locally and offline, so every lesson is repeatable.

Here is one bug from the course. Searching for `Search` in the tracker returns nothing, but searching for `search`
works. The loop an agent needs to fix it:

1. **Observe:** read the failing test, or the page, to see the symptom.
2. **Decide:** find the search code and form a guess about the cause.
3. **Act:** change the code, e.g. make the comparison case-insensitive.
4. **Verify:** run the tests again. Stop only when they pass, or when a step or cost limit is reached.

Each step is a lesson in this track. The agent acts through tools, and a checker decides if the work is done.

## What you will need

- Python 3.12, git, pytest and basic Docker (for the sandbox lessons).
- No API key is needed for the recorded lessons. The recordings are replayed. To make live calls, copy
  `env.example` to `.env` and add your own key. Never commit your `.env`.

## Running the lessons

```bash
cd agentic-ai-7-advanced-agents
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/
```

Run the notebooks from inside `notebooks/`, because they use relative paths such as `../data/`.

## Layout

| Path | Contents |
|---|---|
| [notebooks/](notebooks/) | The lessons, in order (`00_…` to `13_…` so far) |
| [solutions/](solutions/) | Worked answers to the exercises |
| [apps/](apps/) | The Pocket Tracker app and the agent code the lessons build |
| [data/](data/) | Recorded model responses (so lessons run without a key) and sample files |
| [src/](src/) | Plain `.py` versions of the lessons |
| [GLOSSARY.md](GLOSSARY.md) | Every term the course uses, with the lesson that introduces it |
| [SYLLABUS.md](SYLLABUS.md) | The full plan, paths (Essentials, Professional, Complete) and the Basic, Intermediate and Advanced split |
