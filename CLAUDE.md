# Restock Agent Demo — Project Spec (v1.7, locked; v1.7 adds Curveball + Shadow shop, see below)

A minimal autonomous inventory agent for a live demo, built with an
enterprise-style architecture. A simulated shop sells items (stock goes down),
an agent (rule-based or Gemini, switchable) watches stock and places orders, and a simulated supplier
delivers after a delay (stock goes back up). Everything is visible on ONE web
screen so an audience can follow: decreasing → danger zone → order placed,
awaiting N seconds → restocked.

## Tech stack
Backend
- Python 3.11+, FastAPI, uvicorn (run with exactly 1 worker — state is in memory), Pydantic v2, pydantic-settings.
- Storage: CSV files (+ one small runtime.json) behind a repository interface, swappable for Postgres later.
- Live updates: Server-Sent Events (SSE). Actions via REST endpoints.
- Dev tools: pytest, ruff.
- LLM: Gemini 2.5 Flash-Lite on Vertex AI via `langchain-google-genai` (`ChatGoogleGenerativeAI`), python-dotenv.
  Client exactly as below — do NOT pass `project` or `location` (with an API key that makes the SDK ignore the key
  and fail looking for default credentials):
  ```python
  ChatGoogleGenerativeAI(model=settings.llm_model, vertexai=True,
                         api_key=settings.google_cloud_api_key,
                         max_output_tokens=1024, temperature=0)
  ```

Frontend
- Node 20, React 18 + Vite + TypeScript (strict).
- State: Zustand store fed by a custom `useLiveState` hook (EventSource → store).
- Charts: Recharts. Styling: Tailwind CSS with the color tokens below.
- API types generated from FastAPI's OpenAPI schema with openapi-typescript into `web/src/api/types.ts`
  via an npm script `gen:types` (reads `http://localhost:8000/openapi.json`). The SSE payload is the same
  `Snapshot` model as `GET /api/snapshot`, so its type is covered.
- Vite dev proxy: `/api` → `VITE_API_TARGET` (`http://localhost:8000` locally, `http://api:8000` in Docker). No CORS needed.
- Dev tools: Vitest + React Testing Library, ESLint (Vite default).

Run
- Docker Compose: `api` (port 8000) and `web` (port 5173, Vite started with `--host 0.0.0.0`).
  `docker compose up` starts the demo. Mount `./api/data:/app/data` so the CSV files are visible and editable on the host.
- Use FastAPI lifespan for startup/shutdown so Ctrl+C and `docker compose stop` both save state.
- Also runnable without Docker: `uvicorn app.main:app` in `api/` and `npm run dev` in `web/`.
- Must work on Windows, macOS and Linux (use pathlib, no OS-specific commands in code).

Out of scope for v1: auth, Kubernetes, message queues, microservices, a real database,
partial deliveries, multiple shops, multi-step LLM tool-calling agents. (v1.7: the agent picks actions
from a fixed menu — order from main/backup supplier, or wait — in ONE structured call; still no multi-step loop.)

## Folder structure
```
api/
  app/
    main.py              # app factory, startup/shutdown hooks, starts the simulation task
    config.py            # Settings from .env
    run_sim.py           # headless runner: python -m app.run_sim
    domain/
      models.py          # Pydantic: Product, Order, Event, SimSettings, Runtime, PersistedState, Decision;
                         #   Snapshot (API view model) is added in phase 4
      rules.py           # pure: product_state(), inventory_position()
    services/
      clock.py           # simulation clock and speed
      shop.py            # customer simulator
      supplier.py        # order lifecycle and deliveries
      agent.py           # autonomous loop; picks an engine, applies guardrails, falls back
      engines/
        base.py          # DecisionEngine protocol
        rules_engine.py  # pure rule-based decide()
        llm_engine.py    # Gemini engine (LangChain, structured output)
        prompts.py       # system prompt + context builder
        guardrails.py    # validate/clamp any engine's decisions
        rate_limiter.py  # hard cap: ≤ 10 LLM calls per 60 real seconds, ≥ 6s apart
      simulation.py      # owns in-memory state; tick: clock → shop → supplier → agent → publish
    repositories/
      base.py            # InventoryRepository (abstract)
      csv_repo.py        # CsvInventoryRepository — THE ONLY CODE THAT TOUCHES FILES
    api/
      routes.py          # REST endpoints
      stream.py          # SSE endpoint
  data/
    products.csv  orders.csv  events.csv  runtime.json
    scenarios/ normal_day.csv  rush_hour.csv  low_stock_start.csv
  tests/
  requirements.txt  requirements-dev.txt  Dockerfile   # dev = pytest, httpx, ruff (test-only)
web/
  src/
    api/                 # client.ts (fetch wrappers), types.ts (generated)
    hooks/useLiveState.ts
    store/useShopStore.ts
    components/
      TopBar.tsx  MetricsRow.tsx  ShopCounter.tsx  ProductGrid.tsx  ProductCard.tsx
      OrdersPipeline.tsx  ActivityFeed.tsx  StockChart.tsx  EditDrawer.tsx  ConnectionBanner.tsx
    App.tsx  main.tsx  index.css
  Dockerfile
design/
  restock-agent-dashboard.pdf   # visual reference (see Design reference)
docker-compose.yml  .env.example  README.md  .gitignore
```
`.gitignore` excludes live data files (`data/products.csv`, `orders.csv`, `events.csv`, `runtime.json`) and quarantined `products.csv.bad-*`,
but keeps `data/scenarios/`.

## Time model (important)
- `sim_s` = simulation seconds. It advances by `0.5 × speed` every 0.5s real tick; it does not advance when paused.
- All lead times, due times, intervals and countdowns are in `sim_s` (they mean "seconds at 1x").
  So at 5x a countdown drops 5 per real second; when paused, everything freezes.
- Shop clock display: day 1 starts at 08:00; shop_time = 08:00 + sim_s × 5 minutes (1 sim second = 5 shop minutes),
  shown as "Day N · HH:MM" (it wraps past midnight into the next day). The shop clock is cosmetic; all logic uses sim_s.
- `sim_s`, speed, settings and counters persist in `runtime.json`, so a restart continues where it left off
  and open orders keep their remaining time.
- Startup is ALWAYS paused (speed 0). `last_speed` is restored from runtime.json, so Play resumes it.

## Repository interface
`InventoryRepository` (services use only these):
`load() -> PersistedState` (products, orders, runtime, current run's events), `save_products(list[Product])`, `save_orders(list[Order])`,
`append_event(Event)`, `read_events(run_id) -> list[Event]` (used once at startup; afterwards the simulation keeps the current run's events in memory),
`save_runtime(dict)`, `load_runtime() -> dict`,
`load_scenario(name) -> list[Product]`, `list_scenarios() -> list[str]`.

## Data files
`products.csv` (rewritten on save): `id,name,stock,max_stock,reorder_point,sell_weight,lead_time_s`
- `id` is a slug (`milk`, `cold-drink`). `lead_time_s` in sim seconds.

`orders.csv` (rewritten on save): `id,product_id,qty,status,placed_at_s,due_at_s,delivered_at_s`
- `id` like `O-0001`. Status: PLACED, CONFIRMED, SHIPPED, DELIVERED. Times in sim_s.

`events.csv` (APPEND-ONLY): `run_id,ts_real,sim_s,shop_time,type,product_id,qty,stock_after,ref,message`
- `run_id` increments on every scenario load or reset (sim_s restarts at 0 per run, so history must filter by run_id).
- `ts_real` ISO 8601. `ref` = customer id (`C-0057`) for sales, order id for order events, "MANUAL" for manual sales, empty otherwise.
- `stock_after` is filled for every event that has a product_id.
- Types: SALE, MISSED_SALE, CROSSED_MARK, ORDER_PLACED, ORDER_CONFIRMED, ORDER_SHIPPED,
  DELIVERED, EDIT, SETTINGS_CHANGED, SCENARIO_LOADED, RESET, AGENT_WAIT, AGENT_FALLBACK.
- AGENT_WAIT: Gemini chose to wait on a watch-zone product (message = reason). Logged at most once per product
  until its stock changes zone, so the feed stays readable.
- ORDER_PLACED message is prefixed with the source, e.g. "[gemini] Rush hour and 60s lead time; ordering milk early."
- CROSSED_MARK is emitted once when stock goes from above reorder_point to at/below it.
- On every scenario load or reset, emit one SCENARIO_LOADED (or RESET) event PER PRODUCT with its starting
  stock_after, so the chart always has a starting point.

`runtime.json`: `run_id, sim_s, speed, last_speed, scenario, rush_hour, supplier_delay, agent_enabled, agent_mode, agent_interval_s,
next_agent_check_s, next_customer_at_s, counters {sales, missed_sales, orders_placed}, next_customer_id, next_order_id`.

Seed products (`scenarios/normal_day.csv`):
| id | name | stock | max_stock | reorder_point | sell_weight | lead_time_s |
|---|---|---|---|---|---|---|
| milk | Milk | 18 | 30 | 12 | 5 | 60 |
| bread | Bread | 18 | 25 | 9 | 4 | 45 |
| eggs | Eggs | 22 | 40 | 13 | 4 | 60 |
| rice | Rice 1kg | 22 | 30 | 10 | 2 | 90 |
| sugar | Sugar | 16 | 24 | 10 | 2 | 90 |
| biscuits | Biscuits | 25 | 40 | 12 | 3 | 90 |
| chips | Chips | 22 | 30 | 9 | 4 | 45 |
| soap | Soap | 12 | 15 | 7 | 1 | 90 |
| toothpaste | Toothpaste | 12 | 15 | 7 | 1 | 90 |
| cold-drink | Cold drink | 20 | 36 | 9 | 4 | 30 |
- These values were checked with a quick simulation of these exact rules (600 sim_s, 20 random seeds):
  normal ≈ 0–1 missed sales; rush hour ≈ 6% missed (visible pressure, not collapse); agent off ≈ 300 missed.
  Do not change them without re-running that check (phase 3 test).
- `rush_hour.csv`: same products; loading it turns `rush_hour` on.
- `low_stock_start.csv`: Milk 14, Eggs 15, Chips 11, Cold drink 11 (each 2 above its reorder point); rest as normal_day.

File safety rules:
- Only `csv_repo.py` touches files.
- products/orders/runtime: write temp file then `os.replace` (atomic). Save every 3s and on shutdown.
- events: append immediately, flush after each write.
- If a write fails (e.g. file open in Excel on Windows): log a warning, keep running, retry next save. Never crash.
  Events that fail to append are kept in an in-memory queue and written, in order, on the next successful write.
- Startup: load products.csv; if missing, copy `scenarios/normal_day.csv`. Missing orders/events/runtime → start empty/defaults.
- If products.csv is invalid (bad row, duplicate id, empty), rename it to `products.csv.bad-<YYYYmmdd-HHMMSS>`,
  log a clear warning, then fall back to the scenario. Never overwrite an earlier .bad file.
- All CSV files are read and written as `utf-8-sig` (Excel-friendly; reading also accepts plain UTF-8).

## Simulation rules
- Tick every 0.5 real seconds. One asyncio task runs the loop. API actions go through the
  simulation service and are applied under one asyncio lock, so the loop and requests never conflict.
- Customers: next arrival every 2–4 sim_s (uniform random); with rush_hour, every 1–2 sim_s (about 2x demand).
  Basket size = uniform random 1–4. Items are picked one at a time weighted by sell_weight, removing each picked
  item (no repeats); qty 1 each. Keep exactly this — the seed stock values are calibrated to it.
  Stock > 0 → SALE (stock −1). Stock 0 → MISSED_SALE.
- Manual sell {qty}: sells what is available, each missing unit is a MISSED_SALE. Works while paused
  (stock changes; nothing else reacts until play resumes).
- Supplier: order lead time = product.lead_time_s (× 1.5 if supplier_delay was on when placed).
  CONFIRMED at 10% of lead time, SHIPPED at 30%, DELIVERED at 100% (stock += qty, capped at max_stock;
  if capped, the event message says how many units were returned).
  Editing a product's lead_time_s, or toggling supplier_delay, affects only orders placed afterwards.
- Agent: runs every `agent_interval_s` (default 5) when `agent_enabled`. Snapshot exposes `next_agent_check_s`.
  Changing agent_interval_s or turning the agent on sets next_agent_check_s = sim_s + agent_interval_s.
- Random seed from `SIM_SEED` in .env (empty = random). Same seed + same actions = same demo.
- Testability: services take an injected `random.Random` and are driven by `tick(dt_sim_s)`; tests never sleep.
  `python -m app.run_sim --speed 5 --duration 600 --fast` runs ticks without real-time waiting.

## Agent
Two engines behind one `DecisionEngine` interface: `async decide(context) -> list[Decision]`.
`Decision` = {product_id, action: "order" | "wait", qty, reason, source: "rules" | "gemini" | "fallback"}.
`agent_mode` setting chooses the engine: "rules" or "gemini" (default from `AGENT_MODE` in .env).

Shared definitions
- inventory_position = stock + qty of all undelivered orders for that product.
- Must-order zone: no open order AND stock <= reorder_point.
- Watch zone: no open order AND reorder_point < stock <= reorder_point × 1.5 (rounded up).

Rules engine (pure: no I/O, no randomness)
- Must-order zone → order qty = max_stock − inventory_position. Watch zone → wait. Reason e.g.
  "Milk at 12, at mark 12, nothing incoming. Ordered 18 to refill to 30."

Gemini call budget (HARD LIMIT — never more than 10 LLM calls in any 60 real seconds)
- `LlmRateLimiter` in `engines/rate_limiter.py`: rolling window of real-time call timestamps.
  Allows a call only if (a) fewer than `LLM_MAX_CALLS_PER_MIN` (10) calls in the last 60 real seconds AND
  (b) at least `LLM_MIN_GAP_S` (6) real seconds since the previous call. (b) alone keeps it ≤ 10/min; (a) is a backstop.
- EVERY call counts: warm-up, decisions, the live smoke test. No automatic retries; a failed call still counts.
- The limiter is checked BEFORE building the request; when it says no, nothing is sent.
- Limits use real time (time.monotonic), not sim_s, so speed changes cannot exceed the budget.
  In `--fast` runs the limiter uses a virtual clock advanced by tick.
- The limiter lives in the api process. The `-m live` smoke test makes exactly ONE call; never run it while the demo
  is running (it is a separate process the limiter cannot see).

When Gemini is asked (event-driven, batched)
- A product becomes "pending" when it newly ENTERS the watch zone or the must-order zone (zone change since the last
  check). A product Gemini answered "wait" for is not asked again until it changes zone.
- Zone tracking starts with every product's last-seen zone = its zone at run start; products that start inside the
  watch or must zone are pending at the first check.
- Switching agent_mode to "gemini" marks every product currently in the watch or must zone pending.
- Turning rush_hour or supplier_delay on/off marks all current watch-zone products pending (new information).
- At each agent check with pending products: if the limiter allows, ONE call covers ALL pending products.
- If the limiter says no: watch-zone products stay pending for the next check. Must-order products get a grace of one
  agent interval; if still no budget, the rules engine orders them (source "fallback", reason "Gemini budget reached").
- Measured with the simulation of these rules (10 seeds × 5 real minutes): 1x ≈ 4 calls/min (worst minute 5);
  1x + rush ≈ 5/min (worst 6); 0.5x ≈ 3/min; 5x hits the cap and most decisions fall back to rules.
  So Gemini mode is meant for 0.5x and 1x.

Gemini engine
- Called only as described above (never on a timer by itself).
- Context sent (compact JSON): those products (stock, max_stock, reorder_point, lead_time_s, sales in the last 60 sim_s),
  open orders, rush_hour, supplier_delay, agent_interval_s.
- Task: for each listed product choose order or wait and a qty, using demand and lead time. It MAY order early in the
  watch zone (e.g. rush hour or supplier delay) and MAY pick a qty below refill-to-max. Reason ≤ 20 words, plain English.
- Uses `llm.with_structured_output(<Pydantic model>)`; temperature 0.
- At most ONE call in flight. While a call is running, the agent shows "thinking" and the next check is skipped;
  the simulation never waits for the LLM.
- Timeout `LLM_TIMEOUT_S` (default 8 real seconds). On timeout, error, or invalid output → use the rules engine for
  that check, source "fallback", and log AGENT_FALLBACK with the short error reason.
- Warm-up: one tiny call in the background at startup (first API-key call can take ~10s). Snapshot shows
  `llm_ready` false until it succeeds. Warm-up is not retried. If the key is missing, gemini mode is still selectable
  but every check falls back to rules with no call made. If the key exists but warm-up failed, decision calls are still
  attempted (within the budget); `llm_ready` becomes true on the first successful call. Fallbacks are clearly shown in UI.

Guardrails (applied to every engine's output, including rules)
- Unknown product, or a product with an open order → dropped.
- qty clamped to 1 … max_stock − inventory_position; qty ≤ 0 → dropped.
- Products in the must-order zone that the engine skipped or answered "wait" → ordered by the rules engine
  (source "fallback"). Gemini can order earlier or smaller, never leave a shelf to run empty.
- Every ORDER_PLACED event message = the decision's reason; `ref` = order id; source shown in UI.
- Tests use a fake LLM; tests NEVER call the real API. One opt-in smoke test (`pytest -m live`) may call Gemini.

## Product states (computed in backend by rules.product_state)
Priority, first match wins:
1. EMPTY: stock == 0 → red (the only use of red)
2. AWAITING: an open order exists → amber bar + blue state
3. DANGER: stock <= reorder_point → amber, card pulses
4. RESTOCKED: a delivery in the last 5 sim_s → green flash
5. SELLING: otherwise → green
Badges (independent of state): open order → "+QTY arriving in Ns" (N = due_at_s − sim_s, rounded up);
DANGER → "Agent checks in Ns" (or "Agent is off" when disabled); RESTOCKED → "+QTY delivered just now".
Note: with the default 5s agent interval, DANGER lasts at most ~5s before AWAITING. That is expected; use 0.5x
or a longer agent interval in the demo to dwell on it.

Color tokens: green #2E8B5E, amber #D98A00, blue #1F4FB8, red #C9302C, ink #17201B,
muted #56615B, ground #F3F4F1, card #FFFFFF, border #DCE0DA.
Fonts: IBM Plex Sans (text), IBM Plex Mono (numbers), Google Fonts.

## API
- `GET /api/health`
- `GET /api/snapshot` (response_model=Snapshot) — products (with state + badge text), open orders (with stage and
  seconds left), settings, counters, run_id, sim_s, shop_time, next_agent_check_s, saved_ago_s, last 50 events,
  agent {mode, enabled, thinking, llm_ready, last_latency_ms, llm_calls, fallbacks,
  calls_last_60s, call_limit, next_call_allowed_in_s, pending_products}.
- `GET /api/stream` — SSE; sends the full Snapshot JSON every tick (small enough). Heartbeat comment every 15s.
  Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- `POST /api/speed` {speed: 0 | 0.5 | 1 | 5} (0 = pause; last non-zero speed is remembered)
- `POST /api/sell` {product_id, qty}  — manual sale; logs SALE/MISSED_SALE with ref "MANUAL".
- `PATCH /api/products/{id}` {stock?, max_stock?, reorder_point?, sell_weight?, lead_time_s?} — logs EDIT, saves immediately.
- `POST /api/settings` {rush_hour?, supplier_delay?, agent_enabled?, agent_mode?, agent_interval_s?} — logs SETTINGS_CHANGED.
- `GET /api/scenarios`, `POST /api/scenario` {name} — replaces products, clears open orders, resets sim_s and counters, logs SCENARIO_LOADED.
- `POST /api/reset` — reloads the current scenario (same effect as above), logs RESET.
- `GET /api/history/{product_id}?window_s=600` — current run only: stock points (sim_s, shop_time, stock_after)
  plus order-placed and delivered markers.
Validation (Pydantic, return 422 with a clear message), checked against the product AFTER merging the patch:
0 ≤ stock ≤ max_stock; 0 ≤ reorder_point < max_stock;
1 ≤ max_stock ≤ 999; 1 ≤ sell_weight ≤ 10; 5 ≤ lead_time_s ≤ 600; 1 ≤ agent_interval_s ≤ 60; known product id.

## Design reference
- `design/restock-agent-dashboard.pdf` — mockups of the live dashboard, one product's cycle (4 states), and the edit panel.
- Use it for LOOK ONLY: layout, spacing, colors, typography, card anatomy, badges, pipeline and feed styling.
- The numbers, product values and times in it are SAMPLE data. Data, rules and behavior come from this file.
- It predates the Gemini features: add the brain switch, agent status chip and budget meter in the same visual style.
- Where the PDF and this file disagree, this file wins.

## UI (one screen)
- TopBar: shop clock ("Day N · HH:MM"), Pause / 0.5x / 1x / 5x, Rush hour, Supplier delay, Agent on/off,
  Agent brain switch "Rules | Gemini" (Gemini shows "warming up" until llm_ready), Reset, "saved Ns ago".
- Agent status chip: "Gemini thinking…" while a call is in flight; last latency; calls and fallbacks count.
- Gemini budget meter (visible in Gemini mode): "Calls this minute 4 / 10", a 10-segment bar, and
  "next call in Ns" when waiting for the gap. Turns amber at 8, red at 10.
- In Gemini mode the 5x button shows a hint "Gemini is limited at 5x — rules will cover most decisions".
- MetricsRow: sales, missed sales, orders placed, orders on the way (since last reset).
- ShopCounter (left): latest customer's items revealed one by one with flash and "−1" (from SALE events grouped by ref),
  last 5 receipts, manual "Sell 1" with product picker.
- ProductGrid (center): 10 ProductCards — name, big stock / max, bar with visible reorder-mark line, state pill, badge, pencil to edit.
- Right: OrdersPipeline (4 steps + countdown per open order), ActivityFeed (latest 30 lines, newest first).
  Feed labels: ORDER_PLACED, AGENT_WAIT → "Agent · Rules" or "Agent · Gemini" (fallbacks marked "Agent · Fallback");
  AGENT_FALLBACK → Alert; ORDER_CONFIRMED/SHIPPED/DELIVERED → Supplier; SALEs → Shop, ONE line per
  customer ("Customer #57 bought Milk, Eggs"); MISSED_SALE, CROSSED_MARK → Alert; EDIT, SETTINGS_CHANGED,
  SCENARIO_LOADED, RESET → System (per-product RESET/SCENARIO_LOADED rows collapse into one line).
- StockChart (bottom): selected product via chips, dashed reorder line, shaded danger zone, markers for order placed and delivered, live updating.
- EditDrawer: fields as PATCH; quick actions Sell 5, Drop to mark (stock = reorder_point), Empty shelf (stock = 0);
  scenario picker; "Apply and save to CSV"; shows validation errors inline.
- ConnectionBanner: shows "Reconnecting…" when SSE drops; EventSource auto-reconnects.
- React holds no business logic: states, badges, countdowns and "saved ago" all come computed from the snapshot.
  React may only format, group events for display, and animate.
- Target 1280–1440 wide (projector). Animations: CSS transitions only, ≤ 600ms. Respect prefers-reduced-motion.

## .env.example
`SIM_SEED=`, `DATA_DIR=./data`, `DEFAULT_SCENARIO=normal_day`, `AGENT_INTERVAL_S=5`,
`SAVE_INTERVAL_S=3`, `API_PORT=8000`, `VITE_API_TARGET=http://localhost:8000`,
`AGENT_MODE=rules`, `GOOGLE_CLOUD_API_KEY=`, `LLM_MODEL=gemini-2.5-flash-lite`, `LLM_TIMEOUT_S=8`,
`LLM_MAX_CALLS_PER_MIN=10`, `LLM_MIN_GAP_S=6` (config may lower the limit, never raise it above 10)
- The real `.env` (with the key) is in `.gitignore` and is never printed, logged or sent to the UI.
- Docker Compose passes it to the api service with `env_file: .env`.

## v1.7: Curveball and Shadow shop (phase 8)
Goal: prove on screen that the Gemini brain is an autonomous agent, not event-driven automation.
Curveball = the agent handles news nobody wrote a handler for. Shadow shop = a measured comparison with the rules.

Economics (constants in `domain/economics.py`, shown in the UI)
- A missed sale loses ₹15 profit (`PROFIT_PER_SALE`).
- Two suppliers. `main`: lead_time_s (× 1.5 with supplier_delay), no fee — the only one the rules use.
  `backup`: lead = max(5, round(lead_time_s × 0.4)) sim_s, ₹2 per unit extra (`BACKUP_FEE_PER_UNIT`);
  not affected by supplier_delay or a strike.
- Calibrated with scripted agents (strike at 1x, 8 seeds, 500 sim_s): bridging the strike with backup orders
  beats the rules shop by ₹170–₹500; refilling every low shelf from backup can lose. So the scoreboard rewards
  judgment, not just using the backup. Guarded by `test_economics_reward_judgment`.
- `Order.supplier` ("main" | "backup", default main) → new last column in orders.csv (old files load as main).
- Counters gain `extra_fees` (₹ paid to the backup supplier). ORDER_PLACED message for backup ends with
  " · backup supplier, +₹N".

Curveball
- `POST /api/curveball {preset?, text?}` (exactly one). `GET /api/curveballs` lists presets. 422 for an unknown
  preset, text outside 3–200 chars, or when 3 curveballs are already active. Logs a CURVEBALL event
  (message = the news text, ref = preset id or "CUSTOM").
- Presets (each lasts 180 sim_s; the effect changes the simulated world for both shops):
  - `heatwave` "Heatwave this afternoon: everyone wants something cold." → cold-drink demand ×3.
  - `strike` "Our main supplier is on strike for the next 3 minutes." → main-supplier orders placed while it is
    active are due at strike end + lead time. Orders already placed are not affected.
  - `cricket` "Cricket final tonight: expect a run on snacks." → chips, cold-drink, biscuits demand ×2.5.
- Custom text: no world effect; only the agent is told (lasts 180 sim_s).
- Demand ×N multiplies that product's sell_weight when customers pick items (basket size unchanged).
  Multipliers of active curveballs multiply. Active curveballs persist in runtime.json; expired ones are removed.
- The agent is told ONLY the news text and seconds left, never the mechanics.
- Rules brain: ignores news (that is the point). Gemini brain: at the next agent check after a curveball (or when
  switching to Gemini while one is active), ONE call covers every product without an open order, not just the
  watch/must zones. Every Gemini call includes active news, both suppliers and the economics.
- Gemini output adds `situation` (≤ 30 words: how it reads the situation) and per decision `supplier`.
  Guardrails unchanged (rules fallbacks always use main). AGENT_WAIT is logged only for watch/must products.
- Agent plan (in AgentStatus.plan, memory only): sim_s, shop_time, trigger ("Curveball: <title>" or
  "Routine check"), situation, steps = final decisions after guardrails (product, action, qty, supplier, reason,
  source). Updated on every Gemini call result, including fallbacks.

Shadow shop (counterfactual twin, `services/shadow.py`, no LLM calls)
- A second copy of the shop managed by the rules engine. It gets exactly the same customers (the same baskets,
  drawn once), manual sales, product edits, settings and curveball effects as the real shop. Its agent runs at
  the same moments and is on/off with the real agent. So with the Rules brain both shops stay identical.
- It writes nothing to events.csv or the feed. Its stock, open orders and counters persist in runtime.json
  (`shadow`), reset on reset/scenario load. Product attributes always mirror the real shop.
- It keeps a stock history (current run) for the chart's ghost line.
- Snapshot `scoreboard`: for agent and rules shop — missed_sales, lost_profit (₹), extra_fees (₹),
  total_cost (₹) — plus `agent_ahead_by` (rules total − agent total) and `same_brain` (agent_mode is rules).
  Snapshot `shadow_stock` {product_id: stock}. History adds `shadow_points`.

UI (phase 8)
- New row under MetricsRow: CurveballPanel | AgentPlanCard | Scoreboard.
- CurveballPanel: preset buttons, a text box + Send, active curveballs with seconds left. In rules mode a hint:
  "The Rules brain can't read news — switch to Gemini."
- AgentPlanCard: trigger and time, the situation sentence, steps (product · order N from main/backup · reason),
  each step tagged Gemini/Fallback. Rules mode: "The Rules brain follows a fixed formula; it doesn't plan."
- Scoreboard: "Agent vs Rules · same customers" with both columns and a headline (e.g. "Agent ahead by ₹240").
- StockChart: dashed grey "Rules shop" line for the selected product.
- OrdersPipeline marks backup orders. Feed: CURVEBALL → label "Curveball".

## Build phases (stop after each)
0. Plan: confirm structure, list questions, `git init`. No code.
1. Backend skeleton, domain models, rules, repository interface, CSV repo, scenarios, runtime.json, tests.
2. Clock, shop, supplier, simulation loop; `python -m app.run_sim` prints events; `--fast` mode;
   manual orders via a repeatable flag `--order <product_id>:<qty>@<sim_s>` (e.g. `--order milk:20@30`), no interactive input.
3. Agent with rules engine + guardrails + tests; `run_sim --duration 600 --fast` on normal_day with no input: missed sales ≤ 3.
3b. Gemini engine: rate limiter, pending/batching, prompts, structured output, timeout, fallback, warm-up,
   fake-LLM tests (incl. limiter test: 10 virtual minutes at 5x, assert no 60s window has > 10 calls),
   one `-m live` smoke test; `run_sim --mode gemini` (real time) shows Gemini reasons and calls/min in the output.
4. API routes + SSE + validation + api Dockerfile/Compose.
5. Web scaffold, generated types, useLiveState + store, ProductGrid/ProductCard with all states and badges.
6. TopBar, MetricsRow, ShopCounter, OrdersPipeline, ActivityFeed, EditDrawer, ConnectionBanner; web in Compose.
7. StockChart, demo polish, README (setup, run, the demo script below, how to swap storage).
8. (v1.7) Curveball + Shadow shop + backup supplier, with tests (twin identical to the real shop in rules mode
   over 600 sim_s on every scenario, with and without presets; fake-LLM curveball tests).

## Final acceptance test
- `docker compose up`, open http://localhost:5173.
- At 1x, a product visibly goes SELLING → DANGER → AWAITING (countdown ticking) → RESTOCKED with no clicks.
- Agent off + rush hour on + 5x for ~20 real seconds → several items EMPTY and missed sales rise;
  agent on, rush off → recovery.
- Edit a product in the drawer → change shows instantly, products.csv updated, EDIT in events.csv.
- Stop and restart → state, open orders and countdowns continue.
- Reset → cards return to scenario values, chart starts fresh, previous runs remain in events.csv.
- Switch brain to Gemini → feed shows "Agent · Gemini" reasons; with rush hour on it orders some items early.
- Remove the API key (or block network) → every check falls back to rules, shelves still never run empty in normal mode.
- Gemini mode for 5 real minutes at 1x (with rush hour toggled once): budget meter never exceeds 10; logs confirm it.
- All backend tests pass; `npm run build` and type check pass.
- (v1.7) Rules brain: scoreboard shows identical scores. Gemini brain at 1x + Supplier strike: the plan card shows
  backup orders with reasons, and the scoreboard shows the agent ahead of the rules shop.

## Demo script (about 4.5 minutes, ≈ 10–12 Gemini calls total)
Numbers below come from simulating these exact rules (20 seeds).
1. (0:00) Start paused, rules brain, normal_day. Explain the screen in 20s. Press 1x.
2. (0:20) Watch Milk: it crosses its mark in under a minute → danger → order placed → countdown → restocked
   (about 60s lead time). Point at the sawtooth chart.
3. (1:45) Show what happens without the agent: agent OFF, rush hour ON, switch to 5x for ~20 real seconds.
   Expect ~5 empty shelves and ~20+ missed sales (never fewer than ~9 in testing).
   Agent ON, rush hour OFF, keep 5x ~15s to recover, then back to 1x.
   (Agent off alone at 1x needs over 2 minutes to show anything, because in-flight orders still arrive.)
4. (2:45) Switch brain to Gemini (already warmed up). Point at the budget meter and "Agent · Gemini" reasons.
5. (3:15) Turn rush hour ON: Gemini re-evaluates watch-zone items and orders some early, explaining why.
   Optionally turn supplier delay ON and show it ordering earlier again.
6. (4:15) (v1.7) Rush hour OFF; take a curveball from the audience or press Supplier strike. Show the plan card
   (situation + backup orders), the rules shop's ghost line dropping, and the scoreboard swinging to the agent.
7. (5:30) Close: scoreboard, metrics row, the activity feed, and the CSV files on disk.
Rules for the presenter: keep Gemini mode at 1x or 0.5x; use 5x only with the rules brain.
Before going live: open the app 1 minute early so warm-up finishes, and rehearse with a fixed SIM_SEED.

## Working rules for Claude
- Build only the phase asked. Stop at the end of each phase and summarize what to test.
- Run the code, type checks and tests before saying a phase is done. Commit at the end of each phase.
- Keep files small and readable. No libraries beyond this stack without asking.
- Business logic lives in the backend; React only displays state and sends actions.
- If the spec is unclear, ask instead of guessing. Do not change this spec without saying so.
