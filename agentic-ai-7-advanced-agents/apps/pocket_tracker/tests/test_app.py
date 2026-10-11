def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_issue_list_shows_seeded_issues(client):
    page = client.get("/issues")
    assert page.status_code == 200
    assert "Login page broken" in page.text
    assert len(client.get("/api/issues").json()) == 10


def test_filter_by_status_and_label(client):
    closed = client.get("/api/issues", params={"status": "closed"}).json()
    assert [i["id"] for i in closed] == [10]
    features = client.get("/api/issues", params={"label": "feature"}).json()
    assert [i["id"] for i in features] == [8, 9]


def test_search_finds_matching_title(client):
    found = client.get("/api/issues", params={"q": "Login"}).json()
    assert [i["id"] for i in found] == [1]


def test_create_issue(client):
    reply = client.post("/issues", data={"title": "Export to CSV", "label": "feature"})
    assert reply.status_code == 200 and "Export to CSV" in reply.text   # redirected to the new issue
    assert client.get("/api/issues/11").json()["label"] == "feature"


def test_close_and_reopen(client):
    client.post("/issues/3/close")
    assert client.get("/api/issues/3").json()["status"] == "closed"
    client.post("/issues/3/reopen")
    assert client.get("/api/issues/3").json()["status"] == "open"


def test_change_label(client):
    client.post("/issues/1/label", data={"label": "docs"})
    issue = client.get("/api/issues/1").json()
    assert issue["label"] == "docs" and issue["status"] == "open"


def test_add_comment(client):
    client.post("/issues/2/comments", data={"body": "I can reproduce this."})
    assert [c["body"] for c in client.get("/api/issues/2").json()["comments"]] == ["I can reproduce this."]
    assert client.get("/api/issues", params={"q": "Search"}).json()[0]["comment_count"] == 1


def test_missing_issue_is_404(client):
    assert client.get("/issues/999").status_code == 404


def test_about_page(client):
    assert "Labels" in client.get("/about").text
