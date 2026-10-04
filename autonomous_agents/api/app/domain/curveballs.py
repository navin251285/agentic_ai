"""Curveball presets and their effects on the world. Pure: no I/O.

The agent is only told the news text; these effects are what the simulation does, for both shops.
"""

import math
from dataclasses import dataclass, field

from app.domain.models import Curveball

DURATION_S = 180  # sim seconds
MAX_ACTIVE = 3
CUSTOM = "CUSTOM"  # event ref for custom text


@dataclass(frozen=True)
class Preset:
    title: str
    text: str
    effect: str
    demand: dict[str, float] = field(default_factory=dict)  # product id → sell_weight multiplier
    crowd: bool = False  # customers arrive as in rush hour (about twice as many)
    strike: bool = False  # main supplier ships nothing new until it ends


PRESETS: dict[str, Preset] = {
    "heatwave": Preset(
        "Heatwave",
        "Heatwave this afternoon: the shop will be packed and everyone wants something cold.",
        "Twice as many customers; cold drinks sell 3× more.",
        demand={"cold-drink": 3},
        crowd=True,
    ),
    "strike": Preset(
        "Supplier strike",
        "Our main supplier is on strike for the next 3 minutes.",
        "Orders to the main supplier ship only after the strike ends.",
        strike=True,
    ),
    "cricket": Preset(
        "Cricket final",
        "Cricket final tonight: the shop will be packed, with a run on snacks and drinks.",
        "Twice as many customers; chips, cold drinks and biscuits sell 2.5× more.",
        demand={"chips": 2.5, "cold-drink": 2.5, "biscuits": 2.5},
        crowd=True,
    ),
}


def make(curveball_id: int, sim_s: float, preset: str | None = None, text: str | None = None) -> Curveball:
    """Raises KeyError for an unknown preset."""
    if preset is not None:
        p = PRESETS[preset]
        title, text = p.title, p.text
    else:
        text = " ".join((text or "").split())
        title = text if len(text) <= 40 else text[:39] + "…"
    return Curveball(
        id=curveball_id,
        preset=preset,
        title=title,
        text=text,
        started_at_s=sim_s,
        ends_at_s=sim_s + DURATION_S,
    )


def active(curveballs: list[Curveball], sim_s: float) -> list[Curveball]:
    return [c for c in curveballs if c.ends_at_s > sim_s]


def demand_multiplier(curveballs: list[Curveball], product_id: str) -> float:
    return math.prod(PRESETS[c.preset].demand.get(product_id, 1) for c in curveballs if c.preset in PRESETS)


def crowd(curveballs: list[Curveball]) -> bool:
    return any(PRESETS[c.preset].crowd for c in curveballs if c.preset in PRESETS)


def strike_ends_at_s(curveballs: list[Curveball]) -> float | None:
    ends = [c.ends_at_s for c in curveballs if c.preset in PRESETS and PRESETS[c.preset].strike]
    return max(ends, default=None)
