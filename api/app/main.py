"""App factory. Run with exactly one worker: state lives in memory.

uvicorn app.main:app        (from api/)
"""

import asyncio
import contextlib
import logging
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings, get_settings
from app.repositories.base import InventoryRepository
from app.repositories.csv_repo import CsvInventoryRepository
from app.services.agent import build_llm_setup
from app.services.simulation import Simulation

log = logging.getLogger(__name__)


def build_repository(settings: Settings) -> CsvInventoryRepository:
    return CsvInventoryRepository(
        settings.data_dir,
        default_scenario=settings.default_scenario,
        runtime_defaults={
            "scenario": settings.default_scenario,
            "agent_mode": settings.agent_mode,
            "agent_interval_s": settings.agent_interval_s,
        },
    )


def create_app(settings: Settings | None = None, repo: InventoryRepository | None = None) -> FastAPI:
    settings = settings or get_settings()
    repo = repo or build_repository(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = repo.load()
        state.runtime = state.runtime.paused_for_startup()
        rng = random.Random(settings.sim_seed)
        llm = build_llm_setup(settings)
        sim = Simulation(state, repo, rng, save_interval_s=settings.save_interval_s, llm=llm)
        app.state.repo = repo
        app.state.data = state
        app.state.sim = sim
        log.info("Loaded %d products, run %d", len(state.products), state.runtime.run_id)
        task = asyncio.create_task(sim.run())
        if llm.engine is not None:
            sim.agent.start_warmup()  # background; llm_ready turns true when it succeeds
        else:
            log.info("No GOOGLE_CLOUD_API_KEY: gemini mode will fall back to rules")
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # Save on shutdown (Ctrl+C, docker compose stop).
        sim.save()

    app = FastAPI(title="Restock Agent", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
