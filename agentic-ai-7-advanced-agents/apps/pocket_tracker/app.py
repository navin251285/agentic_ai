"""Pocket Tracker: a tiny issue tracker (FastAPI + SQLite + server-rendered HTML).

Run:  uvicorn app:app --host 127.0.0.1 --port 8000
The database file comes from POCKET_TRACKER_DB (default: pocket_tracker.db here).
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import db

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")


@asynccontextmanager
async def lifespan(app):
    app.state.db = os.environ.get("POCKET_TRACKER_DB", str(HERE / "pocket_tracker.db"))
    db.init_db(app.state.db, HERE / "issues.json")
    yield


app = FastAPI(title="Pocket Tracker", lifespan=lifespan)


def found(request, issue_id):
    issue = db.get_issue(request.app.state.db, issue_id)
    if issue is None:
        raise HTTPException(404, f"No issue #{issue_id}")
    return issue


def back_to(issue_id):
    return RedirectResponse(f"/issues/{issue_id}", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return RedirectResponse("/issues", status_code=303)


@app.get("/issues")
def issue_list(request: Request, q: str = "", status: str = "", label: str = ""):
    path = request.app.state.db
    context = {"issues": db.list_issues(path, q, status, label), "open_count": db.count_open(path),
               "q": q, "status": status, "label": label, "labels": db.LABELS}
    return templates.TemplateResponse(request, "issues.html", context)


@app.get("/issues/new")
def new_issue_form(request: Request):
    return templates.TemplateResponse(request, "new_issue.html", {"labels": db.LABELS})


@app.post("/issues")
def create_issue(request: Request, title: str = Form(...), body: str = Form(""), label: str = Form("")):
    issue_id = db.create_issue(request.app.state.db, title, body, label)
    return back_to(issue_id)


@app.get("/issues/{issue_id}")
def issue_page(request: Request, issue_id: int):
    context = {"issue": found(request, issue_id), "labels": db.LABELS}
    return templates.TemplateResponse(request, "issue.html", context)


@app.post("/issues/{issue_id}/close")
def close_issue(request: Request, issue_id: int):
    found(request, issue_id)
    db.update_issue(request.app.state.db, issue_id, status="closed")
    return back_to(issue_id)


@app.post("/issues/{issue_id}/reopen")
def reopen_issue(request: Request, issue_id: int):
    issue = found(request, issue_id)
    db.update_issue(request.app.state.db, issue_id, status="open", label=issue["label"])
    return back_to(issue_id)


@app.post("/issues/{issue_id}/label")
def set_label(request: Request, issue_id: int, label: str = Form("")):
    found(request, issue_id)
    db.update_issue(request.app.state.db, issue_id, label=label)
    return back_to(issue_id)


@app.post("/issues/{issue_id}/comments")
def add_comment(request: Request, issue_id: int, body: str = Form(...)):
    found(request, issue_id)
    db.add_comment(request.app.state.db, issue_id, body)
    return back_to(issue_id)


@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"labels": db.LABELS})


@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"next": request.query_params.get("next", "/issues"),
                                                              "error": error})


# JSON API: the same data for scripts and agents.
@app.get("/api/issues")
def api_list(request: Request, q: str = "", status: str = "", label: str = ""):
    return db.list_issues(request.app.state.db, q, status, label)


@app.get("/api/issues/{issue_id}")
def api_issue(request: Request, issue_id: int):
    return found(request, issue_id)
