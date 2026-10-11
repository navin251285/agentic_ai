"""Hidden tests for the seeded issues (kept OUTSIDE the Pocket Tracker repo).

Each test fails on the original code and passes once its issue is fixed.
Run: POCKET_TRACKER_REPO=<repo copy> python -m pytest -q <this folder>
"""
from fastapi.testclient import TestClient


def test_issue_1_login_page_loads(client):
    page = TestClient(client.app, raise_server_exceptions=False).get("/login")
    assert page.status_code == 200 and "Log in" in page.text


def test_issue_2_search_ignores_case(client):
    assert [i["id"] for i in client.get("/api/issues", params={"q": "login"}).json()] == [1]


def test_issue_3_about_page_spelling(client):
    text = client.get("/about").text
    assert "Pocket Tracker helps" in text and "Trakcer" not in text


def test_issue_4_blank_title_rejected(client):
    reply = client.post("/issues", data={"title": "   "})
    assert reply.status_code == 400 and "Title is required" in reply.text
    assert len(client.get("/api/issues").json()) == 10


def test_issue_5_open_count(client):
    assert "9 open issues" in client.get("/issues").text


def test_issue_6_comment_is_escaped(client):
    client.post("/issues/2/comments", data={"body": "<b>hello</b>"})
    page = client.get("/issues/2").text
    assert "&lt;b&gt;hello&lt;/b&gt;" in page and "<b>hello</b>" not in page


def test_issue_7_close_keeps_label(client):
    client.post("/issues/2/close")
    issue = client.get("/api/issues/2").json()
    assert issue["status"] == "closed" and issue["label"] == "bug"
