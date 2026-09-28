from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# pool_pre_ping tests each pooled connection with a lightweight query before handing it out.
# If the DB restarted or a load balancer dropped an idle connection, the stale connection
# is discarded and replaced instead of failing the request.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

# A factory for sessions. Each request gets its own session (unit of work).
SessionLocal = sessionmaker(bind=engine, autoflush=False)

# Deterministic constraint names, so Alembic migrations can reference (and later drop)
# constraints by a predictable name instead of one Postgres generated.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: open a session for one request and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        # Runs after the response is produced, even if the route raised.
        # close() returns the connection to the pool and rolls back anything uncommitted.
        db.close()
