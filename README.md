# K8AWS

A REST API for managing projects and tasks, built with FastAPI and PostgreSQL. It is built to be deployed on Amazon EKS, with infrastructure provisioned by Terraform, CI/CD through GitHub Actions and monitoring in CloudWatch. The application layer is complete; the infrastructure is not yet built.

## Status

Done:

- Application: CRUD endpoints for projects and tasks, liveness and readiness endpoints, structured JSON logging
- Database migrations with Alembic
- Test suite (pytest) running against a real PostgreSQL database

Planned:

- Docker image
- Kubernetes manifests (Amazon EKS)
- Terraform for AWS infrastructure
- CI/CD with GitHub Actions
- Observability with CloudWatch

## Architecture

Diagram to be added at `docs/architecture.png`.

## Quickstart

Requires Python 3.11+ and a running PostgreSQL. The [full setup](docs/app-overview.md#local-development) covers starting PostgreSQL in Docker, the test database, and macOS/Linux commands.

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env   # then set DATABASE_URL
.\venv\Scripts\alembic.exe upgrade head
.\venv\Scripts\uvicorn.exe app.main:app --reload
```

The API runs at http://localhost:8000, with interactive docs at http://localhost:8000/docs.

## Documentation

- [Application overview](docs/app-overview.md): structure, API, configuration, design, migrations, testing, full local setup
- [Decisions](docs/decisions.md): technology choices and the alternatives considered
