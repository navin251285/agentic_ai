"""SQLite storage for Pocket Tracker. One connection per call; plain SQL."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LABELS = ["bug", "docs", "feature"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    issue_id INTEGER NOT NULL REFERENCES issues(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def connect(path):
    """Open the database, commit on success, always close."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path, seed_file):
    """Create the tables; load issues.json if the database has no issues yet."""
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            for issue in json.loads(Path(seed_file).read_text()):
                conn.execute(
                    "INSERT INTO issues (id, title, body, label, status, created_at) "
                    "VALUES (:id, :title, :body, :label, :status, :created_at)", issue)


def list_issues(path, q="", status="", label=""):
    sql = ("SELECT issues.*, COUNT(comments.id) AS comment_count FROM issues "
           "LEFT JOIN comments ON comments.issue_id = issues.id WHERE 1 = 1")
    params = []
    if q:
        sql += " AND instr(issues.title, ?) > 0"
        params.append(q)
    if status:
        sql += " AND issues.status = ?"
        params.append(status)
    if label:
        sql += " AND issues.label = ?"
        params.append(label)
    sql += " GROUP BY issues.id ORDER BY issues.id"
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def count_open(path):
    with connect(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
        closed = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'Closed'").fetchone()[0]
    return total - closed


def get_issue(path, issue_id):
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if row is None:
            return None
        issue = dict(row)
        issue["comments"] = [dict(c) for c in conn.execute(
            "SELECT * FROM comments WHERE issue_id = ? ORDER BY id", (issue_id,))]
    return issue


def create_issue(path, title, body="", label=""):
    with connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO issues (title, body, label, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (title, body, label, now()))
        return cur.lastrowid


def update_issue(path, issue_id, status=None, label=""):
    """Change an issue's status and/or label."""
    with connect(path) as conn:
        conn.execute(
            "UPDATE issues SET status = COALESCE(?, status), label = ? WHERE id = ?",
            (status, label, issue_id))


def add_comment(path, issue_id, body):
    with connect(path) as conn:
        conn.execute("INSERT INTO comments (issue_id, body, created_at) VALUES (?, ?, ?)",
                     (issue_id, body, now()))
