# Running and monitoring the Restock Agent on Vertex AI Workbench

The app runs on a Vertex AI Workbench instance. You start and monitor it from **JupyterLab terminals** and open the
dashboard in **your own browser** through JupyterLab's proxy, with the same Google sign-in you use for JupyterLab. You
don't need an external IP, a firewall rule or an SSH tunnel.

See [README.md](README.md) for what the app does and the demo script.

## 1. One-time setup

Open a terminal in JupyterLab (**File → New → Terminal**). All commands in this guide run there.

`.env` in the project folder holds only your Vertex AI key, `GOOGLE_CLOUD_API_KEY`. The Gemini brain needs it;
without it the rules brain makes every decision. Leave `.env` as it is. Every other setting in this guide is typed on
the command line when you start the app:

| Setting | When to use it |
|---|---|
| `VITE_BASE=/proxy/absolute/5173/` | **Always on Workbench.** It serves the dashboard under JupyterLab's proxy. |
| `SIM_SEED=7` | Optional, for the API: the same seed and the same clicks give the same demo, which helps rehearsals. |
| `HOST_UID=$(id -u) HOST_GID=$(id -g)` | Docker only: the CSV files the container writes then belong to you. |

Then install the dependencies, unless `api/.venv` and `web/node_modules` already exist. Running `python -m venv .venv`
again on an existing venv rebuilds it, and fails if another user created it.

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd ../web
npm install
```

### Your dashboard address

The dashboard is at your JupyterLab address with `/lab...` replaced by `/proxy/absolute/5173/`:

```
JupyterLab:  https://<id>-dot-<region>.notebooks.googleusercontent.com/lab/tree/...
Dashboard:   https://<id>-dot-<region>.notebooks.googleusercontent.com/proxy/absolute/5173/
```

To print the address from a terminal:

```bash
echo "https://$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/proxy-url)/proxy/absolute/5173/"
```

Keep the **trailing slash**: without it the page returns 404. Bookmark the address; it stays the same as long as the
instance exists.

## 2. Start the app

### First, check whether it is already running

Run **only one API at a time.** Every API instance saves to the same `api/data` files, so two of them overwrite each
other's data.

```bash
curl -s http://localhost:8000/api/health       # {"status":"ok"} means an API is already running
docker ps --filter name=api                    # shows it if it is the Docker container
ps -eo user,pid,args | grep -E "uvicorn|vite" | grep -v grep
```

If an API is already running, either use it and start only the dashboard, or stop it first (see section 3).

### Option A: Two terminals (recommended)

```bash
# Terminal 1: API. Use exactly one worker, because all state is in memory.
cd /home/jupyter/agentic_ai_tutorial/autonomous_agent/api
source .venv/bin/activate
uvicorn app.main:app --port 8000              # rehearsal: SIM_SEED=7 uvicorn app.main:app --port 8000
```

```bash
# Terminal 2: dashboard
cd /home/jupyter/agentic_ai_tutorial/autonomous_agent/web
VITE_BASE=/proxy/absolute/5173/ npm run dev
```

Wait for `Uvicorn running on http://127.0.0.1:8000` in terminal 1 and `Local: http://localhost:5173/proxy/absolute/5173/`
in terminal 2, then open your [dashboard address](#your-dashboard-address).

### Option B: Docker

```bash
cd /home/jupyter/agentic_ai_tutorial/autonomous_agent
VITE_BASE=/proxy/absolute/5173/ HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up --build -d
```

Leave out `--build` on later runs unless dependencies changed. The dashboard address is the same as with Option A.

### After it starts

- The simulation always starts **paused**. Press **1x** to start it.
- If you use Gemini, open the page about a minute before you present so that the warm-up call can finish. The brain
  switch shows "warming up" until it does.
- Workbench can shut down idle instances. If the instance stopped, start it from the Workbench console, then start the
  app again. It continues where it left off.

## 3. Stop the app

| How you started it | How to stop it |
|---|---|
| Two terminals | `Ctrl+C` in both terminals |
| Docker | `docker compose stop` |

Each of these saves the current state. The next start continues from the same clock, stock levels, open orders and
countdowns, in the paused state.

`docker compose down` also keeps your data, because the data lives in `api/data` on the instance's disk.

To make sure nothing is left running:

```bash
ps -eo user,pid,args | grep -E "uvicorn|vite" | grep -v grep     # should print nothing
docker ps --filter name=api                                       # should list no containers
```

## 4. Monitor the app

Run these in a JupyterLab terminal; `localhost` there is the instance. From your own browser, the same API answers at
your dashboard address plus `api/...`, for example `.../proxy/absolute/5173/api/snapshot`.
`jq` is installed on the instance.

### Is it up?

```bash
curl http://localhost:8000/api/health          # {"status":"ok"}
docker compose ps                              # Docker only: api shows "(healthy)"
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

### Agent vs Rules scoreboard and curveballs

```bash
watch -n 1 "curl -s localhost:8000/api/snapshot | jq -c '{scoreboard, curveballs: [.curveballs[] | {title, seconds_left}], plan: .agent.plan.trigger}'"
```

`scoreboard.agent_ahead_by` is in ₹ (positive: the agent is ahead of the rules shop).

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

With two terminals, the API logs print in terminal 1. With Docker:

```bash
docker compose logs -f api
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
| `WARNING ... Could not save <file> (will retry on next save)` | A file could not be written (usually permissions). Nothing is lost; it retries. |
| `WARNING ... products.csv is INVALID and was moved to ...` | A broken file was set aside, and the default scenario was loaded. |

To check the Gemini budget after a session, copy terminal 1's output to a file, or with Docker:

```bash
docker compose logs api | grep "Gemini call #"
```

### Event stream and data files

Activity is written to `api/data/events.csv` as it happens. You can also open the CSV files in JupyterLab's file
browser.

```bash
cd /home/jupyter/agentic_ai_tutorial/autonomous_agent
tail -f api/data/events.csv
grep -E "ORDER_PLACED|AGENT_FALLBACK|MISSED_SALE" api/data/events.csv | tail -20
```

`products.csv`, `orders.csv` and `runtime.json` are rewritten every 3 seconds. Each reset or scenario load starts a
new `run_id`, and earlier runs stay in `events.csv`.

To see the raw live stream the dashboard uses (one snapshot every 0.5 s):

```bash
curl -N http://localhost:8000/api/stream
```

## 5. Running as a different user (JupyterLab and VS Code)

A JupyterLab terminal runs as the `jupyter` user. A VS Code remote session can run as a different user. Check with
`whoami`. The user that runs the app needs to:

- read `api/.venv`, `web/node_modules` and `.env`
- write to `api/data`, `web/node_modules/.vite` and `web/node_modules/.vite-temp`

If you get `Permission denied`, have the user who owns those files run:

```bash
cd /home/jupyter/agentic_ai_tutorial/autonomous_agent
mkdir -p web/node_modules/.vite web/node_modules/.vite-temp
chmod -R o+rwX api/data web/node_modules/.vite web/node_modules/.vite-temp
```

After a run, those files belong to the user who ran it. Before running as a different user, have the last user run
the same `chmod`.

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard address returns **404** | Check the trailing slash (`/proxy/absolute/5173/`). If the page says "did you mean to visit …", `VITE_BASE` and the dashboard's port don't match; they must use the same port. |
| Dashboard address returns **500** or "connection refused" | The dashboard is not running on port 5173. Start it, or check terminal 2 for errors. |
| Page loads but stays **blank** | `VITE_BASE` is not set, so the page's scripts load from outside the proxy. Start the dashboard with `VITE_BASE=/proxy/absolute/5173/ npm run dev`. Terminal 2's `Local:` line must end in `/proxy/absolute/5173/`. |
| Page says "Connecting to the shop…" or "Reconnecting…" | The API is down or restarting. Check `curl localhost:8000/api/health` and the API logs. The page reconnects by itself. |
| `Permission denied: '.../api/.venv/pyvenv.cfg'` | You ran `python -m venv .venv` on an existing venv as another user. Skip that step and just run `source .venv/bin/activate`. |
| Other `Permission denied` errors when starting | See [section 5](#5-running-as-a-different-user-jupyterlab-and-vs-code). |
| Port 8000 is already in use | Usually an API that is still running; see [First, check whether it is already running](#first-check-whether-it-is-already-running). To use another port, start the API with `--port 8010` and the dashboard with `VITE_API_TARGET=http://localhost:8010 npm run dev`. |
| Port 5173 is already in use | Run the dashboard on another port **and** change the base to match: `VITE_BASE=/proxy/absolute/5180/ npm run dev -- --port 5180`, then open `.../proxy/absolute/5180/`. |
| "saved Ns ago" keeps growing | Saving is failing; look for `Could not save` in the logs. Usually permissions (section 5); with Docker, check that you passed `HOST_UID`/`HOST_GID`. |
| Gemini stays on "warming up" | Check `GOOGLE_CLOUD_API_KEY` in `.env` and look for `warm-up failed` in the logs. The demo keeps working on the rules. |
| Many `Agent · Fallback` lines in Gemini mode | Expected at 5x, because the budget runs out. Use Gemini at 1x or 0.5x. |
| Restore a clean demo | Press **Reset** (or load `normal_day` from the edit panel). To start over completely, stop the app and delete `products.csv`, `orders.csv`, `events.csv` and `runtime.json` from `api/data`. Do not delete `scenarios/`. |

Do not run `pytest -m live` while the demo is running. It makes a real Gemini call that the running app cannot
count toward its budget.
