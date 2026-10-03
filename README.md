# Restock Agent Demo

A small corner shop on one screen. Customers buy items, so stock goes down. An agent watches the shelves and orders
from a simulated supplier, which delivers after a delay, so stock goes back up. The agent uses either fixed rules or
Gemini, and you can switch between them live.

The audience sees each product go **selling → danger zone → order placed (countdown) → restocked**.

- Backend: Python 3.11+, FastAPI, Pydantic v2. State lives in memory and is saved to CSV files. Live updates use SSE.
- Frontend: React 18, Vite, TypeScript, Zustand, Recharts and Tailwind.
- Gemini: Gemini 2.5 Flash-Lite on Vertex AI, called through LangChain. It never makes more than 10 calls per minute.

`CLAUDE.md` is the full spec.

## Setup

```bash
cp .env.example .env        # then edit .env
```

| Variable | Meaning |
|---|---|
| `SIM_SEED` | Fixed random seed. The same seed and the same clicks give the same demo. Leave it empty for random. |
| `DEFAULT_SCENARIO` | Scenario loaded when `products.csv` is missing (`normal_day`). |
| `AGENT_MODE` | Brain at startup: `rules` or `gemini`. |
| `GOOGLE_CLOUD_API_KEY` | Vertex AI API key. Without it, Gemini mode still works but every check falls back to the rules. |
| `LLM_MAX_CALLS_PER_MIN` / `LLM_MIN_GAP_S` | The Gemini budget (10 calls, at least 6 s apart). You can lower it but not raise it. |
| `HOST_UID` / `HOST_GID` | Linux with Docker only: set them to `id -u` / `id -g` so the CSV files the container writes belong to you. |

The real `.env` is git-ignored. The key is never logged or sent to the browser.

## Run

For step-by-step start, stop, health checks, logs and troubleshooting, see [RUNNING.md](RUNNING.md). On Vertex AI
Workbench, follow RUNNING.md: the dashboard opens through JupyterLab's proxy instead of `localhost:5173`.

### Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:5173 (the API runs on http://localhost:8000). `./api/data` is mounted into the container, so
the live CSV files are on your disk while the demo runs. `Ctrl+C` or `docker compose stop` saves the state, and the
next `up` continues from where it stopped.

### Without Docker

```bash
# Terminal 1: API (exactly one worker, because the state is in memory)
cd api
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                    # runtime + test tools
uvicorn app.main:app --port 8000

# Terminal 2: web
cd web
npm install
npm run dev                                            # http://localhost:5173
```

### Headless runs

```bash
cd api
python -m app.run_sim --speed 5 --duration 600 --fast          # prints events and a summary, no waiting
python -m app.run_sim --fast --no-agent --rush-hour --quiet    # what happens without the agent
python -m app.run_sim --fast --order milk:20@30                # a manual order at sim_s 30
python -m app.run_sim --mode gemini --duration 120             # real time, real Gemini calls
```

`run_sim` keeps its state in memory and never writes the live CSV files.

### Checks

```bash
cd api && pytest && ruff check .            # backend (pytest -m live makes ONE real Gemini call)
cd web && npm test && npm run lint && npm run build
npm run gen:types                            # regenerate src/api/types.ts while the API is running
```

Do not run `pytest -m live` while the demo is running. It is a separate process, so the demo's rate limiter cannot
count its call.

## How it works

- **Time.** Everything runs in sim seconds (`sim_s`). At 1x, one sim second is one real second; at 5x, five pass per
  real second; when paused, nothing moves. The shop clock is for show only: 1 sim second = 5 shop minutes, and each day
  starts at 08:00. The app always starts paused, and Play resumes the last speed.
- **Agent.** Every `agent_interval_s` (5 s by default) the agent checks every product. With the rules brain, a
  product at or below its reorder mark with nothing on order gets refilled to max. With the Gemini brain, one call
  covers every product that just entered the watch zone or the danger zone. Gemini may order early or order less.
  Guardrails clamp every order, and no shelf is ever left to run empty. On a timeout, an error or no budget, the rules
  take over and the feed shows `Agent · Fallback`.
- **Curveball.** One press: pick a preset (heatwave or cricket final pack the shop; supplier strike stops the
  main supplier) or type any news. The Rules brain can't read news, so a curveball switches the brain to
  Gemini. Gemini reads it, re-plans every shelf in one call, orders before the sales figures catch up, and can switch to a faster
  **backup supplier** (₹2 extra per unit). The **Agent plan** card shows its reading of the situation and each step.
- **Shadow shop.** A second copy of the shop serves exactly the same customers, but is run by the Rules. The
  **Agent vs Rules** scoreboard compares missed sales, lost profit (₹15 per missed sale) and backup fees. With the
  Rules brain both shops score the same; any gap comes from the agent's decisions.
- **Screen.** React only displays the snapshot that the API sends on every tick (0.5 s). The snapshot already
  contains every state, badge, countdown and "saved ago" value.

## Data files (`api/data`)

| File | Contents |
|---|---|
| `products.csv` | Current products. Rewritten on save (every 3 s and on edit). You can edit it while the app is stopped. |
| `orders.csv` | Every order and its status. |
| `events.csv` | Append-only log of every sale, order, delivery and edit, kept across runs (`run_id`). |
| `runtime.json` | Clock, speed, settings, counters and next ids, so a restart continues where it left off. |
| `scenarios/*.csv` | `normal_day`, `rush_hour`, `low_stock_start`. Reset and scenario loads read from these files. |

If `products.csv` is broken, the app renames it to `products.csv.bad-<timestamp>` and loads the default scenario.
If a file is locked (for example, open in Excel), the app logs a warning and retries on the next save.

## Demo script (about 6 minutes, about 15 Gemini calls)

Before you go live: open the app one minute early so the Gemini warm-up finishes, and rehearse with a fixed `SIM_SEED`.

1. **(0:00)** Start paused, with the rules brain and `normal_day`. Spend 20 s explaining the screen, then press **1x**.
2. **(0:20)** Watch Milk. It crosses its mark in under a minute, enters the danger zone, gets an order, counts down
   and is restocked (about 60 s lead time). Point at the sawtooth in the stock chart.
3. **(1:45)** Show the shop without the agent: Agent **off**, Rush hour **on**, then **5x** for about 20 real seconds.
   Expect about 5 empty shelves and 20+ missed sales. Then Agent **on**, Rush hour **off**, keep 5x for about 15 s
   to recover, and go back to **1x**.
4. **(2:45)** Switch the brain to **Gemini** (it is already warmed up). Point at the budget meter and the
   `Agent · Gemini` reasons in the feed.
5. **(3:15)** Turn Rush hour **on**. Gemini re-checks the watch-zone items, orders some of them early and says why.
   You can also turn Supplier delay on and show it ordering earlier again.
6. **(4:15)** Prove it's an agent. Turn Rush hour off and press one curveball (**Cricket final** shows the
   clearest win; **Supplier strike** shows the backup supplier), or take one from the audience. Point at the **Agent plan** card: Gemini explains how it reads the news and orders from the
   backup supplier. Rules can't do this: their shadow shop's line drops on the stock chart and the
   **Agent vs Rules** scoreboard swings to the agent. Give it 1–2 minutes at 1x: the gap opens once the rules
   shop starts running out.
7. **(5:30)** Close with the scoreboard, the activity feed and the CSV files on disk.

Keep Gemini mode at 1x or 0.5x. Use 5x only with the rules brain: at 5x the budget runs out and the rules make most
decisions.

## Swapping storage (e.g. Postgres)

All file access is in `api/app/repositories/csv_repo.py`. Services see only the `InventoryRepository` interface in
`api/app/repositories/base.py`:

```
load() · save_products() · save_orders() · append_event() · read_events(run_id)
save_runtime() · load_runtime() · load_scenario(name) · list_scenarios()
```

To use another store:

1. Write `PostgresInventoryRepository(InventoryRepository)` in `api/app/repositories/`. Put products, orders and
   runtime in tables, and make `append_event` a plain `INSERT`. Keep the return contract: return `False` on a failed
   write instead of raising, so the simulation keeps running and retries on the next save.
2. Return it from `build_repository(settings)` in `api/app/main.py`, chosen by a new setting such as `STORAGE=postgres`.
3. Run the backend tests. `InMemoryInventoryRepository` (`memory_repo.py`) is a second, minimal implementation you
   can use as a reference.

Nothing else changes: the simulation, API and UI never touch storage directly.
