def test_create_task_defaults_to_todo(client, make_project):
    project = make_project()
    r = client.post("/tasks", json={"project_id": project["id"], "title": "Write copy"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Write copy"
    assert body["status"] == "todo"
    assert body["project_id"] == project["id"]
    assert isinstance(body["id"], int)
    assert body["created_at"]


def test_create_task_for_missing_project_404(client):
    r = client.post("/tasks", json={"project_id": 999999, "title": "Orphan"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Project 999999 not found"}


def test_create_task_invalid_status_422(client, make_project):
    project = make_project()
    r = client.post(
        "/tasks", json={"project_id": project["id"], "title": "x", "status": "blocked"}
    )
    assert r.status_code == 422


def test_get_task(client, make_project, make_task):
    task = make_task(make_project()["id"])
    r = client.get(f"/tasks/{task['id']}")
    assert r.status_code == 200
    assert r.json() == task


def test_get_task_404(client):
    r = client.get("/tasks/999999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Task 999999 not found"}


def test_list_tasks(client, make_project, make_task):
    project = make_project()
    a = make_task(project["id"], title="A")
    b = make_task(project["id"], title="B")
    r = client.get("/tasks")
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == [a["id"], b["id"]]


def test_list_tasks_filter_by_status(client, make_project, make_task):
    project = make_project()
    todo = make_task(project["id"], title="A", status="todo")
    make_task(project["id"], title="B", status="in_progress")
    done = make_task(project["id"], title="C", status="done")

    r = client.get("/tasks", params={"status": "todo"})
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == [todo["id"]]

    r = client.get("/tasks", params={"status": "done"})
    assert [t["id"] for t in r.json()] == [done["id"]]


def test_list_tasks_invalid_status_filter_422(client):
    assert client.get("/tasks", params={"status": "blocked"}).status_code == 422


def test_update_task_status(client, make_project, make_task):
    task = make_task(make_project()["id"], title="Design")
    r = client.patch(f"/tasks/{task['id']}", json={"status": "done"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["title"] == "Design"  # untouched


def test_update_task_move_to_other_project(client, make_project, make_task):
    task = make_task(make_project(name="A")["id"])
    b = make_project(name="B")
    r = client.patch(f"/tasks/{task['id']}", json={"project_id": b["id"]})
    assert r.status_code == 200
    assert r.json()["project_id"] == b["id"]


def test_update_task_move_to_missing_project_404(client, make_project, make_task):
    task = make_task(make_project()["id"])
    r = client.patch(f"/tasks/{task['id']}", json={"project_id": 999999})
    assert r.status_code == 404


def test_update_task_null_field_422(client, make_project, make_task):
    task = make_task(make_project()["id"])
    assert client.patch(f"/tasks/{task['id']}", json={"status": None}).status_code == 422


def test_update_task_404(client):
    assert client.patch("/tasks/999999", json={"status": "done"}).status_code == 404


def test_delete_task(client, make_project, make_task):
    task = make_task(make_project()["id"])
    r = client.delete(f"/tasks/{task['id']}")
    assert r.status_code == 204
    assert client.get(f"/tasks/{task['id']}").status_code == 404


def test_delete_task_404(client):
    assert client.delete("/tasks/999999").status_code == 404
