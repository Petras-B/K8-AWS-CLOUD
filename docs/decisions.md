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
    *   **Rationale:** Industry-standard Object-Relational Mapper that abstracts raw SQL into Python objects, preventing SQL injection.
    *   **Rejected Alternatives:** *Raw SQL* is highly vulnerable to injection attacks and difficult to maintain. *Peewee* lacks enterprise-grade relationship handling.

*   **Database Driver: Psycopg2 (`psycopg2-binary`)**
    *   **Rationale:** The required PostgreSQL adapter that establishes the physical TCP connection between the application and the database.
    *   **Rejected Alternatives:** N/A (Standard required driver for Postgres in Python).

*   **Testing Suite: Pytest & HTTPX (`pytest`, `httpx`)**
    *   **Rationale:** Combines a lightweight test runner with an asynchronous HTTP client to simulate live API requests for CI/CD.
    *   **Rejected Alternatives:** *Requests* cannot properly execute asynchronous requests against local FastAPI endpoints.