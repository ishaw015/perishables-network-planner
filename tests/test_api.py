from tests.conftest import TEST_LINE

# ---------- health and auth ----------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_plans_requires_login(client):
    assert client.get("/plans").status_code == 401


def test_bad_token_rejected(client):
    r = client.get("/plans", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_wrong_password_rejected(client):
    r = client.post("/auth/login", data={"username": "nobody@example.com", "password": "wrong"})
    assert r.status_code in (400, 401)


def test_me(client, auth):
    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    assert "email" in r.json()


# ---------- reading plans ----------

def test_list_plans(client, auth):
    r = client.get("/plans", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_summary_matches_example_plan(client, auth):
    s = client.get("/plans/1/summary", headers=auth).json()
    assert s["lines"] == 4529
    assert s["orders"] + s["holds"] + s["warehouse_short"] == s["lines"]
    assert s["orders"] == 4279
    assert s["warehouse_pools"] == 60
    assert s["warehouse_pools_short"] == 3


def test_summary_unknown_plan(client, auth):
    assert client.get("/plans/999999/summary", headers=auth).status_code == 404


def test_store_lines_paging(client, auth):
    r = client.get("/plans/1/store-lines", params={"limit": 5}, headers=auth)
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_store_lines_status_filter(client, auth):
    r = client.get("/plans/1/store-lines",
                   params={"status": "warehouse short", "limit": 50}, headers=auth)
    assert r.status_code == 200
    rows = r.json()
    assert rows and all(x["status"] == "warehouse short" for x in rows)


def test_store_lines_city_filter(client, auth):
    rows = client.get("/plans/1/store-lines",
                      params={"city_id": 12, "limit": 50}, headers=auth).json()
    assert rows and all(x["city_id"] == 12 for x in rows)


def test_limit_too_large_rejected(client, auth):
    r = client.get("/plans/1/store-lines", params={"limit": 201}, headers=auth)
    assert r.status_code == 422


def test_bad_sort_value_rejected(client, auth):
    r = client.get("/plans/1/store-lines", params={"sort": "drop table"}, headers=auth)
    assert r.status_code == 422


def test_warehouse_lines(client, auth):
    r = client.get("/plans/1/warehouse-lines", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) == 60


# ---------- decisions: validation ----------

def test_decision_requires_login(client):
    r = client.post(f"/store-lines/{TEST_LINE}/decision", json={"action": "approve"})
    assert r.status_code == 401


def test_decision_edit_needs_quantity(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "edit", "comment": "pytest"}, headers=auth)
    assert r.status_code == 422


def test_decision_approve_rejects_quantity(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "approve", "final_qty": 10, "comment": "pytest"},
                    headers=auth)
    assert r.status_code == 422


def test_decision_unknown_action(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "delete", "comment": "pytest"}, headers=auth)
    assert r.status_code == 422


def test_decision_quantity_over_cap(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "edit", "final_qty": 100000, "comment": "pytest"},
                    headers=auth)
    assert r.status_code == 422


def test_decision_negative_quantity(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "edit", "final_qty": -5, "comment": "pytest"},
                    headers=auth)
    assert r.status_code == 422


def test_decision_unknown_line(client, auth):
    r = client.post("/store-lines/99999999/decision",
                    json={"action": "approve", "comment": "pytest"}, headers=auth)
    assert r.status_code == 404


# ---------- decisions: full flow (writes one row, removed at the end) ----------

def test_decision_flow(client, auth):
    r = client.post(f"/store-lines/{TEST_LINE}/decision",
                    json={"action": "edit", "final_qty": 40, "comment": "pytest"},
                    headers=auth)
    assert r.status_code == 201
    assert r.json()["action"] == "edit"
    assert r.json()["final_qty"] == 40

    # the line now shows the decision
    rows = client.get("/plans/1/store-lines",
                      params={"city_id": 12, "limit": 200}, headers=auth).json()
    mine = [x for x in rows if x["id"] == TEST_LINE]
    if mine:  # line 1974 is in city 12
        assert mine[0]["decision_action"] == "edit"

    # and drops out of the undecided list
    und = client.get("/plans/1/store-lines",
                     params={"city_id": 12, "undecided": "true", "limit": 200},
                     headers=auth).json()
    assert TEST_LINE not in [x["id"] for x in und]