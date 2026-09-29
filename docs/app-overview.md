# Application Overview

A REST API for managing **Projects** and **Tasks**, built with FastAPI and PostgreSQL and designed to run on Kubernetes on AWS.

- A project has many tasks; a task belongs to exactly one project.
- Deleting a project deletes its tasks.
- A task's status is one of `todo`, `in_progress`, `done`.

For the reasoning behind library choices, see [decisions.md](decisions.md).

---

## Tech stack

| Component | Purpose |
|---|---|
| FastAPI | Web framework: routing, request validation, OpenAPI docs at `/docs` |
| Uvicorn | ASGI server that runs the application |
| Pydantic / pydantic-settings | Request/response validation; configuration from environment variables |
| SQLAlchemy 2.0 | ORM mapping Python classes to database tables |
| psycopg2 | PostgreSQL driver (synchronous) |
| Alembic | Versioned database schema migrations |
| Pytest + FastAPI TestClient | Test suite, calling the app in-process |

---

## Project structure

| Path | Responsibility |
|---|---|
| `app/config.py` | Loads all settings from environment variables or `.env` |
| `app/database.py` | Engine and connection pool, session factory, declarative `Base`, `get_db` dependency |
| `app/models.py` | SQLAlchemy models: `Project`, `Task`, `TaskStatus` |
| `app/schemas.py` | Pydantic schemas defining API input and output |
| `app/crud.py` | All database access. Routes never query the database directly |
| `app/main.py` | FastAPI application, routes, error mapping, health checks, request logging |
| `app/logging_config.py` | JSON log formatter writing to stdout |
| `alembic/`, `alembic.ini` | Migration environment and migration scripts |
| `tests/` | Test suite, run against a real PostgreSQL database |
| `.env.example` | Template for local environment variables |

### Request lifecycle

```
HTTP request
 → logging middleware starts a timer
 → route (main.py)
 → Pydantic schema validates the body/query (422 on failure)
 → get_db provides a database session
 → crud.py performs the database work
 → response serialised through a Read schema
 → middleware writes one JSON log line
```

---

## API

| Method | Path | Description | Responses |
|---|---|---|---|
| POST | `/projects` | Create a project | 201, 409 duplicate name, 422 |
| GET | `/projects` | List projects (`skip`, `limit`) | 200 |
| GET | `/projects/{id}` | Get a project | 200, 404 |
| GET | `/projects/{id}/tasks` | Get a project with its tasks | 200, 404 |
| PATCH | `/projects/{id}` | Partially update a project | 200, 404, 409, 422 |
| DELETE | `/projects/{id}` | Delete a project and its tasks | 204, 404 |
| POST | `/tasks` | Create a task | 201, 404 unknown project, 422 |
| GET | `/tasks` | List tasks (`status`, `skip`, `limit`) | 200, 422 invalid status |
| GET | `/tasks/{id}` | Get a task | 200, 404 |
| PATCH | `/tasks/{id}` | Partially update a task | 200, 404, 422 |
| DELETE | `/tasks/{id}` | Delete a task | 204, 404 |
| GET | `/healthz` | Liveness probe | 200 |
| GET | `/readyz` | Readiness probe | 200, 503 |

- `limit` accepts 1–1000 (default 100); `skip` must be ≥ 0.
- Updates use PATCH: only fields present in the request body are changed. Sending `null` for a required field returns 422.
- Interactive documentation is served at `/docs`.

---

## Configuration

All configuration comes from environment variables (or `.env` locally). Nothing is hardcoded, so the same image runs in every environment.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | – | PostgreSQL connection string |
| `LOG_LEVEL` | No | `INFO` | Root log level |
| `DB_POOL_SIZE` | No | `5` | Persistent connections per process |
| `DB_MAX_OVERFLOW` | No | `10` | Extra connections allowed above the pool size |
| `DB_CONNECT_TIMEOUT` | No | `3` | Seconds to wait when opening a connection |
| `TEST_DATABASE_URL` | Tests only | – | Database used by the test suite |

Maximum database connections = number of pods × (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`). Keep this below the database's `max_connections` when scaling.

---

## Design

### Database sessions: `get_db`

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- Each request gets its own session, which is always closed after the response, including when the route raises.
- Closing rolls back anything uncommitted and returns the connection to the pool.
- FastAPI caches the dependency per request, so all dependencies within one request share the same session.
- Tests replace it through `app.dependency_overrides`.

### Synchronous routes

psycopg2 is a blocking driver, so every route is a plain `def`. FastAPI runs `def` routes in a threadpool, keeping blocking database calls off the event loop. Declaring them `async def` would run blocking calls on the event loop and stall all concurrent requests. Horizontal scaling is handled by running more pods.

The request-logging middleware is `async` because it wraps the ASGI call chain; it does not access the database.

### Connection pool

- `pool_pre_ping=True` validates each connection before use, so connections broken by a database restart or failover are replaced transparently.
- `connect_timeout` bounds how long a new connection attempt can take, so readiness checks fail quickly when the database is unreachable.

### Health checks

| | `/healthz` (liveness) | `/readyz` (readiness) |
|---|---|---|
| Question | Is the process running and serving HTTP? | Can this instance handle traffic right now? |
| Check | None | `SELECT 1` against the database |
| Kubernetes action on failure | Restarts the container | Removes the pod from Service endpoints until it recovers |

Liveness deliberately does not depend on the database. A database outage should stop traffic to the pods, not restart them: restarting cannot fix the database and would cause every pod to reconnect at once when it returns.

### Models and schemas

- **Models** (`models.py`) describe database storage. **Schemas** (`schemas.py`) describe the API contract. They are kept separate so server-owned fields (`id`, `created_at`) cannot be set by clients and storage can change without changing the API.
- `Create` schemas exclude server-generated fields; `Update` schemas make every field optional; `Read` schemas use `from_attributes=True` to serialise ORM objects.
- Field length limits in schemas match column sizes, so oversized input returns 422 rather than a database error.

### Data model

**projects**

| Column | Type | Notes |
|---|---|---|
| `id` | integer | Primary key |
| `name` | varchar(100) | Unique, required |
| `description` | text | Optional |
| `created_at` | timestamptz | Set by the database |

**tasks**

| Column | Type | Notes |
|---|---|---|
| `id` | integer | Primary key |
| `project_id` | integer | FK → `projects.id`, `ON DELETE CASCADE`, indexed |
| `title` | varchar(200) | Required |
| `status` | `task_status` enum | `todo` / `in_progress` / `done`, default `todo`, indexed |
| `created_at` | timestamptz | Set by the database |

- `status` is a native PostgreSQL enum, so invalid values are rejected by the database itself.
- Timestamps are generated by PostgreSQL (`now()`), keeping them consistent across instances.
- Cascade delete is enforced by the database foreign key. The ORM relationship uses `passive_deletes=True` so SQLAlchemy relies on it instead of loading and deleting tasks individually.
- `project_id` and `status` are indexed because tasks are queried by project and filtered by status. PostgreSQL does not index foreign keys automatically.
- A naming convention on `Base.metadata` gives constraints predictable names (e.g. `uq_projects_name`, `fk_tasks_project_id_projects`), which migrations and error handling depend on.
- IDs come from sequences and may have gaps (for example after a failed insert). Do not rely on them being consecutive.

### Data access layer

- `crud.py` contains all queries. Lookups return `None` when a row is missing and the route returns 404.
- Business rule violations raise domain exceptions (`DuplicateProjectNameError`, `ProjectNotFoundError`), which exception handlers in `main.py` map to 409 and 404. `crud.py` has no knowledge of HTTP.
- Unique project names are enforced by the database constraint. `crud.py` catches the resulting `IntegrityError` and identifies it by constraint name. Checking for an existing name before inserting would be subject to a race between concurrent requests.
- `GET /projects/{id}/tasks` uses `joinedload` to load the project and its tasks in a single query with a join, avoiding a separate query for the tasks.

### Logging

Logs are written to stdout as one JSON object per line, for collection by the container runtime and shipping to CloudWatch.

```json
{"timestamp": "2026-09-29T11:19:27.745151+00:00", "level": "INFO", "logger": "app", "message": "request", "method": "GET", "path": "/tasks", "status_code": 200, "duration_ms": 3.07}
```

- Every request is logged with method, path, status code and duration.
- Fields passed via `extra={...}` become top-level JSON keys; exceptions include the traceback.
- Uvicorn's loggers use the same formatter. Its access log is disabled in favour of the request middleware.

---

## Migrations

The schema is managed exclusively by Alembic; the application never calls `create_all`.

- `alembic/env.py` reads `DATABASE_URL` from application settings; no connection string is stored in `alembic.ini`.
- Migration files are named `YYYY_MM_DD_HHMM-<revision>_<slug>.py`.
- Autogenerated migrations must be reviewed before committing. For example, autogenerate does not drop PostgreSQL enum types on downgrade, so this is added manually.

```
alembic upgrade head                              # apply all migrations
alembic downgrade -1                              # revert the latest migration
alembic revision --autogenerate -m "description"  # generate a new migration, then review it
alembic current                                   # show the applied revision
```

### Running migrations in production

Migrations run as a Kubernetes Job, once per deployment, before the Deployment is updated:

```
build and push image
 → apply migration Job (same image, command: alembic upgrade head)
 → wait for the Job to complete
 → roll out the Deployment
```

- Running once avoids concurrent migrations from multiple replicas.
- Using the application image keeps migration files in step with the code.
- A failed migration stops the deployment while the previous version keeps serving.
- The Job can use database credentials with schema-change privileges, while the application uses read/write-only credentials.
- The database is in private subnets, so migrations run inside the cluster rather than from the CI runner.

During a rolling update, old and new pods run against the new schema at the same time, so migrations must be backward compatible (expand/contract):

1. **Expand:** add new tables or nullable columns that the old code ignores.
2. **Deploy** code that uses the new structure.
3. **Contract:** remove old columns in a later release, once no running code uses them.

---

## Testing

The suite runs against a real PostgreSQL database, because behaviour the application relies on (enum types, `timestamptz`, constraint error reporting, cascade deletes) differs in SQLite.

- `TEST_DATABASE_URL` is read from the environment (CI) or `.env` (local). The suite refuses to run unless the database name contains `test`.
- `DATABASE_URL` is overridden with the test URL before the application is imported, so the tests cannot reach any other database.
- The schema is created by running `alembic upgrade head` once per session, so the tests also verify the migrations.

### Isolation

Each test runs inside a transaction that is rolled back afterwards:

```
connect → BEGIN
  session created with join_transaction_mode="create_savepoint"
  application commit()   → releases a SAVEPOINT; the outer transaction stays open
  application rollback() → rolls back to the SAVEPOINT
test ends → ROLLBACK → database returns to its empty state
```

The `get_db` dependency is overridden to yield this session, so the application runs unchanged against the rolled-back transaction.

### Coverage

| File | Covers |
|---|---|
| `test_health.py` | `/healthz` returns 200 and never requests a DB session; `/readyz` returns 200, or 503 with an unreachable database while `/healthz` stays 200 |
| `test_projects.py` | Project CRUD, validation, 404, 409 on create and rename, pagination, cascade delete, the project-with-tasks join, test isolation |
| `test_tasks.py` | Task CRUD, default status, status filter, moving tasks between projects, 404 for unknown projects and tasks, validation |

```
python -m pytest            # run all tests
python -m pytest -v         # verbose, one line per test
python -m pytest -k join    # run tests matching a keyword
```

---

## Local development

Prerequisites: Python 3.11+, Docker.

```bash
# 1. Start PostgreSQL
docker run -d --name k8aws-postgres \
  -e POSTGRES_PASSWORD=<password> -e POSTGRES_DB=api_db \
  -p 5432:5432 -v k8aws-pgdata:/var/lib/postgresql/data \
  --restart unless-stopped postgres:16
docker exec k8aws-postgres psql -U postgres -c "CREATE DATABASE api_db_test;"

# 2. Install dependencies
python -m venv venv
venv\Scripts\pip install -r requirements.txt      # Windows
# source venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

# 3. Configure
copy .env.example .env    # then set DATABASE_URL and TEST_DATABASE_URL

# 4. Create the schema
venv\Scripts\alembic upgrade head

# 5. Run the API (http://localhost:8000/docs)
venv\Scripts\uvicorn app.main:app --reload

# 6. Run the tests
venv\Scripts\python -m pytest
```

After the first run, `docker start k8aws-postgres` starts the existing database; data persists in the `k8aws-pgdata` volume.

---

## Repository conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `chore:`, `refactor:`, `ci:`).
- `.env` is never committed; `.env.example` documents every variable.
- `.gitattributes` enforces LF line endings for all text files, since the application runs in Linux containers.
