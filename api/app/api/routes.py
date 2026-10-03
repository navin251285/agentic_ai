"""REST endpoints. Every action runs through the Simulation under its lock, so it never interleaves with
a tick. Actions return the new Snapshot. Invalid input → 422 with a clear message (FastAPI's format)."""

from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.domain import curveballs
from app.domain.models import (
    CurveballPreset,
    CurveballRequest,
    History,
    ProductPatch,
    ScenarioRequest,
    SellRequest,
    SettingsPatch,
    Snapshot,
    SpeedRequest,
)
from app.repositories.base import ScenarioNotFound
from app.services.simulation import Simulation, TooManyCurveballs, UnknownProduct
from app.services.snapshot import build_history, build_snapshot

router = APIRouter(prefix="/api")


def _sim(request: Request) -> Simulation:
    return request.app.state.sim


def _invalid(loc: Sequence[str | int], msg: str, value: Any = None) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": tuple(loc), "msg": msg, "input": value}])


def _unknown_product(loc: Sequence[str | int], product_id: str) -> RequestValidationError:
    return _invalid(loc, f"Unknown product id '{product_id}'", product_id)


def _from_validation_error(exc: ValidationError) -> RequestValidationError:
    """Errors from validating the merged object, reported against the request body."""
    errors = []
    for e in exc.errors(include_url=False):
        msg = e["msg"].removeprefix("Value error, ")
        errors.append({"type": e["type"], "loc": ("body", *e["loc"]), "msg": msg, "input": e.get("input")})
    return RequestValidationError(errors)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/snapshot")
async def snapshot(request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        return build_snapshot(sim)


@router.post("/speed", summary="Set speed (0 = pause; the last non-zero speed is remembered)")
async def set_speed(body: SpeedRequest, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        sim.set_speed(body.speed)
        return build_snapshot(sim)


@router.post("/sell", summary="Manual sale (works while paused)")
async def sell(body: SellRequest, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        try:
            sim.sell(body.product_id, body.qty)
        except UnknownProduct:
            raise _unknown_product(("body", "product_id"), body.product_id) from None
        return build_snapshot(sim)


@router.patch("/products/{product_id}", summary="Edit a product (logged as EDIT, saved to CSV at once)")
async def edit_product(product_id: str, body: ProductPatch, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        try:
            sim.edit_product(product_id, **body.model_dump(exclude_none=True))
        except UnknownProduct:
            raise _unknown_product(("path", "product_id"), product_id) from None
        except ValidationError as exc:
            raise _from_validation_error(exc) from None
        return build_snapshot(sim)


@router.post("/settings", summary="Change settings (logged as SETTINGS_CHANGED)")
async def update_settings(body: SettingsPatch, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        try:
            sim.update_settings(**body.model_dump(exclude_none=True))
        except ValidationError as exc:
            raise _from_validation_error(exc) from None
        return build_snapshot(sim)


@router.get("/scenarios")
def list_scenarios(request: Request) -> list[str]:
    return _sim(request).repo.list_scenarios()


@router.post("/scenario", summary="Load a scenario: new run, orders cleared, sim_s and counters reset")
async def load_scenario(body: ScenarioRequest, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        try:
            sim.load_scenario(body.name)
        except ScenarioNotFound:
            known = ", ".join(sim.repo.list_scenarios())
            raise _invalid(
                ("body", "name"), f"Unknown scenario '{body.name}' (known: {known})", body.name
            ) from None
        return build_snapshot(sim)


@router.post("/reset", summary="Reload the current scenario (new run, logged as RESET)")
async def reset(request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        sim.reset()
        return build_snapshot(sim)


@router.get("/curveballs", summary="Curveball presets")
def list_curveballs() -> list[CurveballPreset]:
    return [
        CurveballPreset(id=k, title=p.title, text=p.text, effect=p.effect)
        for k, p in curveballs.PRESETS.items()
    ]


@router.post("/curveball", summary="Tell the agent some news (a preset also changes the world)")
async def add_curveball(body: CurveballRequest, request: Request) -> Snapshot:
    sim = _sim(request)
    async with sim.lock:
        try:
            sim.add_curveball(body.preset, body.text)
        except KeyError:
            known = ", ".join(curveballs.PRESETS)
            raise _invalid(
                ("body", "preset"), f"Unknown preset '{body.preset}' (known: {known})", body.preset
            ) from None
        except TooManyCurveballs as exc:
            raise _invalid(("body",), str(exc)) from None
        return build_snapshot(sim)


@router.get("/history/{product_id}", summary="Stock history of one product in the current run")
async def history(
    request: Request,
    product_id: Annotated[str, Path()],
    window_s: Annotated[float, Query(gt=0, le=86_400, description="Sim seconds to look back")] = 600,
) -> History:
    sim = _sim(request)
    async with sim.lock:
        try:
            return build_history(sim, product_id, window_s)
        except UnknownProduct:
            raise _unknown_product(("path", "product_id"), product_id) from None
