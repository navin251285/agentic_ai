"""Headless runner: prints every event, then a summary. Never touches the live data files.

    python -m app.run_sim --speed 5 --duration 600 --fast
    python -m app.run_sim --fast --duration 120 --order milk:20@30 --order eggs:10@45

--duration is in sim seconds. --fast runs ticks back to back with no real-time waiting.
"""

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass

from app.config import get_settings
from app.domain.models import Event
from app.domain.rules import product_state
from app.repositories.csv_repo import CsvInventoryRepository
from app.repositories.memory_repo import InMemoryInventoryRepository
from app.services import clock
from app.services.simulation import Simulation, UnknownProduct

ORDER_RE = re.compile(r"^(?P<product>[a-z0-9-]+):(?P<qty>[1-9]\d*)@(?P<at>\d+(\.\d+)?)$")


@dataclass(frozen=True)
class ManualOrder:
    product_id: str
    qty: int
    at_s: float


def parse_order(text: str) -> ManualOrder:
    m = ORDER_RE.match(text.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"expected ID:QTY@SIM_S, e.g. milk:20@30 (got {text!r})")
    return ManualOrder(m["product"], int(m["qty"]), float(m["at"]))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.run_sim", description=__doc__.split("\n")[0])
    p.add_argument("--speed", type=float, choices=[0.5, 1, 5], default=1, help="sim speed (default 1)")
    p.add_argument("--duration", type=float, default=600, help="sim seconds to run (default 600)")
    p.add_argument("--fast", action="store_true", help="no real-time waiting")
    p.add_argument("--scenario", default=None, help="scenario name (default: DEFAULT_SCENARIO)")
    p.add_argument("--seed", type=int, default=None, help="random seed (default: SIM_SEED, else random)")
    p.add_argument("--rush-hour", action="store_true", help="turn rush hour on")
    p.add_argument("--supplier-delay", action="store_true", help="turn supplier delay on")
    p.add_argument("--no-agent", action="store_true", help="turn the agent off")
    p.add_argument("--agent-interval", type=int, default=None, help="agent check interval in sim_s")
    p.add_argument(
        "--order",
        type=parse_order,
        action="append",
        default=[],
        metavar="ID:QTY@SIM_S",
        help="place a manual order at a sim time; repeatable (e.g. --order milk:20@30)",
    )
    p.add_argument("--quiet", action="store_true", help="print only the summary")
    return p.parse_args(argv)


def format_event(e: Event) -> str:
    stock = "" if e.stock_after is None else f"stock={e.stock_after}"
    product = e.product_id or ""
    return f"{e.sim_s:7.1f}  {e.shop_time}  {e.type:<15} {product:<11} {stock:<9} {e.ref:<7} {e.message}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    scenario = args.scenario or settings.default_scenario
    seed = args.seed if args.seed is not None else settings.sim_seed
    if seed is None:
        seed = random.randrange(2**32)

    scenarios = CsvInventoryRepository(settings.data_dir)  # read-only use: scenarios
    if scenario not in scenarios.list_scenarios():
        print(f"Unknown scenario {scenario!r}. Available: {', '.join(scenarios.list_scenarios())}")
        return 2
    repo = InMemoryInventoryRepository(scenarios, scenario)
    sim = Simulation(repo.load(), repo, random.Random(seed))
    if not args.quiet:
        sim.event_listeners.append(lambda e: print(format_event(e), flush=True))

    sim.load_scenario(scenario)
    rt = sim.state.runtime
    rt.rush_hour = rt.rush_hour or args.rush_hour
    rt.supplier_delay = args.supplier_delay
    rt.agent_enabled = not args.no_agent
    if args.agent_interval is not None:
        rt.agent_interval_s = args.agent_interval
        rt.next_agent_check_s = rt.agent_interval_s
    sim.set_speed(args.speed)

    orders = sorted(args.order, key=lambda o: o.at_s)
    for o in orders:
        try:
            sim.product(o.product_id)
        except UnknownProduct:
            print(f"Unknown product in --order: {o.product_id!r}")
            return 2

    started = time.monotonic()
    dt = clock.sim_dt(rt)
    ticks = 0
    while rt.sim_s < args.duration:
        while orders and orders[0].at_s <= rt.sim_s:
            o = orders.pop(0)
            name = sim.product(o.product_id).name
            sim.place_order(o.product_id, o.qty, f"[manual] Ordered {o.qty} {name} (run_sim --order)")
        sim.tick(dt)
        ticks += 1
        if not args.fast:
            time.sleep(clock.TICK_REAL_S)

    print_summary(sim, scenario, seed, args, ticks, time.monotonic() - started)
    return 0


def print_summary(sim: Simulation, scenario: str, seed: int, args, ticks: int, wall_s: float) -> None:
    rt, c = sim.state.runtime, sim.state.runtime.counters
    agent = f"agent {rt.agent_mode} every {rt.agent_interval_s}s" if rt.agent_enabled else "agent off"
    flags = [agent] + [
        f for f, on in (("rush hour", rt.rush_hour), ("supplier delay", rt.supplier_delay)) if on
    ]
    print()
    print(
        f"=== {rt.sim_s:g} sim_s ({clock.shop_time(rt.sim_s)}) · scenario {scenario} · {args.speed:g}x"
        f"{' · ' + ', '.join(flags) if flags else ''} · seed {seed}"
    )
    print(f"    {ticks} ticks in {wall_s:.2f}s real{' (fast)' if args.fast else ''}")
    print(f"    sales {c.sales} · missed sales {c.missed_sales} · orders placed {c.orders_placed}")
    print(f"    {'product':<11} {'stock':>9}  state")
    for p in sim.state.products:
        state = product_state(p, sim.state.orders, rt.sim_s)
        print(f"    {p.id:<11} {p.stock:>4} / {p.max_stock:<3} {state}")


if __name__ == "__main__":
    sys.exit(main())
