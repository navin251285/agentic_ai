# Pocket Tracker

A tiny issue tracker: FastAPI + SQLite + server-rendered HTML. It is the app the course's
browser agents drive and the repo its coding agents fix. Its open bugs are listed in `issues.json`.

## Files
- `app.py` — routes: HTML pages, form posts, a small JSON API under `/api`
- `db.py` — SQLite storage, plain SQL
- `templates/` — Jinja2 pages (labelled forms and buttons)
- `issues.json` — the issue backlog; also seeds an empty database
- `tests/` — the pytest suite (`python -m pytest -q`)

## Run
```
uvicorn app:app --host 127.0.0.1 --port 8000
```
Set `POCKET_TRACKER_DB` to choose the database file (default `pocket_tracker.db` here).
A new database is seeded from `issues.json`; delete the file to start again.

## Pages
| URL | What |
|---|---|
| `/issues?q=&status=&label=` | issue list with search and filters |
| `/issues/new` | new-issue form |
| `/issues/{id}` | one issue: close/reopen, label, comments |
| `/about` | about page |
| `/health` | `{"status": "ok"}` |
| `/api/issues`, `/api/issues/{id}` | the same data as JSON |

## Working on a copy
Lessons never change this folder. Each one copies it to a scratch folder, makes that a git
repo with one commit, and resets with `git reset --hard && git clean -fdx`.
