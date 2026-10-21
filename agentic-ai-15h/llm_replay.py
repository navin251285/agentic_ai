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
    llm_replay.stop()                        # saves the recording

Modes (environment variable TUT_LLM_MODE):
    auto    (default) replay if a recording exists; otherwise record if an API key is set
    replay  only replay; fail if a call was not recorded
    record  make real calls and overwrite the recording
    live    no recording at all: real calls every time (for learners using their own key)

Recordings live in ../data/llm_cassettes/<lesson>.yaml (relative to the notebook) and are
committed with the course. API keys, auth headers and cookies are stripped before saving.
Calls are matched by method + URL and replayed in the order they were recorded, so a
notebook must make its calls in the same order every run (it does, if run top to bottom).
"""
from __future__ import annotations

import atexit
import os
import re
from pathlib import Path

KEY_ENV_VARS = ["GOOGLE_CLOUD_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
SECRET_HEADERS = ["authorization", "x-api-key", "x-goog-api-key", "api-key", "openai-organization",
                  "openai-project", "cookie", "set-cookie", "x-goog-user-project", "proxy-authorization"]
SECRET_QUERY = ["key", "api_key", "apikey", "access_token"]

# Cloud project ids and regions are account settings: never saved in a recording, and ignored
# when matching, so a recording made with one project replays for anyone (or with no key).
PROJECT_PATH = re.compile(r"/projects/[^/]+/locations/[^/]+")
MODEL_PATH = re.compile(r"(/models/)[^/:]+")                   # the model id: a learner may override it
REGION_HOST = re.compile(r"^(?:[a-z]+-[a-z]+\d*-aiplatform|aiplatform\.[a-z]+\.rep)\.googleapis\.com$")
REGION_URL = re.compile(r"//(?:[a-z]+-[a-z]+\d*-aiplatform|aiplatform\.[a-z]+\.rep)\.googleapis\.com")

# A model call = one generation request to an LLM API (embeddings and local tool servers don't count).
LLM_CALL = re.compile(r"(:generateContent|:streamGenerateContent|/v1/messages\b|/chat/completions|/v1/responses\b|"
                      r"/api/chat\b|/api/generate\b|/v1/complete\b)")
MAX_CALLS = int(os.environ.get("TUT_LLM_MAX_CALLS", "8"))   # per notebook (standards/NOTEBOOK_RULES.md)


class CallBudgetExceeded(RuntimeError):
    pass


def is_llm_call(uri: str) -> bool:
    return bool(LLM_CALL.search(uri or ""))


_state: dict = {"cm": None, "mode": None, "path": None, "cassette": None}


def _norm_path(path: str) -> str:
    return MODEL_PATH.sub(r"\1M", PROJECT_PATH.sub("", path))


def _norm_host(host: str) -> str:
    return "aiplatform.googleapis.com" if REGION_HOST.match(host or "") else (host or "")


def _account_values() -> list[str]:
    """Literal account settings from .env that must never be saved (project id, account ids)."""
    vals = [os.environ.get(n, "") for n in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_QUOTA_PROJECT", "AWS_ACCOUNT_ID")]
    return [v for v in vals if len(v) >= 4 and not v.startswith("your")]


def _scrub_text(text: str) -> str:
    text = PROJECT_PATH.sub("/projects/PROJECT/locations/LOCATION", text)
    text = REGION_URL.sub("//aiplatform.googleapis.com", text)
    for v in _account_values():
        text = text.replace(v, "PROJECT")
    return text


def _scrub_request(request):
    cas = _state.get("cassette")
    if _state.get("mode") == "record" and cas is not None and is_llm_call(request.uri):
        made = sum(is_llm_call(r.uri) for r, _ in cas.data)
        if made >= MAX_CALLS:   # refuse before the request is sent: no spend beyond the budget
            raise CallBudgetExceeded(
                f"This notebook already made {made} model calls; the limit is {MAX_CALLS} per notebook. "
                "Combine prompts, reuse an earlier answer, or show one agent run instead of several.")
    request.uri = _scrub_text(request.uri)
    if isinstance(request.body, (bytes, str)) and request.body:
        b = request.body.decode("utf-8", "ignore") if isinstance(request.body, bytes) else request.body
        if PROJECT_PATH.search(b) or any(v in b for v in _account_values()):
            request.body = _scrub_text(b).encode("utf-8")
    return request


def _match_path(r1, r2):
    assert _norm_path(r1.path) == _norm_path(r2.path)


def _match_host(r1, r2):
    assert _norm_host(r1.host) == _norm_host(r2.host)


def cassette_dir() -> Path:
    return Path(os.environ.get("TUT_CASSETTE_DIR", Path.cwd().parent / "data" / "llm_cassettes"))


def _has_key() -> bool:
    try:
        import sys
        sys.path.insert(0, str(Path.cwd().parent))
        from tut_env import is_set
    except ImportError:  # older topic without tut_env.py
        return any(os.environ.get(k) for k in KEY_ENV_VARS) or bool(os.environ.get("TUT_LLM_LOCAL"))
    return any(is_set(k) for k in KEY_ENV_VARS + ["GOOGLE_CLOUD_PROJECT", "TUT_LLM_LOCAL"])


def _scrub_response(response):
    headers = response.get("headers", {})
    for h in list(headers):
        if h.lower() in SECRET_HEADERS:
            headers.pop(h)
    body = response.get("body", {})
    raw = body.get("string") if isinstance(body, dict) else None
    if raw:
        text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
        clean = _scrub_text(text)
        if clean != text:
            body["string"] = clean.encode("utf-8") if isinstance(raw, bytes) else clean
    return response


def start(lesson: str) -> None:
    """Start recording or replaying for this lesson (prints the mode in use; see mode())."""
    if _state["cm"] is not None:
        stop()
    mode = os.environ.get("TUT_LLM_MODE", "auto").lower()
    path = cassette_dir() / f"{lesson}.yaml"
    if mode == "auto":
        if path.exists():
            mode = "replay"
        elif _has_key():
            mode = "record"
        else:
            raise RuntimeError(
                f"No recording at {path} and no API key set.\n"
                "Either add your key to the .env file (see README.md) and run again to make real calls, "
                "or get the course's recordings (data/llm_cassettes/)."
            )
    if mode == "live":
        _state.update(mode="live", path=None, cm=None)
        print("LLM mode: live (real calls, nothing recorded)")
        return None
    if mode not in ("replay", "record"):
        raise ValueError("TUT_LLM_MODE must be auto, replay, record or live")

    import vcr
    path.parent.mkdir(parents=True, exist_ok=True)
    recorder = vcr.VCR(
        record_mode="none" if mode == "replay" else "all",
        match_on=["method", "scheme", "tut_host", "port", "tut_path"],
        filter_headers=SECRET_HEADERS,
        filter_query_parameters=SECRET_QUERY,
        before_record_request=_scrub_request,
        before_record_response=_scrub_response,
        decode_compressed_response=True,
    )
    recorder.register_matcher("tut_path", _match_path)
    recorder.register_matcher("tut_host", _match_host)
    cm = recorder.use_cassette(str(path), allow_playback_repeats=False)
    cassette = cm.__enter__()
    _state.update(cm=cm, mode=mode, path=path, cassette=cassette)
    print(f"LLM mode: {mode} ({path.name})")


def stop() -> None:
    """Stop recording/replaying and save the recording (record mode)."""
    cm = _state.get("cm")
    if cm is not None:
        cm.__exit__(None, None, None)
        if _state["mode"] == "record":
            print(f"Saved recording: {_state['path']}")
    _state.update(cm=None, mode=None, path=None, cassette=None)


def calls() -> int:
    """Model calls recorded (or replayed) so far in this notebook."""
    cas = _state.get("cassette")
    return sum(is_llm_call(r.uri) for r, _ in cas.data) if cas is not None else 0


def mode() -> str | None:
    """The current mode: replay, record, live, or None when not started."""
    return _state.get("mode")


def is_replaying() -> bool:
    return _state.get("mode") == "replay"


atexit.register(stop)
