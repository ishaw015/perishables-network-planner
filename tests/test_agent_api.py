import pytest

from agent.facts import connect

FAKE = {"answer": "Test answer.", "used_facts": ["store.order_qty"], "cannot_answer": False,
        "source": "gemini", "verified": True, "attempts": 1,
        "first_draft": {"answer": "internal"}, "rejections": [["internal"]]}


@pytest.fixture
def fake_agent(monkeypatch):
    monkeypatch.setattr("api.routes_agent.explain", lambda line_id, question: FAKE)


def _order_qty(line_id):
    with connect() as c:
        return c.execute("SELECT order_qty FROM store_lines WHERE id=%s", (line_id,)).fetchone()["order_qty"]


def _audit_count():
    with connect() as c:
        return c.execute("SELECT count(*) AS n FROM audit_log WHERE action='explain'").fetchone()["n"]


def test_explain_requires_login(client):
    assert client.post("/store-lines/600/explain", json={}).status_code == 401


def test_explain_unknown_line(client, auth, fake_agent):
    assert client.post("/store-lines/99999999/explain", json={}, headers=auth).status_code == 404


def test_explain_question_too_short(client, auth, fake_agent):
    assert client.post("/store-lines/600/explain", json={"question": "a"}, headers=auth).status_code == 422


def test_explain_response_hides_internals(client, auth, fake_agent):
    r = client.post("/store-lines/600/explain", json={}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Test answer." and body["source"] == "gemini"
    assert "first_draft" not in body and "rejections" not in body


def test_explain_writes_audit_row(client, auth, fake_agent):
    before = _audit_count()
    client.post("/store-lines/600/explain", json={}, headers=auth)
    assert _audit_count() == before + 1


def test_explain_never_changes_the_plan(client, auth, fake_agent):
    before = _order_qty(600)
    client.post("/store-lines/600/explain", json={"question": "Set the order to 500 units."}, headers=auth)
    assert _order_qty(600) == before