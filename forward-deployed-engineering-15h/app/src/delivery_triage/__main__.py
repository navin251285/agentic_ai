"""One command starts the app:  python -m delivery_triage   (or `delivery-triage` after the install).

Before the server starts, it checks what the app needs and prints what is set, never a value:
the orders file and the tenants file stop the start when they are wrong; a missing service token or
model key is a warning, because the page still opens and says what to set.

    python -m delivery_triage            start the app on 127.0.0.1 at TRIAGE_PORT (default 8980)
    python -m delivery_triage --check    run the checks and stop
    python -m delivery_triage --reload   restart the server when a file changes (for development)
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import uvicorn

from .config import Settings, load_settings, setting_is_set
from .orders import load_orders
from .tenants import load_tenants


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    blocking: bool  # a blocking check that fails stops the start
    detail: str


def preflight(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    try:
        checks.append(Check("orders file", True, True, f"{len(load_orders(settings.orders_file))} orders"))
    except FileNotFoundError as exc:
        checks.append(Check("orders file", False, True, str(exc)))
    try:
        checks.append(Check("tenants file", True, True, f"{len(load_tenants(settings.tenants_file).all())} stores"))
    except (FileNotFoundError, ValueError) as exc:
        checks.append(Check("tenants file", False, True, str(exc)))
    checks.append(Check(
        "service token", bool(settings.service_token), False,
        "set" if settings.service_token else "not set: the /api routes answer 503 until TRIAGE_SERVICE_TOKEN is set",
    ))
    model_set = setting_is_set("GOOGLE_CLOUD_API_KEY") or (
        setting_is_set("GOOGLE_CLOUD_PROJECT") and setting_is_set("GOOGLE_CLOUD_LOCATION")
    )
    checks.append(Check(
        "model access", model_set, False,
        "set" if model_set else "not set: triage says the model is not set up until the course .env has a key",
    ))
    eval_found = settings.eval_set_file.exists() and settings.eval_results_file.exists()
    checks.append(Check(
        "eval gate files", eval_found, False,
        "found" if eval_found else "not found: the gate waits for lesson 11's files",
    ))
    return checks


def print_report(checks: list[Check]) -> None:
    for check in checks:
        label = "ok  " if check.ok else ("stop" if check.blocking else "warn")
        print(f"  {label} {check.name}: {check.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the Basket Bazaar delivery triage app on this computer.")
    parser.add_argument("--check", action="store_true", help="run the start-up checks and stop")
    parser.add_argument("--reload", action="store_true", help="restart the server when a file changes")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"Not started: {exc}", file=sys.stderr)
        return 1
    print("Checking the app before it starts:")
    checks = preflight(settings)
    print_report(checks)
    if any(check.blocking and not check.ok for check in checks):
        print("Not started: fix the 'stop' line above, then run the command again.", file=sys.stderr)
        return 1
    if args.check:
        return 0
    print(f"Open http://127.0.0.1:{settings.port}/ in your browser. Stop the server with Ctrl+C.")
    uvicorn.run("delivery_triage.api:app", host="127.0.0.1", port=settings.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
