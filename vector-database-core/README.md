# Vector databases: foundations to enterprise

A hands-on course that builds vector search from scratch and then moves onto a real vector database
(Qdrant). Every lesson is one Jupyter notebook that works with the same small recipe dataset.

**Status: in progress.** Lessons 01–18 are written. [SYLLABUS.md](SYLLABUS.md) lists the full plan.

## What's here

| Path | Contents |
|---|---|
| [notebooks/](notebooks/) | The lessons, `01_…` to `18_…`. Open them in order. |
| [solutions/](solutions/) | Worked answers to the exercises (part 1: lessons 01–06, part 2: 07–15, part 3: 16 onward), as notebooks and plain `.py` files |
| [data/](data/) | Recipe datasets (`recipes_50.csv`, `recipes_2000.csv`), saved embeddings (`.npz`), evaluation labels (`.json`) and recorded server results for lessons 13–14 |
| [infra/compose/](infra/compose/) | Docker Compose file for an optional local Qdrant server (lessons 13–14) |
| [GLOSSARY.md](GLOSSARY.md) | Every term the course uses, with the lesson that introduces it |

## Lessons

| # | Lesson | # | Lesson |
|---|---|---|---|
| 01 | Why keyword search misses meaning | 10 | Query: top-k results and scores |
| 02 | A vector is just a list of numbers | 11 | Filter by metadata |
| 03 | Measuring closeness: distance, dot product and cosine | 12 | Update, upsert and delete safely |
| 04 | Nearest-neighbour search in ten lines | 13 | In-memory, on-disk and server modes |
| 05 | Embeddings: turning text into vectors | 14 | Load a dataset in batches |
| 06 | Checkpoint: a recipe search engine with NumPy | 15 | Checkpoint: a filtered recipe finder |
| 07 | What a vector database adds to NumPy | 16 | Measuring search quality |
| 08 | Create a collection: size and distance | 17 | Chunking long text |
| 09 | Store points: ids, vectors and payloads | 18 | Choosing an embedding model |

## Getting started

You need Python 3.12 or newer.

```bash
git clone https://github.com/navin251285/agentic_ai.git
cd agentic_ai/vector-database-core
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/      # or open the folder in VS Code
```

Run the notebooks from inside `notebooks/`, because they read files with relative paths like `../data/recipes_50.csv`.

- **No API key is needed** for lessons 01–18. Embedding models download from Hugging Face the first time and then
  run locally on the CPU.
- **Each lesson runs on its own.** Files that an earlier lesson creates (embeddings, evaluation labels) are
  already included in `data/`, so you can open any lesson without running the ones before it.
- **Docker is optional.** Lessons 13 and 14 compare an embedded database with a Qdrant server. If a server is
  running on port 6333 they use it. If not, they show the results recorded in `data/recorded/`. To start a server:
  `docker compose -f infra/compose/qdrant-single.yml up -d`
- `requirements.txt` covers the whole planned course. Lessons 01–18 only need `numpy`, `pandas`, `matplotlib`,
  `qdrant-client`, `qdrant-edge-py`, `sentence-transformers`, `ranx` and `ipykernel`.
- While they run, the lessons write local databases to `data/cache/`. You can delete that folder at any time.
