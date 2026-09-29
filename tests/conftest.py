import os

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


class TestSettings(BaseSettings):
    """TEST_DATABASE_URL from the environment (CI) or from .env (local)."""

    __test__ = False  # stop pytest trying to collect this class as a test

    TEST_DATABASE_URL: str
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


TEST_DATABASE_URL = TestSettings().TEST_DATABASE_URL

# Safety net: the suite runs migrations and writes data, so refuse anything that doesn't
# look like a throwaway test database (e.g. a dev or production URL pasted by mistake).
if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
    raise RuntimeError("TEST_DATABASE_URL must point at a database whose name contains 'test'")

# Point the app itself at the test database BEFORE importing it. app.config builds its
# settings at import time, and env vars take priority over .env, so nothing the app or
# Alembic does during tests can reach the dev database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    """Once per test run: build the schema with the real Alembic migrations, not create_all.

    That way the suite also proves the migrations produce a schema the app works with.
    """
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """A session inside a transaction that is rolled back after every test.

    The app calls commit(); with join_transaction_mode="create_savepoint" those commits
    only release SAVEPOINTs inside our outer transaction. Rolling the outer transaction
    back at the end erases everything the test wrote, so every test starts from an empty
    database without truncating or re-creating tables.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """TestClient whose get_db dependency yields the test's rolled-back session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------- Small helpers so tests read as behaviour, not setup ----------

@pytest.fixture
def make_project(client):
    def _make(name="Website", description=None):
        r = client.post("/projects", json={"name": name, "description": description})
        assert r.status_code == 201, r.text
        return r.json()

    return _make


@pytest.fixture
def make_task(client):
    def _make(project_id, title="Do something", status="todo"):
        r = client.post(
            "/tasks", json={"project_id": project_id, "title": title, "status": status}
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make
