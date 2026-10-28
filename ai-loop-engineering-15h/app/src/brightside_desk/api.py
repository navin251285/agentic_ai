"""The FastAPI app: /health, the desk chat, the scheduled runs and approvals, and the one-page UI at /.

Run it (one command, from the topic's app folder):  python -m brightside_desk
Or with uvicorn, from app/src:  uvicorn brightside_desk.api:app --reload --port 8980
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import LEDGER_PATH, STATE_DIR, MissingSettingError, Settings, load_settings
from .desk import Caps, run_desk
from .llm import build_chat_model
from .permissions import CHAT_RUN, GRANTS, permit
from .refunds import decide_refunds
from .scheduled import ApprovalError, ScheduledDesk, Ticker, UnknownTask
from .tools import TOOLS, TOOLS_BY_NAME

log = logging.getLogger("brightside_desk")
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    max_turns: int = Field(default=6, ge=1, le=10)
    max_tokens: int | None = Field(default=None, ge=1)
    max_usd: float | None = Field(default=None, gt=0)
    # Stand-in payment faults for the refunds this request makes: "503" or "lost_reply" per call, in order.
    payment_faults: list[Literal["503", "lost_reply"]] = Field(default_factory=list, max_length=4)


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    # The reviewer echoes the total they were shown. A different amount is refused, so the approval covers
    # exactly what the reviewer saw (lesson 22).
    amount_usd: float | None = Field(default=None, gt=0, le=10000)


def create_app(settings: Settings | None = None,
               model_factory: Callable[[], Any] | None = None,
               ledger_path: Path | None = None,
               state_dir: Path | None = None,
               clock: Callable[[], float] | None = None) -> FastAPI:
    """Build the app. Settings are read once; the model is built per request, so a missing key is a clear 503."""
    ledger = ledger_path or LEDGER_PATH
    state = state_dir or STATE_DIR
    config = settings or load_settings()

    def make_model(names: Sequence[str] | None = None) -> Any:
        """The chat model with the given tools bound (all of them by default). The runner still checks each call."""
        if model_factory is not None:
            return model_factory()
        tools = TOOLS if names is None else [TOOLS_BY_NAME[n] for n in names]
        return build_chat_model(config).bind_tools(tools)

    desk = ScheduledDesk(state_dir=state, ledger_path=ledger, clock=clock or time.time,
                         make_model=make_model, limit_usd=config.approval_limit_usd, lease_s=config.lease_s,
                         window_s=config.review_window_s)
    ticker = Ticker(desk, config.tick_s)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        ticker.start()  # a timer only when APP_TICK_S is set; otherwise POST /api/tick is the heartbeat
        try:
            yield
        finally:
            ticker.stop()

    app = FastAPI(title="Brightside support desk loop", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(PAGE)

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict[str, Any]:
        caps = Caps(max_turns=body.max_turns, max_tokens=body.max_tokens, max_usd=body.max_usd)
        try:
            model = make_model()
        except MissingSettingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        try:
            result = run_desk(body.message, caps, model, allowed=lambda name: permit(CHAT_RUN, name))
        except Exception as exc:
            log.exception("the model call failed")
            raise HTTPException(status_code=502,
                                detail="The model call failed. The server log has the details.") from exc
        data = result.to_dict()
        if result.proposals:  # started by a person: the checker and the payment service decide here (step 2)
            data["refunds"] = decide_refunds(result.proposals, ledger, body.payment_faults)
        return data

    @app.get("/api/permissions")
    def permissions() -> dict[str, list[str]]:
        """The grant list of each kind of run: the tools it may call."""
        return {run: sorted(tools) for run, tools in GRANTS.items()}

    @app.post("/api/tick")
    def tick() -> dict[str, Any]:
        """The heartbeat: add the inbox's tickets, then run every claimable one. Scheduled runs wait at the gate."""
        try:
            return desk.tick()
        except MissingSettingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("the scheduled tick failed")
            raise HTTPException(status_code=500, detail="The tick failed. The server log has the details.") from exc

    @app.get("/api/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": desk.tasks()}

    @app.get("/api/approvals")
    def approvals() -> dict[str, Any]:
        return {"approvals": desk.approvals()}

    @app.post("/api/approvals/{ticket}")
    def decide(ticket: str, body: DecisionIn) -> dict[str, Any]:
        try:
            result = desk.decide(ticket, body.decision, body.amount_usd)
        except UnknownTask as exc:
            raise HTTPException(status_code=404, detail=f"no task {ticket}") from exc
        except ApprovalError as exc:  # not waiting for a decision, or the echoed amount is not the one shown
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("the approval could not be applied")
            raise HTTPException(status_code=500, detail="The approval failed. The server log has the details.") from exc
        if result["outcome"] == "refused":  # the review window closed: nothing merged, nothing paid
            raise HTTPException(status_code=409, detail=result["reason"])
        return result

    return app


app = create_app()
