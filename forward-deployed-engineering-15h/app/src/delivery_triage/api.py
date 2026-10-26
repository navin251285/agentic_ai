"""The FastAPI app: /health, the triage endpoint, the stored issues, the stores, the eval gate, and the one-page web UI at /.

Every /api route needs the service token (step 3, lesson 13): `Authorization: Bearer <TRIAGE_SERVICE_TOKEN>`.
/health and the page are open, so a browser can load the page and ask for the token there.
"""
from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
from tenacity.wait import WaitBaseT

from .config import Settings, load_settings
from .errors import AppError, install_error_handlers
from .evals import gate_from_settings
from .models import StoredCase, TriageRequest, TriageResult
from .observability import Telemetry, configure_logging
from .orders import load_orders
from .retries import is_transient
from .store import CaseStore
from .tenants import Tenant, load_tenants
from .triage import triage_message

logger = logging.getLogger("delivery_triage")

STATIC_DIR = Path(__file__).resolve().parent / "static"
VERSION = "0.3.0"
MODEL_NOT_SET = (
    "The model is not set up. Add GOOGLE_CLOUD_API_KEY (or GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION) "
    "to the course .env, then restart the server."
)
AUTH_NOT_SET = (
    "The service token is not set. Add TRIAGE_SERVICE_TOKEN to the course .env (a long random string), "
    "then restart the server. Nothing is answered on /api until it is set."
)


def _default_llm() -> Any:
    from llm_setup import get_llm  # the course's model setup (lesson 06); reads the course .env

    return get_llm()


def create_app(
    settings: Settings | None = None,
    llm_factory: Callable[[], Any] | None = None,
    retry_wait: WaitBaseT | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    configure_logging()
    make_llm = llm_factory or _default_llm
    orders = load_orders(settings.orders_file)
    tenants = load_tenants(settings.tenants_file)
    store = CaseStore(settings.store_file)
    telemetry = Telemetry(settings.trace_file)
    if not settings.service_token:
        logger.warning("TRIAGE_SERVICE_TOKEN is not set: every /api route answers 503 until it is")
    logger.info("orders loaded: %d | stores: %d | cases file: %s", len(orders), len(tenants.all()), settings.store_file.name)

    app = FastAPI(title="Basket Bazaar delivery triage", version=VERSION)
    install_error_handlers(app)

    def require_service_token(authorization: str | None = Header(default=None)) -> None:
        """Lesson 13: the caller proves who it is with a token. The check compares in constant time."""
        if not settings.service_token:
            raise AppError(503, "auth_not_configured", AUTH_NOT_SET)
        presented = authorization[len("Bearer "):] if authorization and authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(presented.encode(), settings.service_token.encode()):
            logger.warning("refused an /api call with a missing or wrong service token")
            raise AppError(401, "unauthorized", "The service token is missing or wrong. Send it as 'Authorization: Bearer <token>'.")

    api = APIRouter(prefix="/api", dependencies=[Depends(require_service_token)])

    def resolve_tenant(tenant_id: str | None) -> Tenant:
        """Lesson 23: the store must be on the list. Refused before any model call is made."""
        tenant = tenants.get((tenant_id or tenants.default_id).strip().lower())
        if tenant is None:
            raise AppError(404, "unknown_tenant", "No such store. The list of stores is at GET /api/tenants.")
        return tenant

    def run_model_and_check(message: str, tenant: Tenant) -> TriageResult:
        try:
            llm = make_llm()
        except Exception as exc:  # no key, or the model client could not start
            logger.warning("model not available: %s", type(exc).__name__)
            raise AppError(503, "model_not_configured", MODEL_NOT_SET) from exc
        try:
            return triage_message(
                message, orders, llm, tenant=tenant, attempts=settings.model_attempts,
                wait=retry_wait, tracer=telemetry.tracer,
            )
        except (ValidationError, OutputParserException) as exc:
            logger.warning("model reply did not fit the case form: %s", type(exc).__name__)
            raise AppError(
                502, "model_reply_invalid",
                "The model's reply did not fit the case form, so nothing was stored. Try the message again.",
            ) from exc
        except Exception as exc:  # the model call failed; the details go to the log
            if is_transient(exc):
                logger.warning("model still unavailable after %d tries", settings.model_attempts)
                raise AppError(
                    503, "model_busy",
                    f"The model was busy or unreachable after {settings.model_attempts} tries. "
                    "Nothing was stored; try again in a minute.",
                ) from exc
            logger.exception("triage failed")
            raise AppError(502, "model_failed", "The model call failed. See the server log.") from exc

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": VERSION,
            "orders_loaded": len(orders),
            "cases_stored": store.count(),
            "service_token_set": bool(settings.service_token),
        }

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @api.get("/tenants")
    def list_tenants() -> dict[str, Any]:
        return {"default": tenants.default_id, "tenants": [t.model_dump() for t in tenants.all()]}

    @api.post("/triage", response_model=TriageResult)
    def triage(request: TriageRequest) -> TriageResult:
        tenant = resolve_tenant(request.tenant)
        started = time.perf_counter()
        # One trace per request (lesson 16). record_exception=False: an error's text may hold model output,
        # so only the status is kept on the span.
        with telemetry.tracer.start_as_current_span("triage.request", record_exception=False) as span:
            span.set_attribute("triage.tenant", tenant.tenant_id)
            trace_id = format(span.get_span_context().trace_id, "032x")
            result = run_model_and_check(request.message, tenant)
            try:
                with telemetry.tracer.start_as_current_span("store.add"):
                    case, created = store.add(result.record, result.status, result.problems, tenant.tenant_id)
            except OSError as exc:
                logger.exception("could not write the cases file")
                raise AppError(500, "store_failed", "The case could not be saved. See the server log.") from exc
            # logged inside the span, so the line carries this request's trace id
            logger.info(
                "triage finished",
                extra={"fields": {
                    "case_id": case.case_id, "duplicate": not created, "status": result.status,
                    "tenant": tenant.tenant_id, "duration_ms": round((time.perf_counter() - started) * 1000),
                }},
            )
        return result.model_copy(update={
            "case_id": case.case_id, "duplicate": not created, "tenant": tenant.tenant_id, "trace_id": trace_id,
        })

    @api.get("/issues", response_model=list[StoredCase])
    def list_issues(limit: int = 20) -> list[StoredCase]:
        return store.list_cases(limit=max(1, min(limit, 100)))

    @api.get("/issues/{case_id}", response_model=StoredCase)
    def get_issue(case_id: str) -> StoredCase:
        case = store.get(case_id)
        if case is None:
            raise AppError(404, "case_not_found", f"No case {case_id}. The list of cases is at GET /api/issues.")
        return case

    @api.get("/evals/gate")
    def eval_gate() -> dict[str, Any]:
        """Lesson 12's bar as a gate: passed only when enough labelled cases pass (evals.py)."""
        try:
            return gate_from_settings(settings).as_dict()
        except FileNotFoundError as exc:
            raise AppError(409, "eval_files_missing", f"{exc} Nothing was checked.") from exc

    app.include_router(api)
    return app


app = create_app()  # uvicorn delivery_triage.api:app
