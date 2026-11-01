import os
import pytest
import psycopg
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from api.main import app  # noqa: E402

TEST_LINE = 1974  # a store line used only by the write tests


@pytest.fixture(scope="session")
def client():
    # the "with" block runs the app startup, which opens the database pool
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    email = os.getenv("TEST_EMAIL")
    password = os.getenv("TEST_PASSWORD")
    if not email or not password:
        pytest.skip("TEST_EMAIL / TEST_PASSWORD not set in .env")
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
def clean_test_decisions():
    """Remove only the decisions that these tests create."""
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("DELETE FROM decisions WHERE comment = 'pytest'")
        conn.commit()