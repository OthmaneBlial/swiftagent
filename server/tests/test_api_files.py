from __future__ import annotations


def test_health_and_readiness_expose_a_request_id(client):
    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Request-ID"]
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_file_api_is_workspace_scoped_and_atomic(client):
    created = client.post(
        "/api/files/write",
        json={"path": "notes/today.md", "content": "first version"},
    )
    assert created.status_code == 200

    overwritten = client.post(
        "/api/files/write",
        json={"path": "notes/today.md", "content": "final version"},
    )
    assert overwritten.status_code == 200

    read = client.post("/api/files/read", json={"path": "notes/today.md"})
    assert read.status_code == 200
    assert read.json()["content"] == "final version"

    escaped = client.post("/api/files/read", json={"path": "../outside.txt"})
    assert escaped.status_code == 400
    assert "escapes workspace" in escaped.json()["detail"]


def test_file_api_blocks_workspace_deletion_and_unintended_overwrites(client):
    assert (
        client.post(
            "/api/files/write", json={"path": "source.txt", "content": "source"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/files/write", json={"path": "destination.txt", "content": "destination"}
        ).status_code
        == 200
    )

    overwrite = client.post(
        "/api/files/move",
        json={"source_path": "source.txt", "target_path": "destination.txt"},
    )
    assert overwrite.status_code == 409

    root_delete = client.post("/api/files/delete", json={"path": ".", "recursive": True})
    assert root_delete.status_code == 400
    assert "workspace root" in root_delete.json()["detail"]


def test_file_api_enforces_configured_size_limit(client, monkeypatch):
    monkeypatch.setenv("SWIFTAGENT_MAX_FILE_BYTES", "1024")
    response = client.post(
        "/api/files/write",
        json={"path": "too-large.txt", "content": "x" * 1025},
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_task_list_is_bounded_and_unknown_task_is_404(client):
    response = client.get("/api/tasks?limit=101")
    assert response.status_code == 422

    deleted = client.delete("/api/tasks/not-a-real-task")
    assert deleted.status_code == 404
