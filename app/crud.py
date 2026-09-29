"""All database access lives here. Routes call these functions and never query directly.

Lookups return None when a row doesn't exist, and the route decides that means 404.
Rule violations raise the domain exceptions below, which main.py maps to HTTP status codes,
so this module knows nothing about HTTP.
"""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import models, schemas


class DuplicateProjectNameError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Project with name '{name}' already exists")


class ProjectNotFoundError(Exception):
    def __init__(self, project_id: int):
        super().__init__(f"Project {project_id} not found")


def _commit(db: Session, name: str | None = None) -> None:
    """Commit, translating the unique-name violation into a domain error.

    The unique constraint is the source of truth: checking "does this name exist?" first
    would race with a concurrent insert, so we let Postgres enforce it and catch the error.
    """
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # Named by the naming convention in database.py, so we can match it reliably
        if getattr(e.orig.diag, "constraint_name", None) == "uq_projects_name":
            raise DuplicateProjectNameError(name) from e
        raise


def _ensure_project_exists(db: Session, project_id: int) -> None:
    if db.get(models.Project, project_id) is None:
        raise ProjectNotFoundError(project_id)


# ---------- Projects ----------

def get_project(db: Session, project_id: int) -> models.Project | None:
    return db.get(models.Project, project_id)


def get_project_with_tasks(db: Session, project_id: int) -> models.Project | None:
    # joinedload: one query with a LEFT OUTER JOIN, instead of 1 query for the project
    # plus a second lazy query when .tasks is accessed during serialisation.
    stmt = (
        select(models.Project)
        .options(joinedload(models.Project.tasks))
        .where(models.Project.id == project_id)
    )
    # unique() is required with joinedload on a collection: the join returns one row per task
    return db.scalars(stmt).unique().one_or_none()


def list_projects(db: Session, skip: int = 0, limit: int = 100) -> Sequence[models.Project]:
    stmt = select(models.Project).order_by(models.Project.id).offset(skip).limit(limit)
    return db.scalars(stmt).all()


def create_project(db: Session, data: schemas.ProjectCreate) -> models.Project:
    project = models.Project(**data.model_dump())
    db.add(project)
    _commit(db, data.name)
    db.refresh(project)  # load server-generated values (id, created_at)
    return project


def update_project(
    db: Session, project: models.Project, data: schemas.ProjectUpdate
) -> models.Project:
    # exclude_unset: only fields the client actually sent, so omitted fields stay unchanged
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    _commit(db, changes.get("name"))
    db.refresh(project)
    return project


def delete_project(db: Session, project: models.Project) -> None:
    # Tasks are removed by ON DELETE CASCADE in the database
    db.delete(project)
    db.commit()


# ---------- Tasks ----------

def get_task(db: Session, task_id: int) -> models.Task | None:
    return db.get(models.Task, task_id)


def list_tasks(
    db: Session,
    status: models.TaskStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[models.Task]:
    stmt = select(models.Task).order_by(models.Task.id)
    if status is not None:
        stmt = stmt.where(models.Task.status == status)
    return db.scalars(stmt.offset(skip).limit(limit)).all()


def create_task(db: Session, data: schemas.TaskCreate) -> models.Task:
    _ensure_project_exists(db, data.project_id)
    task = models.Task(**data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: models.Task, data: schemas.TaskUpdate) -> models.Task:
    changes = data.model_dump(exclude_unset=True)
    if "project_id" in changes:
        _ensure_project_exists(db, changes["project_id"])
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: models.Task) -> None:
    db.delete(task)
    db.commit()
