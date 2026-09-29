# Application Overview

A REST API for managing **Projects** and **Tasks**, built with FastAPI and PostgreSQL. It is designed to be deployed on Kubernetes on AWS; that infrastructure is planned and not yet built.

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

All configuration comes from environment variables (or `.env` locally). Nothing is hardcoded, so the same build can run in any environment by changing only its environment variables.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | – | PostgreSQL connection string |
| `LOG_LEVEL` | No | `INFO` | Root log level |
| `DB_POOL_SIZE` | No | `5` | Persistent connections per process |
| `DB_MAX_OVERFLOW` | No | `10` | Extra connections allowed above the pool size |
| `DB_CONNECT_TIMEOUT` | No | `3` | Seconds to wait when opening a connection |
| `TEST_DATABASE_URL` | Tests only | – | Database used by the test suite |

Maximum database connections = number of application instances × (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`). Keep this below the database's `max_connections`; this will matter when the application is scaled out as multiple pods on Kubernetes (planned).

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

psycopg2 is a blocking driver, so every route is a plain `def`. FastAPI runs `def` routes in a threadpool, keeping blocking database calls off the event loop. Declaring them `async def` would run blocking calls on the event loop and stall all concurrent requests. Horizontal scaling is intended to come from running more instances (pods on Kubernetes, planned) rather than from in-process concurrency.

The request-logging middleware is `async` because it wraps the ASGI call chain; it does not access the database.

### Connection pool

- `pool_pre_ping=True` validates each connection before use, so connections broken by a database restart or failover are replaced transparently.
- `connect_timeout` bounds how long a new connection attempt can take, so readiness checks fail quickly when the database is unreachable.

### Health checks

Both endpoints are implemented. They are intended as Kubernetes liveness and readiness probes; the probe configuration will be added with the Kubernetes manifests (planned).

| | `/healthz` (liveness) | `/readyz` (readiness) |
|---|---|---|
| Question | Is the process running and serving HTTP? | Can this instance handle traffic right now? |
| Check | None | `SELECT 1` against the database |
| Kubernetes action on failure, once probes are configured | Restarts the container | Removes the pod from Service endpoints until it recovers |

Liveness deliberately does not depend on the database. Once the application runs on Kubernetes, a database outage should stop traffic to the pods, not restart them: restarting cannot fix the database and would cause every pod to reconnect at once when it returns.

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

Logs are written to stdout as one JSON object per line, so they can be collected and shipped to CloudWatch. Log shipping to CloudWatch is planned for the observability phase.

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

### Running migrations in production (planned)

None of this deployment pipeline exists yet. Migrations are currently run by hand with `alembic upgrade head`.

Migrations will run as a Kubernetes Job, once per deployment, before the Deployment is updated:

```
build and push image
 → apply migration Job (same image, command: alembic upgrade head)
 → wait for the Job to complete
 → roll out the Deployment
```

- Running once will avoid concurrent migrations from multiple replicas.
- Using the application image will keep migration files in step with the code.
- A failed migration will stop the deployment while the previous version keeps serving.
- The Job will use database credentials with schema-change privileges, while the application will use read/write-only credentials.
- The database will be in private subnets, so migrations will run inside the cluster rather than from the CI runner.

During a rolling update, old and new pods will run against the new schema at the same time, so migrations must be backward compatible (expand/contract). This rule applies to every migration written from now on:

1. **Expand:** add new tables or nullable columns that the old code ignores.
2. **Deploy** code that uses the new structure.
3. **Contract:** remove old columns in a later release, once no running code uses them.

---

## Testing

The suite runs against a real PostgreSQL database, because behaviour the application relies on (enum types, `timestamptz`, constraint error reporting, cascade deletes) differs in SQLite.

- `TEST_DATABASE_URL` is read from the environment or, locally, from `.env`. Reading it from the environment is what will let the planned CI pipeline point the tests at a PostgreSQL service container. The suite refuses to run unless the database name contains `test`.
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

Prerequisites: Python 3.11+ and Docker (Docker Desktop on Windows and macOS). Run all commands from the repository root.

Each step shows **PowerShell** (Windows) first, then **bash** (macOS/Linux). The commands call the tools inside `venv` directly, so the virtual environment does not need to be activated.

### 1. Start PostgreSQL

Choose a password; it goes into `.env` in step 3.

PowerShell:

```powershell
$pgPassword = "choose-a-password"
docker run -d --name k8aws-postgres -e POSTGRES_PASSWORD=$pgPassword -e POSTGRES_DB=api_db -p 5432:5432 -v k8aws-pgdata:/var/lib/postgresql/data --restart unless-stopped postgres:16
```

bash:

```bash
PG_PASSWORD="choose-a-password"
docker run -d --name k8aws-postgres -e POSTGRES_PASSWORD="$PG_PASSWORD" -e POSTGRES_DB=api_db -p 5432:5432 -v k8aws-pgdata:/var/lib/postgresql/data --restart unless-stopped postgres:16
```

### 2. Create the test database

Wait until PostgreSQL reports `accepting connections` (a few seconds on first start), then create the test database. These commands are identical in PowerShell and bash:

```
docker exec k8aws-postgres pg_isready -U postgres
docker exec k8aws-postgres psql -U postgres -c "CREATE DATABASE api_db_test;"
```

### 3. Configure

Copy the template.

PowerShell:

```powershell
Copy-Item .env.example .env
```

bash:

```bash
cp .env.example .env
```

Then edit `.env` so both URLs use the password from step 1:

```
DATABASE_URL=postgresql+psycopg2://postgres:choose-a-password@localhost:5432/api_db
TEST_DATABASE_URL=postgresql+psycopg2://postgres:choose-a-password@localhost:5432/api_db_test
```

- The `+psycopg2` part selects the installed driver explicitly. SQLAlchemy 2.1 and later default plain `postgresql://` URLs to a different driver (psycopg 3), which is not installed.
- If the password contains characters such as `@`, `:`, `/` or `%`, URL-encode them in these URLs (for example `@` becomes `%40`).

### 4. Install dependencies

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

bash:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

If `python` is not found on Windows, use `py` instead.

### 5. Create the schema

PowerShell:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

bash:

```bash
venv/bin/alembic upgrade head
```

### 6. Run the API

The API is served at http://localhost:8000, with interactive documentation at http://localhost:8000/docs. Stop it with `Ctrl+C`.

PowerShell:

```powershell
.\venv\Scripts\uvicorn.exe app.main:app --reload
```

bash:

```bash
venv/bin/uvicorn app.main:app --reload
```

### 7. Run the tests

PowerShell:

```powershell
.\venv\Scripts\python.exe -m pytest
```

bash:

```bash
venv/bin/python -m pytest
```

### Later sessions

The container, its data (in the `k8aws-pgdata` volume) and `venv` persist. Start Docker Desktop, then:

```
docker start k8aws-postgres
```

---

## Repository conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `chore:`, `refactor:`, `ci:`).
- `.env` is never committed; `.env.example` documents every variable.
- `.gitattributes` enforces LF line endings for all text files, since the application will run in Linux containers.
