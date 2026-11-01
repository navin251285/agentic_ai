# Agentic AI with LangGraph (15 hours)

The LangGraph version of the agentic AI course: 38 lessons in six tracks, each lesson a notebook with a flowchart of
the graph it builds.

| Track | Folder | Lessons |
|---|---|---|
| 1 Foundations | `notebooks/langraph_version/01_foundations` | 01-04 |
| 2 Single agent | `notebooks/langraph_version/02_single_agent` | 05-14 |
| 3 Design patterns | `notebooks/langraph_version/03_design_patterns` | 15-18 |
| 4 Agents and protocols (discovery, registry, MCP, A2A) | `notebooks/langraph_version/04_agents_and_protocols` | 19-28 |
| 5 Multi-agent | `notebooks/langraph_version/05_multi_agent` | 29-31 |
| 6 Production | `notebooks/langraph_version/06_production` | 32-38 |

Each track folder starts with an overview notebook (`00_overview.ipynb`).

## Run it

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and set `TUT_LLM_MODEL` to a model id you have access to. Add `GOOGLE_CLOUD_API_KEY`
   only if you want to record new model answers.
3. Open a notebook and run it top to bottom. The model answers are recorded once in `notebooks/langraph_version/data/llm_cassettes`,
   so the lessons replay offline with no key.

Flowcharts use the public Mermaid service (mermaid.ink). Without internet access the notebook prints the same flowchart as text.

No keys, `.env` files or personal data are stored in this folder. The example data is fictional.
