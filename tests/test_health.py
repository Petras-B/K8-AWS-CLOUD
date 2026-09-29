import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app


@pytest.fixture
def client_without_db():
    """A client whose get_db dependency fails loudly if anything asks for a session."""

    def no_db():
        raise AssertionError("this endpoint must not touch the database")
        yield  # pragma: no cover  (makes this a generator, like the real get_db)

    app.dependency_overrides[get_db] = no_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_dead_db():
    """A client whose sessions point at a port where no database is listening."""
    dead_engine = create_engine(
        "postgresql://nobody:nothing@127.0.0.1:1/nodb", connect_args={"connect_timeout": 1}
    )

    def dead_db():
        session = Session(bind=dead_engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = dead_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    dead_engine.dispose()


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_never_touches_database(client_without_db):
    # If /healthz depended on get_db, the override would raise and this would not be 200
    r = client_without_db.get("/healthz")
    assert r.status_code == 200


def test_readyz_ok_when_database_reachable(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readyz_503_when_database_unreachable(client_with_dead_db):
    r = client_with_dead_db.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"detail": "database unavailable"}


def test_healthz_still_ok_when_database_unreachable(client_with_dead_db):
    # The liveness/readiness split: a DB outage must not make Kubernetes restart the pod
    assert client_with_dead_db.get("/healthz").status_code == 200
