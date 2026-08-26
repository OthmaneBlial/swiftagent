from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swiftagent.api.websocket import ConnectionManager
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskResult, TaskStatus
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.storage.database import get_database


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _clean_repo(root: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is required for receipt evidence tests")
    repo = root / "fixture-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "SwiftAgent test")
    _git(repo, "config", "user.email", "swiftagent@example.invalid")
    (repo / "tracked.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "fixture baseline")
    return repo


def _task(repo: Path) -> Task:
    return Task(
        config=TaskConfig(
            prompt="Make the bounded fixture change and report evidence",
            agent_id="codex",
            working_directory=str(repo),
            model_id="fixture-model",
        ),
        status=TaskStatus.RUNNING,
        agent_id="codex",
        adapter_id="codex-app-server-v2",
        adapter_version="0.4.0",
        native_session_id="native-fixture-session",
        session_id="native-fixture-session",
        capability_snapshot={
            "protocol": "codex-app-server-v2",
            "session_resume": True,
            "native_sandbox": True,
            "native_sandbox_mode": "workspace-write",
            "native_approval_policy": "on-request",
            "external_sandbox": "partial",
            "effective_sandbox_mode": "fallback",
            "effective_model": "fixture-model",
        },
    )


def _event(task: Task, event_type: AgentEventType, payload: dict, **extra) -> AgentEvent:
    return AgentEvent(
        type=event_type,
        agent_id=task.agent_id,
        adapter_id=task.adapter_id,
        run_id=task.id,
        native_session_id=task.native_session_id,
        payload=payload,
        **extra,
    )


def test_receipt_persists_git_safety_interactions_and_explicit_verification(client, tmp_path):
    repo = _clean_repo(tmp_path)
    task = _task(repo)
    task_repo.save_task(task)
    receipt_repo.initialize_receipt(task, repo)

    events = [
        _event(
            task,
            AgentEventType.RUN_STARTED,
            {
                "workspace": str(repo),
                "sandbox_notice": "Fallback mode is active. This process is not OS-isolated.",
            },
            native_event_type="initialize",
            native_metadata={"platformFamily": "fixture"},
        ),
        _event(
            task,
            AgentEventType.APPROVAL_REQUESTED,
            {"request_id": "approval-1", "title": "Fixture command"},
            native_event_type="item/commandExecution/requestApproval",
            native_metadata={"command": ["printf", "safe"]},
        ),
        _event(
            task,
            AgentEventType.APPROVAL_RESOLVED,
            {"request_id": "approval-1", "outcome": "decline"},
            native_event_type="item/commandExecution/requestApproval",
        ),
        _event(
            task,
            AgentEventType.QUESTION_REQUESTED,
            {"request_id": "question-1", "question": "Choose a safe option"},
        ),
        _event(
            task,
            AgentEventType.PLAN_UPDATED,
            {"entries": [{"step": "Inspect", "status": "completed"}]},
        ),
        _event(task, AgentEventType.USAGE_UPDATED, {"input_tokens": 12, "output_tokens": 8}),
    ]
    for event in events:
        receipt_repo.add_agent_event(event)

    (repo / "tracked.txt").write_text("after\n", encoding="utf-8")
    (repo / "new file.txt").write_text("new\n", encoding="utf-8")

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    task.result = TaskResult(success=True, summary="Fixture complete")
    task.summary = "Fixture complete"
    task_repo.complete_task(task, task.result)
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.RUN_COMPLETED,
            {"status": "completed", "success": True, "summary": "Fixture complete"},
            native_event_type="turn/completed",
            native_metadata={"stopReason": "end_turn"},
        )
    )
    receipt_repo.finalize_receipt(task.id)

    response = client.get(f"/api/tasks/{task.id}/receipt")
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["schema_version"] == 1
    assert receipt["agent"]["display_name"] == "Codex"
    assert receipt["agent"]["model"] == "fixture-model"
    assert receipt["agent"]["native_session_id"] == "native-fixture-session"
    assert receipt["safety"]["native"]["mode"] == "workspace-write"
    assert receipt["safety"]["swiftagent_isolation"]["active"] is False
    assert "no OS isolation" in receipt["safety"]["effective_summary"]
    assert receipt["interactions"]["approvals_requested"] == 1
    assert receipt["interactions"]["approvals_denied"] == 1
    assert receipt["interactions"]["questions_requested"] == 1
    assert receipt["interactions"]["questions_unresolved"] == 1
    assert receipt["interactions"]["latest_plan"]["entries"][0]["step"] == "Inspect"
    assert receipt["git"]["initial_dirty"] is False
    assert receipt["git"]["changed_files"] == ["new file.txt", "tracked.txt"]
    assert receipt["verification"]["status"] == "not_run"
    assert receipt["ledger_total"] == len(events) + 1
    assert receipt["ledger"][-1]["native_metadata"] == {"stopReason": "end_turn"}
    assert receipt["actions"] == {
        "inspect": True,
        "resume_same_agent": True,
        "create_handoff": True,
    }

    rejected = client.put(
        f"/api/tasks/{task.id}/receipt/verification",
        json={"status": "passed", "summary": ""},
    )
    assert rejected.status_code == 400

    verified = client.put(
        f"/api/tasks/{task.id}/receipt/verification",
        json={
            "status": "passed",
            "command": "pytest -q",
            "summary": "The isolated fixture contract passed.",
        },
    )
    assert verified.status_code == 200
    assert verified.json()["verification"]["status"] == "passed"
    assert verified.json()["verification"]["source"] == "user"

    reset = client.put(
        f"/api/tasks/{task.id}/receipt/verification",
        json={"status": "not_run", "summary": "must be discarded", "command": "pytest -q"},
    )
    assert reset.status_code == 200
    assert reset.json()["verification"]["summary"] is None
    assert reset.json()["verification"]["command"] is None

    verified = client.put(
        f"/api/tasks/{task.id}/receipt/verification",
        json={
            "status": "passed",
            "command": "pytest -q",
            "summary": "The isolated fixture contract passed.",
        },
    )
    assert verified.status_code == 200

    markdown = client.get(f"/api/tasks/{task.id}/receipt/export?format=markdown")
    assert markdown.status_code == 200
    assert "Local Run Receipt" in markdown.text
    assert "The isolated fixture contract passed." in markdown.text
    assert "attachment;" in markdown.headers["content-disposition"]

    exported_json = client.get(f"/api/tasks/{task.id}/receipt/export?format=json")
    assert exported_json.status_code == 200
    assert json.loads(exported_json.text)["run_id"] == task.id


@pytest.mark.asyncio
async def test_connection_manager_persists_events_before_broadcast(client, tmp_path):
    repo = _clean_repo(tmp_path)
    task = _task(repo)
    task_repo.save_task(task)
    receipt_repo.initialize_receipt(task, repo)
    event = _event(
        task,
        AgentEventType.TOOL_STARTED,
        {"name": "Read", "tool_call_id": "tool-1"},
        native_event_type="fixture.tool",
        native_metadata={"path": "tracked.txt"},
    )

    manager = ConnectionManager()
    await manager.broadcast_agent_event(event)

    persisted = receipt_repo.get_agent_events(task.id)
    assert len(persisted) == 1
    assert persisted[0][1].native_metadata == {"path": "tracked.txt"}


def test_receipt_rows_and_events_cascade_when_history_is_deleted(client, tmp_path):
    repo = _clean_repo(tmp_path)
    task = _task(repo)
    task_repo.save_task(task)
    receipt_repo.initialize_receipt(task, repo)
    receipt_repo.add_agent_event(_event(task, AgentEventType.RUN_STARTED, {}))

    assert task_repo.delete_task(task.id) is True
    db = get_database()
    assert db.execute(
        "SELECT COUNT(*) AS count FROM run_receipts WHERE task_id = ?", (task.id,)
    ).fetchone()["count"] == 0
    assert db.execute(
        "SELECT COUNT(*) AS count FROM agent_events WHERE task_id = ?", (task.id,)
    ).fetchone()["count"] == 0
