def test_create_project(client):
    r = client.post("/projects", json={"name": "Website", "description": "Company site"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Website"
    assert body["description"] == "Company site"
    assert isinstance(body["id"], int)
    assert body["created_at"]  # set by Postgres


def test_create_project_description_optional(client):
    r = client.post("/projects", json={"name": "Website"})
    assert r.status_code == 201
    assert r.json()["description"] is None


def test_create_project_duplicate_name_409(client, make_project):
    make_project(name="Website")
    r = client.post("/projects", json={"name": "Website"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_create_project_invalid_name_422(client):
    assert client.post("/projects", json={"name": ""}).status_code == 422
    assert client.post("/projects", json={"name": "x" * 101}).status_code == 422
    assert client.post("/projects", json={}).status_code == 422


def test_get_project(client, make_project):
    project = make_project()
    r = client.get(f"/projects/{project['id']}")
    assert r.status_code == 200
    assert r.json() == project


def test_get_project_404(client):
    r = client.get("/projects/999999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Project 999999 not found"}


def test_list_projects(client, make_project):
    a = make_project(name="A")
    b = make_project(name="B")
    r = client.get("/projects")
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [a["id"], b["id"]]


def test_list_projects_pagination(client, make_project):
    for name in ("A", "B", "C"):
        make_project(name=name)
    r = client.get("/projects", params={"skip": 1, "limit": 1})
    assert [p["name"] for p in r.json()] == ["B"]
    assert client.get("/projects", params={"limit": 0}).status_code == 422


def test_update_project_partial(client, make_project):
    project = make_project(name="Website", description="old")
    r = client.patch(f"/projects/{project['id']}", json={"description": "new"})
    assert r.status_code == 200
    assert r.json()["description"] == "new"
    assert r.json()["name"] == "Website"  # untouched because it wasn't sent


def test_update_project_rename_to_existing_name_409(client, make_project):
    make_project(name="Website")
    other = make_project(name="Mobile app")
    r = client.patch(f"/projects/{other['id']}", json={"name": "Website"})
    assert r.status_code == 409


def test_update_project_null_name_422(client, make_project):
    project = make_project()
    r = client.patch(f"/projects/{project['id']}", json={"name": None})
    assert r.status_code == 422


def test_update_project_404(client):
    assert client.patch("/projects/999999", json={"description": "x"}).status_code == 404


def test_delete_project(client, make_project):
    project = make_project()
    r = client.delete(f"/projects/{project['id']}")
    assert r.status_code == 204
    assert r.content == b""
    assert client.get(f"/projects/{project['id']}").status_code == 404


def test_delete_project_404(client):
    assert client.delete("/projects/999999").status_code == 404


def test_delete_project_cascades_to_tasks(client, make_project, make_task):
    project = make_project()
    task = make_task(project["id"])
    client.delete(f"/projects/{project['id']}")
    assert client.get(f"/tasks/{task['id']}").status_code == 404


# ---------- Join endpoint ----------

def test_get_project_with_tasks(client, make_project, make_task):
    project = make_project(name="Website")
    t1 = make_task(project["id"], title="Design")
    t2 = make_task(project["id"], title="Build", status="in_progress")
    other = make_project(name="Other")
    make_task(other["id"], title="Not mine")

    r = client.get(f"/projects/{project['id']}/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == project["id"]
    assert body["name"] == "Website"
    assert [t["id"] for t in body["tasks"]] == [t1["id"], t2["id"]]  # only this project's, in order
    assert body["tasks"][1]["status"] == "in_progress"


def test_get_project_with_no_tasks(client, make_project):
    project = make_project()
    r = client.get(f"/projects/{project['id']}/tasks")
    assert r.status_code == 200
    assert r.json()["tasks"] == []


def test_get_project_with_tasks_404(client):
    assert client.get("/projects/999999/tasks").status_code == 404


def test_isolation_between_tests(client):
    # Every test above created a "Website" project; if rollback isolation failed,
    # this list would not be empty (and the duplicate-name tests would have clashed).
    assert client.get("/projects").json() == []
