"""The FastAPI app: the chat page, /health, POST /api/chat (step 1), the support desk under /api/desk (step 2), and
the traces and cost dashboard under /api/traces (step 3)."""
from __future__ import annotations

import logging
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from support_desk.agent import ModelUnavailable, run_chat
from support_desk.desk import DESK_TOOLS, DeskService, NoPendingApproval, ThreadExists, UnknownThread
from support_desk.settings import load_settings
from support_desk.tools import TOOLS

logger = logging.getLogger("support_desk")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Brightside support desk", version="0.3.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500, description="What the customer wrote.")


class ToolCall(BaseModel):
    name: str
    args: dict
    result: dict


class ChatReply(BaseModel):
    answer: str
    stop: str
    steps: int
    cost_usd: float
    calls: list[ToolCall]


class DeskChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    thread_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
                           description="One id per question: the saved run is found under it.")
    message: str = Field(min_length=1, max_length=500)


class DecisionRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    reviewer: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$", description="Who decides.")
    approve: bool


class MemoryRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    topic: str = Field(min_length=1, max_length=40)
    fact: str = Field(min_length=1, max_length=300)


class DeskReply(BaseModel):
    thread_id: str
    status: str
    stop: str
    answer: str
    pending: dict | None
    calls: list[dict]
    model_calls: int
    cost_usd: float
    cites: dict
    facts: list[str]


@lru_cache(maxsize=1)
def _desk_service() -> DeskService:
    return DeskService(load_settings())


def get_desk() -> DeskService:
    """The desk's saved state, opened once. Tests replace it with app.dependency_overrides."""
    return _desk_service()


@app.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    settings = load_settings()
    return {"status": "ok", "tools": list(TOOLS), "desk_tools": list(DESK_TOOLS),
            "max_steps": settings.max_steps, "max_usd": settings.max_usd}


@app.post("/api/chat", response_model=ChatReply)
async def chat(request: ChatRequest) -> ChatReply:
    try:
        result = await run_in_threadpool(run_chat, request.message)
    except ModelUnavailable as err:
        logger.warning("chat unavailable: %s", err)
        raise HTTPException(status_code=503, detail=str(err)) from err
    return ChatReply(answer=result.answer, stop=result.stop, steps=result.steps,
                     cost_usd=round(result.cost_usd, 6), calls=result.calls)


def _reply(run) -> DeskReply:
    return DeskReply(**asdict(run))


@app.post("/api/desk/memory")
def remember(request: MemoryRequest, desk: DeskService = Depends(get_desk)) -> dict:
    """Save one fact. The guard refuses a card number or a password; the refusal never repeats the text."""
    return {"result": desk.remember(request.customer_id, request.topic, request.fact)}


@app.get("/api/desk/memory/{customer_id}")
def facts(customer_id: str, desk: DeskService = Depends(get_desk)) -> dict:
    return {"customer_id": customer_id, "facts": desk.facts(customer_id)}


@app.post("/api/desk/chat", response_model=DeskReply)
def desk_chat(request: DeskChatRequest, desk: DeskService = Depends(get_desk)) -> DeskReply:
    try:
        run = desk.start(request.customer_id, request.thread_id, request.message)
    except ThreadExists as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ModelUnavailable as err:
        logger.warning("desk unavailable: %s", err)
        raise HTTPException(status_code=503, detail=str(err)) from err
    return _reply(run)


@app.post("/api/desk/decision", response_model=DeskReply)
def decide(request: DecisionRequest, desk: DeskService = Depends(get_desk)) -> DeskReply:
    try:
        run = desk.decide(request.thread_id, request.reviewer, request.approve)
    except UnknownThread as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except NoPendingApproval as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ModelUnavailable as err:
        logger.warning("desk unavailable: %s", err)
        raise HTTPException(status_code=503, detail=str(err)) from err
    return _reply(run)


@app.get("/api/desk/runs/{thread_id}", response_model=DeskReply)
def run_status(thread_id: str, desk: DeskService = Depends(get_desk)) -> DeskReply:
    """The saved run: after a restart of the app, a run that waits for approval is still waiting here."""
    try:
        return _reply(desk.run(thread_id))
    except UnknownThread as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@app.get("/api/traces")
def traces(desk: DeskService = Depends(get_desk)) -> dict:
    """The dashboard: one row per ticket (model calls, tool calls, refusals, cost, time) and the totals."""
    return desk.tasks()


@app.get("/api/traces/{thread_id}")
def trace(thread_id: str, desk: DeskService = Depends(get_desk)) -> dict:
    """The span tree of one ticket: the call, its model calls with tokens, and its tool calls with decisions."""
    try:
        return {"thread_id": thread_id, "spans": desk.trace(thread_id)}
    except UnknownThread as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
