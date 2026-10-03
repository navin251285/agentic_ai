"""REST routes, validation and OpenAPI. The app runs paused (startup is always paused), so nothing moves
unless a test changes it. No API key: these tests never call Gemini."""

import csv

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_repository, create_app


@pytest.fixture
def app(data_dir):
    settings = Settings(_env_file=None, data_dir=data_dir, sim_seed=7)
    return create_app(settings, build_repository(settings))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def products_csv(data_dir) -> dict[str, dict]:
    with open(data_dir / "products.csv", encoding="utf-8-sig", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def errors(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [e["msg"] for e in response.json()["detail"]]


def test_docs_list_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        ("get", "/api/health"),
        ("get", "/api/snapshot"),
        ("get", "/api/stream"),
        ("post", "/api/speed"),
        ("post", "/api/sell"),
        ("patch", "/api/products/{product_id}"),
        ("post", "/api/settings"),
        ("get", "/api/scenarios"),
        ("post", "/api/scenario"),
        ("post", "/api/reset"),
        ("get", "/api/history/{product_id}"),
        ("get", "/api/curveballs"),
        ("post", "/api/curveball"),
    }
    assert {(m, p) for p, ops in paths.items() for m in ops} == expected
    stream = paths["/api/stream"]["get"]["responses"]["200"]["content"]["text/event-stream"]
    assert stream["itemSchema"]["properties"]["data"]["contentSchema"]["$ref"].endswith("/Snapshot")
    assert client.get("/docs").status_code == 200


def test_snapshot_has_everything_the_screen_needs(client):
    snap = client.get("/api/snapshot").json()
    assert snap["speed"] == 0 and snap["scenario"] == "normal_day"
    assert snap["shop_time"].startswith("Day 1 · 08:")
    assert len(snap["products"]) == 10
    milk = next(p for p in snap["products"] if p["id"] == "milk")
    assert (milk["stock"], milk["state"], milk["badge"]) == (18, "SELLING", None)
    assert snap["agent"]["mode"] == "rules" and snap["agent"]["call_limit"] == 10
    assert snap["settings"]["agent_interval_s"] == 5
    assert snap["events"] == []  # fresh data dir: nothing has happened yet
    assert set(snap["counters"]) == {"sales", "missed_sales", "orders_placed", "extra_fees"}
    assert snap["orders"] == [] and snap["orders_on_the_way"] == 0
    assert snap["curveballs"] == [] and snap["agent"]["plan"] is None
    zero = {"missed_sales": 0, "lost_profit": 0, "extra_fees": 0, "total_cost": 0}
    assert snap["scoreboard"] == {"agent": zero, "rules": zero, "agent_ahead_by": 0, "same_brain": True}
    assert snap["shadow_stock"]["milk"] == 18


def test_snapshot_shows_open_orders_with_countdown_and_badges(client, app):
    sim = app.state.sim
    sim.state.runtime.sim_s = 10
    sim.place_order("milk", 12, "[rules] test")
    sim.edit_product("bread", stock=9)  # at its mark, nothing ordered
    snap = client.get("/api/snapshot").json()
    (order,) = snap["orders"]
    assert (order["product_name"], order["status"], order["seconds_left"]) == ("Milk", "PLACED", 60)
    products = {p["id"]: p for p in snap["products"]}
    assert products["milk"]["state"] == "AWAITING" and products["milk"]["badge"] == "+12 arriving in 60s"
    assert products["milk"]["badge_kind"] == "arriving" and products["bread"]["badge_kind"] == "agent"
    assert products["bread"]["state"] == "DANGER" and products["bread"]["badge"].startswith("Agent checks in")
    assert snap["orders_on_the_way"] == 1


def test_speed_pause_remembers_last_speed(client):
    assert client.post("/api/speed", json={"speed": 5}).json()["speed"] == 5
    snap = client.post("/api/speed", json={"speed": 0}).json()
    assert (snap["speed"], snap["last_speed"]) == (0, 5)
    assert errors(client.post("/api/speed", json={"speed": 2}))


def test_sell_while_paused_logs_sales_and_missed_sales(client):
    snap = client.post("/api/sell", json={"product_id": "soap", "qty": 14}).json()
    soap = next(p for p in snap["products"] if p["id"] == "soap")
    assert soap["stock"] == 0 and soap["state"] == "EMPTY"
    assert snap["counters"]["sales"] == 12 and snap["counters"]["missed_sales"] == 2
    sales = [e for e in snap["events"] if e["type"] in ("SALE", "MISSED_SALE")]
    assert len(sales) == 14 and {e["ref"] for e in sales} == {"MANUAL"}
    assert errors(client.post("/api/sell", json={"product_id": "caviar", "qty": 1})) == [
        "Unknown product id 'caviar'"
    ]
    assert errors(client.post("/api/sell", json={"product_id": "soap", "qty": 0}))


def test_patch_product_merges_logs_edit_and_saves_csv(client, data_dir):
    snap = client.patch("/api/products/milk", json={"stock": 12, "lead_time_s": 40}).json()
    milk = next(p for p in snap["products"] if p["id"] == "milk")
    assert (milk["stock"], milk["lead_time_s"], milk["max_stock"]) == (12, 40, 30)
    edit, crossed = snap["events"][-2:]
    assert (
        edit["type"] == "EDIT" and "stock → 12" in edit["message"] and "lead_time_s → 40" in edit["message"]
    )
    assert crossed["type"] == "CROSSED_MARK" and crossed["stock_after"] == 12
    row = products_csv(data_dir)["milk"]
    assert (row["stock"], row["lead_time_s"]) == ("12", "40")
    assert "EDIT" in (data_dir / "events.csv").read_text(encoding="utf-8-sig")


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"stock": 31}, "stock (31) must be ≤ max_stock (30)"),
        ({"max_stock": 15}, "stock (18) must be ≤ max_stock (15)"),  # checked AFTER merging
        ({"reorder_point": 30}, "reorder_point (30) must be < max_stock (30)"),
        ({"sell_weight": 11}, "Input should be less than or equal to 10"),
        ({"lead_time_s": 4}, "Input should be greater than or equal to 5"),
        ({"max_stock": 1000, "stock": 5}, "Input should be less than or equal to 999"),
    ],
)
def test_patch_product_validation(client, data_dir, patch, message):
    assert message in errors(client.patch("/api/products/milk", json=patch))
    assert products_csv(data_dir)["milk"]["stock"] == "18"  # nothing changed


def test_patch_unknown_product(client):
    assert errors(client.patch("/api/products/caviar", json={"stock": 1})) == ["Unknown product id 'caviar'"]


def test_settings_change_logs_once_and_validates(client):
    snap = client.post("/api/settings", json={"rush_hour": True, "agent_interval_s": 10}).json()
    assert snap["settings"]["rush_hour"] is True and snap["settings"]["agent_interval_s"] == 10
    assert snap["next_agent_check_s"] == snap["sim_s"] + 10
    assert snap["events"][-1]["type"] == "SETTINGS_CHANGED"
    same = client.post("/api/settings", json={"rush_hour": True}).json()
    assert same["events"][-1] == snap["events"][-1]  # no change, no event
    assert errors(client.post("/api/settings", json={"agent_interval_s": 61}))
    assert errors(client.post("/api/settings", json={"agent_mode": "magic"}))


def test_scenarios_load_and_reset_start_new_runs(client):
    assert client.get("/api/scenarios").json() == ["low_stock_start", "normal_day", "rush_hour"]
    first = client.get("/api/snapshot").json()["run_id"]
    snap = client.post("/api/scenario", json={"name": "rush_hour"}).json()
    assert snap["run_id"] == first + 1 and snap["settings"]["rush_hour"] is True and snap["sim_s"] == 0
    assert {e["type"] for e in snap["events"]} == {"SCENARIO_LOADED"} and len(snap["events"]) == 10
    client.post("/api/sell", json={"product_id": "milk", "qty": 3})
    reset = client.post("/api/reset").json()
    assert reset["run_id"] == first + 2 and reset["counters"]["sales"] == 0
    assert next(p for p in reset["products"] if p["id"] == "milk")["stock"] == 18
    assert {e["type"] for e in reset["events"]} == {"RESET"}
    msg = errors(client.post("/api/scenario", json={"name": "nope"}))[0]
    assert msg.startswith("Unknown scenario 'nope'") and "normal_day" in msg


def test_history_is_current_run_with_markers(client, app):
    client.post("/api/reset")
    sim = app.state.sim
    sim.state.runtime.sim_s = 20
    sim.state.runtime.next_customer_at_s = 10_000  # only our actions change milk
    client.post("/api/sell", json={"product_id": "milk", "qty": 2})
    sim.place_order("milk", 14, "[rules] test")
    sim.tick(60)  # delivered
    hist = client.get("/api/history/milk").json()
    assert [p["stock_after"] for p in hist["points"]] == [18, 17, 16, 16, 16, 16, 30]
    assert [(m["type"], m["stock_after"]) for m in hist["markers"]] == [
        ("ORDER_PLACED", 16),
        ("DELIVERED", 30),
    ]
    assert hist["points"][0]["sim_s"] == 0  # RESET gives the starting point
    recent = client.get("/api/history/milk", params={"window_s": 30}).json()
    assert [m["type"] for m in recent["markers"]] == ["DELIVERED"]
    assert errors(client.get("/api/history/caviar")) == ["Unknown product id 'caviar'"]
    assert errors(client.get("/api/history/milk", params={"window_s": 0}))


def test_saved_ago_counts_from_last_save(client, app):
    client.patch("/api/products/milk", json={"stock": 17})  # saves immediately
    assert client.get("/api/snapshot").json()["saved_ago_s"] == 0
    app.state.sim.last_saved_at -= 7
    assert client.get("/api/snapshot").json()["saved_ago_s"] == 7


def test_curveball_presets_and_validation(client, data_dir):
    presets = client.get("/api/curveballs").json()
    assert [p["id"] for p in presets] == ["heatwave", "strike", "cricket"]
    assert presets[1]["effect"].startswith("Orders to the main supplier")
    assert presets[0]["effect"].startswith("Twice as many customers")
    snap = client.post("/api/curveball", json={"preset": "strike"}).json()
    [cb] = snap["curveballs"]
    assert (cb["preset"], cb["title"], cb["seconds_left"]) == ("strike", "Supplier strike", 180)
    snap = client.post("/api/curveball", json={"text": "Diwali sale this weekend"}).json()
    assert (
        snap["curveballs"][-1]["preset"] is None
        and snap["curveballs"][-1]["title"] == "Diwali sale this weekend"
    )
    assert errors(client.post("/api/curveball", json={"preset": "earthquake"}))[0].startswith(
        "Unknown preset 'earthquake'"
    )
    assert errors(client.post("/api/curveball", json={})) == ["Value error, send either a preset or a text"]
    assert errors(client.post("/api/curveball", json={"preset": "strike", "text": "both"}))
    assert errors(client.post("/api/curveball", json={"text": "hi"}))  # too short
    client.post("/api/curveball", json={"preset": "heatwave"})
    assert errors(client.post("/api/curveball", json={"preset": "cricket"}))[0].startswith(
        "At most 3 curveballs"
    )
    with open(data_dir / "events.csv", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["type"] == "CURVEBALL"]
    assert [(r["ref"], r["message"]) for r in rows][:2] == [
        ("strike", "Our main supplier is on strike for the next 3 minutes."),
        ("CUSTOM", "Diwali sale this weekend"),
    ]


def test_history_has_the_rules_shop_line(client):
    hist = client.get("/api/history/milk").json()
    assert hist["shadow_points"][0]["stock_after"] == 18
