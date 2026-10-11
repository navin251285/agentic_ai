"""Record real LLM/API calls once, replay them forever.

LLM-heavy lessons (agentic AI, RAG, ...) call models in almost every cell. To let those
notebooks run on any laptop with no key, no cost and identical output, every HTTP call the
lesson makes (any SDK built on httpx, requests, urllib3 or aiohttp) is recorded to a
"cassette" file the first time, and replayed from it afterwards.

In a lesson (first code cell, and last code cell):

    import sys; sys.path.insert(0, "..")
    import llm_replay
    llm_replay.start("07_tool_calling")      # the notebook's file name without .ipynb
    ...

In this course the lessons don't call start() themselves: agent_model.choose(lesson) picks the
model and calls start(lesson, model=..., key_env=...), so each model has its own recording.
    llm_replay.stop()                        # saves the recording

Modes (environment variable TUT_LLM_MODE):
    auto    (default) replay if a recording exists; otherwise record if an API key is set
    replay  only replay; fail if a call was not recorded
    record  make real calls and overwrite the recording
    live    no recording at all: real calls every time (for learners using their own key)

Low cost: in record and live modes every real model call is counted, and a call beyond the
lesson's budget (start(..., max_calls=N); default TUT_LLM_MAX_CALLS or 4, i.e. two examples of at
most 2 calls each) raises an error before it is sent. stop() prints how many calls were made.
Replay never calls a model, so it costs nothing.

Gentle on quotas: in record and live modes, calls to Google APIs (Gemini) are spaced at least
TUT_LLM_MIN_INTERVAL seconds apart (default 4, i.e. at most 15 per minute), and a 429 / 503
reply is retried with backoff (honouring retry-after) up to TUT_LLM_MAX_RETRIES times
(default 5). Those 429 / 503 replies are never saved, so a recording only holds real answers.

Recordings live in ../data/llm_cassettes/<lesson>.yaml, or <lesson>/<provider>__<model>.yaml
when a model is given (one recording per model, so learners can switch models). They are
committed with the course. API keys, auth headers and cookies are stripped before saving.
Calls are matched by method + URL and replayed in the order they were recorded, so a
notebook must make its calls in the same order every run (it does, if run top to bottom).
"""
from __future__ import annotations

import asyncio
import atexit
import importlib
import os
import re
import time
from pathlib import Path

KEY_ENV_VARS = ["GOOGLE_CLOUD_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
SECRET_HEADERS = ["authorization", "x-api-key", "x-goog-api-key", "api-key", "openai-organization",
                  "openai-project", "cookie", "set-cookie", "x-goog-user-project", "proxy-authorization"]
SECRET_QUERY = ["key", "api_key", "apikey", "access_token"]
PACED_HOSTS = ("googleapis.com", "anthropic.com", "openai.com")   # Gemini, Claude, OpenAI APIs
RETRY_STATUS = {429, 503, 529}      # rate limited / overloaded: wait and try again

_state: dict = {"cm": None, "mode": None, "path": None, "calls": 0, "budget": None}
_pace: dict = {"last": 0.0, "originals": []}


def cassette_dir() -> Path:
    return Path(os.environ.get("TUT_CASSETTE_DIR", Path.cwd().parent / "data" / "llm_cassettes"))


def _has_key() -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path.cwd().parent / ".env")
    except ImportError:
        pass
    return any(os.environ.get(k) for k in KEY_ENV_VARS) or bool(os.environ.get("TUT_LLM_LOCAL"))


def _scrub_response(response):
    if response.get("status", {}).get("code") in RETRY_STATUS:
        return None  # never record a rate-limit reply; the retry's answer is recorded instead
    headers = response.get("headers", {})
    for h in list(headers):
        if h.lower() in SECRET_HEADERS:
            headers.pop(h)
    body = response.get("body", {})
    if isinstance(body.get("string"), (str, bytes)):
        body["string"] = scrub_text(body["string"])
    return response


# Google auth (metadata server / OAuth) replies carry live tokens and account ids
_SECRET_BODY = [
    (re.compile(r'("(?:access_token|id_token|refresh_token)"\s*:\s*")[^"]+'), r"\1REDACTED"),
    (re.compile(r"[\w.+-]+@[\w-]+\.iam\.gserviceaccount\.com|[\w.+-]+@developer\.gserviceaccount\.com"),
     "redacted@example.iam.gserviceaccount.com"),
]


def scrub_text(text):
    as_bytes = isinstance(text, bytes)
    s = text.decode("utf-8", "replace") if as_bytes else text
    for pattern, repl in _SECRET_BODY:
        s = pattern.sub(repl, s)
    return s.encode() if as_bytes else s


def _paced(request) -> bool:
    return request.url.host.endswith(PACED_HOSTS)


def _gap() -> float:
    """Seconds to wait so paced calls stay TUT_LLM_MIN_INTERVAL apart; claims the next slot."""
    interval = float(os.environ.get("TUT_LLM_MIN_INTERVAL", "4"))
    now = time.monotonic()
    slot = max(now, _pace["last"] + interval)
    _pace["last"] = slot
    return slot - now


def _retry_delay(response, attempt: int) -> float:
    try:
        return float(response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return min(60.0, 5.0 * 2 ** attempt)  # 5, 10, 20, 40, 60 s


def _should_retry(response, attempt: int) -> float | None:
    retries = int(os.environ.get("TUT_LLM_MAX_RETRIES", "5"))
    if response.status_code not in RETRY_STATUS or attempt >= retries:
        return None
    delay = _retry_delay(response, attempt)
    print(f"Model busy ({response.status_code}): waiting {delay:.0f}s, retry {attempt + 1}/{retries}")
    return delay


def _count_call() -> None:
    """Count one real model call; refuse it if the lesson's budget is used up."""
    budget = _state.get("budget")
    if budget is not None and _state["calls"] >= budget:
        raise RuntimeError(
            f"Model-call budget reached: this lesson allows {budget} real calls and has made {_state['calls']}.\n"
            "Each example should use at most 2 calls. Shorten the example, or raise the budget "
            "with start(..., max_calls=N) only if the lesson really needs it."
        )
    _state["calls"] += 1


def _install_pacing() -> None:
    """Space out and retry real calls to Google APIs (wraps httpx's send, above vcrpy's hook)."""
    if _pace["originals"]:
        return
    for name in ("httpx", "httpx2"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        sync_send, async_send = mod.Client.send, mod.AsyncClient.send

        def send(self, request, *args, _send=sync_send, **kwargs):
            if not _paced(request):
                return _send(self, request, *args, **kwargs)
            _count_call()
            attempt = 0
            while True:
                time.sleep(_gap())
                response = _send(self, request, *args, **kwargs)
                delay = _should_retry(response, attempt)
                if delay is None:
                    return response
                response.close()
                time.sleep(delay)
                attempt += 1

        async def asend(self, request, *args, _send=async_send, **kwargs):
            if not _paced(request):
                return await _send(self, request, *args, **kwargs)
            _count_call()
            attempt = 0
            while True:
                await asyncio.sleep(_gap())
                response = await _send(self, request, *args, **kwargs)
                delay = _should_retry(response, attempt)
                if delay is None:
                    return response
                await response.aclose()
                await asyncio.sleep(delay)
                attempt += 1

        mod.Client.send, mod.AsyncClient.send = send, asend
        _pace["originals"].append((mod, sync_send, async_send))


def _remove_pacing() -> None:
    for mod, sync_send, async_send in _pace["originals"]:
        mod.Client.send, mod.AsyncClient.send = sync_send, async_send
    _pace["originals"].clear()


def model_tag(model: str) -> str:
    """'gemini:gemini-3.5-flash-lite' -> 'gemini__gemini-3.5-flash-lite' (safe as a file name)."""
    return model.replace(":", "__").replace("/", "-")


def recorded_models(lesson: str) -> list[str]:
    """The models that have a recording for this lesson, as 'provider:model'."""
    folder = cassette_dir() / lesson
    return sorted(p.stem.replace("__", ":", 1) for p in folder.glob("*.yaml")) if folder.is_dir() else []


def _key_set(key_env: str | None) -> bool:
    if key_env is None:          # a local model (Ollama): no key needed
        return True
    _has_key()                   # loads ../.env
    return bool(os.environ.get(key_env))


def start(lesson: str, model: str | None = None, key_env: str | None = "", max_calls: int | None = None) -> None:
    """Start recording or replaying for this lesson (prints the mode in use; see mode()).

    model: 'provider:model' -> one recording per model. key_env: the API key that model needs
    (None for a local model). Without a model, one recording per lesson, as before.
    max_calls: the most real model calls this lesson may make (default TUT_LLM_MAX_CALLS or 4).
    """
    if _state["cm"] is not None:
        stop()
    mode = os.environ.get("TUT_LLM_MODE", "auto").lower()
    path = cassette_dir() / (f"{lesson}/{model_tag(model)}.yaml" if model else f"{lesson}.yaml")
    can_call = _key_set(key_env) if model else _has_key()
    if mode in ("auto", "replay") and not path.exists() and (mode == "replay" or not can_call):
        if model:
            others = [m for m in recorded_models(lesson) if m != model]
            raise RuntimeError(
                f"Can't run lesson {lesson} with {model}: it has no recording for this model"
                + (f" and {key_env} is not set." if key_env else ".")
                + (f"\nTo run it for real, add {key_env}=... to the .env file and run again." if key_env
                   else "\nTo run it for real, start your local model server and run again.")
                + (f"\nOr switch to a model that has a recording: {', '.join(others)}" if others else "")
            )
        raise RuntimeError(
            f"No recording at {path} and no API key set.\n"
            "Either add your key to the .env file (see README.md) and run again to make real calls, "
            "or get the course's recordings (data/llm_cassettes/)."
        )
    if mode == "auto":
        mode = "replay" if path.exists() else "record"
    _state.update(calls=0, budget=max_calls or int(os.environ.get("TUT_LLM_MAX_CALLS", "4")))
    if mode == "live":
        _install_pacing()
        _state.update(mode="live", path=None, cm=None)
        print("LLM mode: live (real calls, nothing recorded)")
        return None
    if mode not in ("replay", "record"):
        raise ValueError("TUT_LLM_MODE must be auto, replay, record or live")

    import vcr
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "record" and path.exists():
        path.unlink()  # record overwrites; vcrpy "all" would otherwise append to the old recording
    recorder = vcr.VCR(
        record_mode="none" if mode == "replay" else "all",
        match_on=["method", "scheme", "host", "port", "project_path"],
        filter_headers=SECRET_HEADERS,
        filter_query_parameters=SECRET_QUERY,
        before_record_response=_scrub_response,
        decode_compressed_response=True,
    )
    # The project id in the URL comes from the caller's account, so match on the path with it blanked.
    recorder.register_matcher("project_path", lambda r1, r2: re.sub(r"/projects/[^/]+/", "/projects/P/", r1.path) == re.sub(r"/projects/[^/]+/", "/projects/P/", r2.path))
    if mode == "record":
        _install_pacing()
    cm = recorder.use_cassette(str(path), allow_playback_repeats=False)
    cm.__enter__()
    _state.update(cm=cm, mode=mode, path=path)
    print(f"LLM mode: {mode} ({path.name})")


def stop() -> None:
    """Stop recording/replaying and save the recording (record mode)."""
    _remove_pacing()
    if _state.get("mode") in ("record", "live"):
        print(f"Real model calls in this lesson: {_state['calls']} (budget {_state['budget']})")
    cm = _state.get("cm")
    if cm is not None:
        cm.__exit__(None, None, None)
        if _state["mode"] == "record":
            print(f"Saved recording: {_state['path']}")
    _state.update(cm=None, mode=None, path=None)


def mode() -> str | None:
    """The current mode: replay, record, live, or None when not started."""
    return _state.get("mode")


def is_replaying() -> bool:
    return _state.get("mode") == "replay"


atexit.register(stop)
