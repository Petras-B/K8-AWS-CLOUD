from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app.config import settings
from app.database import Base
from app import models  # noqa: F401  (import registers the tables on Base.metadata)

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: when migrations run inside the app's process (e.g. the
    # test suite), don't silence loggers the app already created
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Autogenerate compares this metadata (our models) against the live database
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database from settings and apply migrations."""
    # NullPool: a migration is a one-off run, so there is no point keeping connections pooled
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
