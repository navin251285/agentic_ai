# Running and monitoring the Restock Agent

This guide covers how to start the app, check that it is healthy, and watch it while a demo is running.
See [README.md](README.md) for what the app does and the demo script.

## 1. Before the first run

You need either **Docker** (with Compose) or **Python 3.11+ and Node 20+**.

```bash
cp .env.example .env
```

Edit `.env`:

- `GOOGLE_CLOUD_API_KEY`: needed only for the Gemini brain. If you leave it empty, the app still runs and the rules
  brain makes every decision.
- `SIM_SEED`: set a number (for example `7`) to make rehearsals repeatable.
- Linux with Docker only: set `HOST_UID` and `HOST_GID` to the output of `id -u` and `id -g`, so that the CSV files
  the container writes belong to you.

## 2. Start the app

### Option A: Docker (recommended)

```bash
docker compose up --build        # first time, or after dependency changes
docker compose up                # later runs
docker compose up -d             # same, in the background
```

Open **http://localhost:5173**. The API is on http://localhost:8000.

The `web` service waits until the API passes its health check, so the dashboard comes up a few seconds after the API.

### Option B: Without Docker

Use two terminals:

```bash
# Terminal 1: API. Use exactly one worker, because all state is in memory.
cd api
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

```bash
# Terminal 2: dashboard
cd web
npm install
npm run dev                            # http://localhost:5173
```

### After it starts

- The simulation always starts **paused**. Press **1x** to start it.
- If you use Gemini, open the page about a minute before you present so that the warm-up call can finish. The brain
  switch shows "warming up" until it does.

## 3. Stop the app

| How you started it | How to stop it |
|---|---|
| `docker compose up` | `Ctrl+C` |
| `docker compose up -d` | `docker compose stop` |
| Without Docker | `Ctrl+C` in both terminals |

Each of these saves the current state. The next start continues from the same clock, stock levels, open orders and
countdowns, in the paused state.

`docker compose down` also keeps your data, because the data lives in `./api/data` on your disk.

## 4. Monitor the app

The examples below use port 8000. Without Docker, `/api` also works through the dashboard port
(`http://localhost:5173/api/...`). `jq` is optional; without it, pipe to `python -m json.tool` instead.

### Is it up?

```bash
curl http://localhost:8000/api/health          # {"status":"ok"}
docker compose ps                              # api shows "(healthy)"
```

### Live status in one line

```bash
watch -n 1 "curl -s localhost:8000/api/snapshot | jq -c '{shop_time, speed, saved_ago_s, counters, orders_on_the_way}'"
```

| Field | What to look for |
|---|---|
| `speed` | `0` means paused. |
| `saved_ago_s` | Should stay below about 3 while the app runs. If it keeps growing, saves are failing (see the logs). |
| `counters.missed_sales` | Should stay at or near 0 with the agent on and rush hour off. |

### Agent and Gemini budget

```bash
watch -n 1 "curl -s localhost:8000/api/snapshot | jq '.agent'"
```

| Field | Meaning |
|---|---|
| `mode`, `enabled` | Which brain is active, and whether the agent is on. |
| `llm_ready` | `true` after the first successful Gemini call (normally the warm-up). |
| `thinking` | A Gemini call is in progress. |
| `calls_last_60s` / `call_limit` | Calls in the last 60 real seconds. This never goes above 10. |
| `next_call_allowed_in_s` | Seconds until the next call is allowed (calls are at least 6 s apart). |
| `fallbacks` | How often the rules decided instead of Gemini (because of a timeout, an error, an exhausted budget or no key). |
| `last_latency_ms` | How long the last Gemini call took. |
| `pending_products` | Products waiting for Gemini to look at them. |

The dashboard shows the same information in the agent status chip and the budget meter. The meter turns amber at
8 calls and red at 10.

### Logs

```bash
docker compose logs -f api                     # Docker
# Without Docker, the logs print in the API's terminal.
```

Log lines to know:

| Log line | Meaning |
|---|---|
| `app.main: Loaded 10 products, run N` | Startup finished loading data. |
| `Gemini call #N (decision: milk, eggs): 5/10 in the last 60s` | One line per Gemini call, with the budget count at that moment. |
| `Gemini warm-up ok in N ms` | Gemini is ready. |
| `WARNING ... Gemini warm-up failed: ...` | Gemini is not ready yet. Later calls are still tried within the budget. |
| `WARNING ... Gemini fallback: <reason>` | The rules made this decision. Reasons include `timeout after 8s`, `no API key`, and API errors. |
| `No GOOGLE_CLOUD_API_KEY: gemini mode will fall back to rules` | The key is missing. Gemini mode still works, using the rules. |
| `WARNING ... Could not save <file> (will retry on next save)` | A file is locked, often because it is open in Excel. Close it; nothing is lost. |
| `WARNING ... products.csv is INVALID and was moved to ...` | A broken file was set aside, and the default scenario was loaded. |

To check the Gemini budget after a session:

```bash
docker compose logs api | grep "Gemini call #"
```

### Event stream and data files

Activity is written to `api/data/events.csv` as it happens:

```bash
tail -f api/data/events.csv                                  # macOS / Linux
Get-Content api/data/events.csv -Wait -Tail 20               # Windows PowerShell
grep -E "ORDER_PLACED|AGENT_FALLBACK|MISSED_SALE" api/data/events.csv | tail -20
```

`products.csv`, `orders.csv` and `runtime.json` are rewritten every 3 seconds. Each reset or scenario load starts a
new `run_id`, and earlier runs stay in `events.csv`.

To see the raw live stream the dashboard uses (one snapshot every 0.5 s):

```bash
curl -N http://localhost:8000/api/stream
```

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| `permission denied ... docker.sock` | On Linux, add yourself to the docker group with `sudo usermod -aG docker $USER`, then log out and back in. |
| Port 8000 is already in use | **Docker:** set `API_PORT=8010` in `.env` (the API is then at http://localhost:8010). **Without Docker:** run `uvicorn app.main:app --port 8010` and set `VITE_API_TARGET=http://localhost:8010` in `.env` before `npm run dev`. To see what holds the port: `lsof -i :8000`. |
| Port 5173 is already in use | **Without Docker:** `npm run dev -- --port 5180`. **Docker:** stop whatever uses 5173. |
| Dashboard says "Connecting to the shop…" or "Reconnecting…" | The API is down or restarting. Check `/api/health` and the API logs. The page reconnects by itself. |
| "saved Ns ago" keeps growing | Saving is failing; look for `Could not save` in the logs. On Linux with Docker, check `HOST_UID`/`HOST_GID`, and close any CSV open in Excel. |
| Gemini stays on "warming up" | Check the key in `.env` and look for `warm-up failed` in the logs. The demo keeps working on the rules. |
| Many `Agent · Fallback` lines in Gemini mode | Expected at 5x, because the budget runs out. Use Gemini at 1x or 0.5x. |
| Restore a clean demo | Press **Reset** (or load `normal_day` from the edit panel). To start over completely, stop the app and delete `products.csv`, `orders.csv`, `events.csv` and `runtime.json` from `api/data`. Do not delete `scenarios/`. |

Do not run `pytest -m live` while the demo is running. It makes a real Gemini call that the running app cannot
count toward its budget.
