# CLAUDE.md

Full spec is in BUILD_LANGGRAPH_TUTORIAL.md — read only the section you're told to.

## Ground rules

1. **Target LangGraph 1.x and LangChain 1.x.** Before writing code, check the current docs at https://docs.langchain.com/oss/python/langgraph/overview (and the pages linked in the spec) and confirm every import you use still exists. Do not use anything marked deprecated. In particular:
   - Use `from langchain.agents import create_agent` — **not** `langgraph.prebuilt.create_react_agent` (deprecated in v1).
   - Use `from langchain.messages import ...` for message classes and `from langchain.tools import tool` for tools.
   - Use `input_schema=` / `output_schema=` / `context_schema=` on `StateGraph` (not the old `input=` / `output=` / `config_schema=`).
2. **LLM use is minimal.** Only lessons marked **[LLM]** call Gemini. Every other lesson must run with no network and no key.
3. **Keep cells small.** One idea per code cell, 5–20 lines. Every code cell is preceded by a markdown cell explaining what it does and why.
4. **Show the graph.** In every lesson that builds a graph, print it with `print(graph.get_graph().draw_mermaid())` (text, works offline). Do **not** rely on `draw_mermaid_png()` (it calls a web service). Optionally also render with `IPython.display.Markdown` in a ```mermaid block.
5. **Print, don't assume.** After every `invoke`, print the result so the learner sees exactly what state came back.
6. **No hidden magic.** Don't introduce a helper until the lesson that teaches it. No shared utility code except `llm_setup.py`.
7. **Plain language.** Short sentences. Define each term the first time it appears and add it to `GLOSSARY.md`.
8. Never hard-code or commit API keys. `.env` goes in `.gitignore`.

## Lesson template

Each notebook follows this template:

1. **Title + one-sentence goal** ("By the end you can …").
2. **The idea in plain English** (3–6 sentences) + a real-world analogy.
3. **Picture**: a small mermaid diagram of what we're about to build.
4. **Code, step by step** (small cells, each with a markdown explanation above).
5. **What just happened** (bullet recap of the flow, referencing printed output).
6. **Common mistakes** (1–3, each with the error message the learner would see).
7. **Try it** (1–2 exercises; answers in `solutions/`).
8. **Key terms** introduced (links to `GLOSSARY.md`).
