"""Every setting a lesson needs comes from the topic's .env file, never from the notebook.

Copied into every topic folder. Notebooks use it like this:

    import sys; sys.path.insert(0, "..")
    from tut_env import env, is_set
    project = env("GOOGLE_CLOUD_PROJECT")             # required: clear error if not set
    url = env("QDRANT_URL", "http://localhost:6333")   # optional, with a local default

What goes in .env (one place, never committed): API keys, cloud project ids, regions,
buckets, service-account files, database users and passwords, tokens, endpoints of real
services, account / tenant / subscription ids, model ids you want to override.

Lookup order: the real environment → topic/.env → topic/.env.example.
- A placeholder ("your-…", "changeme", "replace-me", "<…>", "xxx", "todo", empty) counts as NOT set,
  wherever it appears, and is never copied into the environment (so SDKs don't pick it up).
- .env.example values are used as defaults only for harmless local-lab settings. A secret-looking
  name (…KEY, …TOKEN, …SECRET, …PASSWORD, …CREDENTIALS, …PROJECT, …ACCOUNT…) falls back to
  .env.example only when its line or the comment above it says "lab" (e.g. the password of a
  throwaway local Postgres container: "# lab-only password for the local container").
- load() also exports those values into os.environ, so `docker compose` started from the notebook
  sees exactly what Python sees.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_MISSING = object()
PLACEHOLDER = re.compile(r"^(your[-_ ].*|your|change[-_]?me.*|replace[-_]?me.*|replace[-_ ]this.*|<.*>|x{3,}|todo|tbd|\.\.\.|)$", re.I)
SECRETISH = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL|PRIVATE|PROJECT|ACCOUNT|SUBSCRIPTION|TENANT)", re.I)
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()   # "a #comment" → a ; "a#b" stays


def _read(path: Path, with_lab: bool = False):
    """{NAME: value} from a dotenv file (with_lab: {NAME: (value, marked_lab)})."""
    out: dict = {}
    if not path.exists():
        return out
    comment = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            comment = ""
            continue
        if s.startswith("#"):
            comment = s
            continue
        m = LINE.match(line)
        if not m:
            continue
        v = _value(m.group(2))
        lab = bool(re.search(r"\blab\b", comment + " " + line, re.I))
        out[m.group(1)] = (v, lab) if with_lab else v
        comment = ""
    return out


def _examples() -> dict:
    found = {}
    for f in [HERE / ".env.example", *sorted((HERE / ".staging").glob("*/env.example"))]:
        for k, v in _read(f, with_lab=True).items():
            found.setdefault(k, v)
    return found


def _usable(v) -> bool:
    return v is not None and not PLACEHOLDER.match(v.strip())


def _lookup(name: str):
    if _usable(os.environ.get(name)):
        return os.environ[name]
    v = _read(HERE / ".env").get(name)
    if _usable(v):
        return v
    ex = _examples().get(name)
    if ex and _usable(ex[0]) and (not SECRETISH.search(name) or ex[1]):
        return ex[0]
    return None


def load() -> None:
    """Put usable settings from .env (and lab defaults from .env.example) into os.environ.
    Real environment variables win; placeholders are never exported."""
    names = set(_read(HERE / ".env")) | set(_examples())
    for n in names:
        if not _usable(os.environ.get(n)):
            v = _lookup(n)
            if v is not None:
                os.environ[n] = v


def is_set(name: str) -> bool:
    return _lookup(name) is not None


def env(name: str, default=_MISSING) -> str:
    """The value of setting `name` from the environment or the topic's .env file."""
    v = _lookup(name)
    if v is not None:
        return v
    if default is not _MISSING:
        return default
    raise RuntimeError(
        f"{name} is not set.\n"
        f"Add it to {HERE / '.env'} (copy .env.example to .env and fill it in), e.g.\n"
        f"  {name}=...\n"
        "then restart the kernel. See README.md, 'Keys and settings'."
    )


if __name__ == "__main__":  # python tut_env.py  → which settings are filled in
    names = list(_examples())
    for n in names:
        print(f"{'ok ' if is_set(n) else '-- '} {n}")
    if not names:
        print("no .env.example in", HERE)
