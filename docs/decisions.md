### Backend Application Stack Decisions

To satisfy the requirements of a Kubernetes-ready REST API, the following Python libraries were selected after evaluating industry alternatives:

*   **API Framework: FastAPI (`fastapi`)**
    *   **Rationale:** Provides native asynchronous capabilities and automatically generates interactive OpenAPI documentation.
    *   **Rejected Alternatives:** *Flask* lacks native async support and requires multiple plugins for validation. *Django* is monolithic and too heavy for a containerized microservice.

*   **Web Server: Uvicorn (`uvicorn[standard]`)**
    *   **Rationale:** High-performance ASGI server required to execute the asynchronous FastAPI application and listen for network traffic.
    *   **Rejected Alternatives:** *Gunicorn* is a WSGI server that is synchronous by default; it cannot run async FastAPI natively without Uvicorn worker processes.

*   **Data & Config Validation: Pydantic (`pydantic`, `pydantic-settings`)**
    *   **Rationale:** Enforces strict data typing and implements 12-Factor App principles by safely parsing environment variables into application code.
    *   **Rejected Alternatives:** *Marshmallow* requires writing verbose, separate validation schemas instead of utilizing standard Python type hints.

*   **Database ORM: SQLAlchemy (`sqlalchemy`)**
    *   **Rationale:** Industry-standard ORM that maps tables and relationships to Python classes, keeping queries maintainable as the schema grows. Integrates with Alembic for versioned schema migrations. Parameterises queries by default, making SQL injection difficult to introduce accidentally.
    *   **Rejected Alternatives:** *Raw SQL* (with parameterised queries) is safe but becomes hard to maintain across joins, relationships and schema changes, with no migration tooling. *Peewee* has a smaller ecosystem and weaker support for complex relationships and migrations.

*   **Database Driver: Psycopg2 (`psycopg2-binary`)**
    *   **Rationale:** Mature, widely deployed PostgreSQL driver with a simple synchronous model. Because the driver is synchronous, API routes are defined as standard `def` functions, which FastAPI executes in a threadpool so blocking database calls do not stall the event loop. Horizontal scaling is handled by Kubernetes (more pods) rather than in-process concurrency.
    *   **Rejected Alternatives:** *asyncpg* offers higher throughput but requires SQLAlchemy's async engine and async sessions throughout, adding complexity with no meaningful benefit at this project's scale. *psycopg (v3)* supports both sync and async and is the likely upgrade path if async database access becomes necessary.

*   **Testing Suite: Pytest & HTTPX (`pytest`, `httpx`)**
    *   **Rationale:** Pytest provides fixtures for isolated test setup, such as overriding the database dependency. FastAPI's `TestClient` is built on HTTPX and calls the application in-process through the ASGI interface, so endpoint tests run without starting a server. This keeps tests fast and suitable for CI.
    *   **Rejected Alternatives:** *Requests* can only send real HTTP requests over the network, so tests would need a running server, making CI slower and more fragile. *unittest* works but is more verbose, and its fixture handling is less flexible.

    