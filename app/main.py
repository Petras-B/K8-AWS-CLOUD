import logging
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import settings
from app.database import get_db
from app.logging_config import setup_logging

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("app")

app = FastAPI(title=settings.APP_NAME)

# Every route that needs the database declares `db: DbSession`; FastAPI calls get_db per request
DbSession = Annotated[Session, Depends(get_db)]


# ---------- Cross-cutting ----------

# Middleware must be async (it wraps the ASGI call chain). That's fine: it never touches
# the database, it only times the request and writes one log line.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed",
            extra={"method": request.method, "path": request.url.path},
        )
        raise
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return response


# crud raises domain errors; these translate them to HTTP in one place
@app.exception_handler(crud.DuplicateProjectNameError)
def duplicate_name_handler(request: Request, exc: crud.DuplicateProjectNameError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(crud.ProjectNotFoundError)
def project_not_found_handler(request: Request, exc: crud.ProjectNotFoundError):
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


# ---------- Health ----------

@app.get("/healthz", tags=["health"])
def healthz():
    """Liveness: is this process alive and able to serve HTTP? Never touches the DB."""
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
def readyz(db: DbSession):
    """Readiness: can this pod do useful work right now? Checks the DB with SELECT 1."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("readiness check failed: database unreachable", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        )
    return {"status": "ready"}


# ---------- Lookup dependencies ----------

def project_or_404(project_id: int, db: DbSession) -> models.Project:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def task_or_404(task_id: int, db: DbSession) -> models.Task:
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


ProjectDep = Annotated[models.Project, Depends(project_or_404)]
TaskDep = Annotated[models.Task, Depends(task_or_404)]

Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=1000)]


# ---------- Projects ----------
# All routes are plain `def`: psycopg2 blocks, so FastAPI runs them in its threadpool
# instead of on the event loop.

@app.post(
    "/projects",
    response_model=schemas.ProjectRead,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(data: schemas.ProjectCreate, db: DbSession):
    return crud.create_project(db, data)


@app.get("/projects", response_model=list[schemas.ProjectRead], tags=["projects"])
def list_projects(db: DbSession, skip: Skip = 0, limit: Limit = 100):
    return crud.list_projects(db, skip, limit)


@app.get("/projects/{project_id}", response_model=schemas.ProjectRead, tags=["projects"])
def get_project(project: ProjectDep):
    return project


@app.get(
    "/projects/{project_id}/tasks", response_model=schemas.ProjectWithTasks, tags=["projects"]
)
def get_project_with_tasks(project_id: int, db: DbSession):
    project = crud.get_project_with_tasks(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@app.patch("/projects/{project_id}", response_model=schemas.ProjectRead, tags=["projects"])
def update_project(project: ProjectDep, data: schemas.ProjectUpdate, db: DbSession):
    return crud.update_project(db, project, data)


@app.delete(
    "/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["projects"]
)
def delete_project(project: ProjectDep, db: DbSession):
    crud.delete_project(db, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Tasks ----------

@app.post(
    "/tasks",
    response_model=schemas.TaskRead,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
)
def create_task(data: schemas.TaskCreate, db: DbSession):
    return crud.create_task(db, data)


@app.get("/tasks", response_model=list[schemas.TaskRead], tags=["tasks"])
def list_tasks(
    db: DbSession,
    status: models.TaskStatus | None = None,
    skip: Skip = 0,
    limit: Limit = 100,
):
    return crud.list_tasks(db, status, skip, limit)


@app.get("/tasks/{task_id}", response_model=schemas.TaskRead, tags=["tasks"])
def get_task(task: TaskDep):
    return task


@app.patch("/tasks/{task_id}", response_model=schemas.TaskRead, tags=["tasks"])
def update_task(task: TaskDep, data: schemas.TaskUpdate, db: DbSession):
    return crud.update_task(db, task, data)


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["tasks"])
def delete_task(task: TaskDep, db: DbSession):
    crud.delete_task(db, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
