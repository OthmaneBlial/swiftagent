from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.receipt import VerificationEvidence
from swiftagent.models.task import Task, TaskConfig, TaskResult, TaskStatus
from swiftagent.storage import handoffs as handoff_repo
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.storage.database import get_database


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is required for handoff evidence tests")
    repo = tmp_path / "handoff-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "SwiftAgent test")
    _git(repo, "config", "user.email", "swiftagent@example.invalid")
    (repo / "README.md").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "baseline")
    return repo


def _source_run(repo: Path) -> Task:
    native_session = "native-session-must-never-transfer"
    task = Task(
        config=TaskConfig(
            prompt=(
                "Continue the fixture using sk-proj-1234567890abcdef and never copy "
                f"session {native_session}"
            ),
            agent_id="codex",
            working_directory=str(repo),
        ),
        status=TaskStatus.RUNNING,
        agent_id="codex",
        adapter_id="codex-app-server-v2",
        adapter_version="0.4.0",
        native_session_id=native_session,
        session_id=native_session,
        capability_snapshot={
            **agent_registry.definition("codex").capabilities.model_dump(),
            "protocol": "codex-app-server-v2",
            "effective_sandbox_mode": "fallback",
        },
    )
    task_repo.save_task(task)
    receipt_repo.initialize_receipt(task, repo)
    return task


def _event(task: Task, event_type: AgentEventType, payload: dict, **kwargs) -> AgentEvent:
    return AgentEvent(
        type=event_type,
        agent_id=task.agent_id,
        adapter_id=task.adapter_id,
        run_id=task.id,
        native_session_id=task.native_session_id,
        payload=payload,
        **kwargs,
    )


def _finish_source(task: Task, repo: Path) -> None:
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.RUN_STARTED,
            {"workspace": str(repo), "sandbox_notice": "fallback"},
        )
    )
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.MESSAGE_DELTA,
            {"content": "ordinary visible answer"},
            native_event_type="agent_thought_chunk",
            native_metadata={
                "hidden_reasoning": "HIDDEN_REASONING_MARKER",
                "environment": {"API_TOKEN": "ENV_SECRET_MARKER"},
            },
        )
    )
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.QUESTION_REQUESTED,
            {"request_id": "resolved-question", "question": "Already answered?"},
        )
    )
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.QUESTION_RESOLVED,
            {"request_id": "resolved-question", "answered": True},
        )
    )
    receipt_repo.add_agent_event(
        _event(
            task,
            AgentEventType.QUESTION_REQUESTED,
            {
                "request_id": "open-question",
                "question": "Which safe option should use token ghp_abcdefghijklmnopqrstuvwxyz1234?",
            },
        )
    )

    (repo / "README.md").write_text("after\n", encoding="utf-8")
    (repo / ".env").write_text("DO_NOT_TRANSFER=secret\n", encoding="utf-8")
    source_dir = repo / "src"
    source_dir.mkdir()
    (source_dir / "app.py").write_text("print('safe')\n", encoding="utf-8")

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    task.summary = "Implemented the fixture; password=hunter2"
    task.result = TaskResult(success=True, summary=task.summary)
    task_repo.complete_task(task, task.result)
    receipt_repo.add_agent_event(
        _event(task, AgentEventType.RUN_COMPLETED, {"success": True, "status": "completed"})
    )
    receipt_repo.record_verification(
        task.id,
        VerificationEvidence(
            status="passed",
            command="pytest -q --token sk-1234567890abcdef",
            summary="Passed with api_key=supersecretvalue",
            source="user",
            recorded_at=datetime.now(UTC),
        ),
    )
    receipt_repo.finalize_receipt(task.id)


def _preview_body(summary_approved: bool = True) -> dict:
    return {
        "target_agent_id": "generic-command",
        "target_model_id": "safe-target-model",
        "include_intent": True,
        "include_summary": True,
        "include_changed_files": True,
        "include_diff_summary": True,
        "include_verification": True,
        "include_unresolved_questions": True,
        "approved_summary": "Reviewed result with password=hunter2",
        "summary_approved": summary_approved,
        "user_instructions": (
            "Continue carefully with Bearer abcdefghijklmnopqrstuvwxyz\n"
            "PATH=/usr/bin\nHOME=/private/home\nLANG=en_US\nAPI_TOKEN=do-not-copy"
        ),
    }


def test_handoff_requires_summary_approval_and_a_different_agent(client, tmp_path):
    repo = _repo(tmp_path)
    source = _source_run(repo)
    _finish_source(source, repo)

    unapproved = client.post(
        f"/api/tasks/{source.id}/handoff/preview",
        json=_preview_body(summary_approved=False),
    )
    assert unapproved.status_code == 400
    assert "approve" in unapproved.text.lower()

    same_agent = _preview_body()
    same_agent["target_agent_id"] = "codex"
    rejected = client.post(f"/api/tasks/{source.id}/handoff/preview", json=same_agent)
    assert rejected.status_code == 400
    assert "different agent" in rejected.text.lower()


def test_handoff_preview_redacts_and_excludes_unportable_state(client, tmp_path, monkeypatch):
    import swiftagent.engine.manager as manager_module

    repo = _repo(tmp_path)
    source = _source_run(repo)
    _finish_source(source, repo)
    original = task_repo.get_task(source.id)
    assert original is not None

    response = client.post(
        f"/api/tasks/{source.id}/handoff/preview",
        json=_preview_body(),
    )
    assert response.status_code == 200
    preview = response.json()
    serialized = json.dumps(preview, sort_keys=True)

    forbidden = [
        "sk-proj-1234567890abcdef",
        "native-session-must-never-transfer",
        "hunter2",
        "ghp_abcdefghijklmnopqrstuvwxyz1234",
        "abcdefghijklmnopqrstuvwxyz",
        "do-not-copy",
        "HIDDEN_REASONING_MARKER",
        "ENV_SECRET_MARKER",
        "DO_NOT_TRANSFER",
    ]
    for secret in forbidden:
        assert secret not in serialized
    assert "[CREDENTIAL_REDACTED]" in serialized
    assert "[NATIVE_SESSION_ID_REDACTED]" in serialized
    assert "[ENVIRONMENT_DUMP_REDACTED]" in serialized
    assert "[SENSITIVE_PATH_REDACTED]" in serialized
    assert "Already answered?" not in serialized
    assert "Which safe option" in serialized
    assert preview["content"]["changed_files"] == [
        "[SENSITIVE_PATH_REDACTED]",
        "README.md",
        "src/app.py",
    ]
    assert preview["content"]["verification"]["status"] == "passed"
    assert {row["category"] for row in preview["redactions"]} >= {
        "credential",
        "native_session_id",
        "environment_dump",
        "sensitive_path",
    }
    assert "Native session IDs" in preview["excluded_by_design"]

    stored = handoff_repo.get_handoff(preview["id"])
    assert stored is not None
    stored_json = stored.model_dump_json()
    for secret in forbidden:
        assert secret not in stored_json

    started_configs: list[TaskConfig] = []

    class FakeTaskManager:
        async def start_task(self, config, _manager):
            started_configs.append(config)
            definition = agent_registry.definition(config.agent_id)
            target = Task(
                config=config,
                status=TaskStatus.RUNNING,
                agent_id=definition.agent_id,
                adapter_id=definition.adapter_id,
                adapter_version=definition.adapter_version,
                capability_snapshot={
                    **definition.capabilities.model_dump(),
                    "protocol": definition.protocol,
                    "effective_sandbox_mode": "fallback",
                },
            )
            task_repo.save_task(target)
            receipt_repo.initialize_receipt(target, Path(config.working_directory or repo))
            return target

        async def shutdown(self):
            return None

    monkeypatch.setattr(manager_module, "task_manager", FakeTaskManager())
    started = client.post(f"/api/handoffs/{preview['id']}/start")
    assert started.status_code == 200
    target = started.json()
    assert target["agent_id"] == "generic-command"
    assert target["native_session_id"] is None
    assert len(started_configs) == 1
    assert started_configs[0].working_directory == str(repo)
    assert started_configs[0].model_id == "safe-target-model"
    assert started_configs[0].prompt == preview["rendered_prompt"]
    for secret in forbidden:
        assert secret not in started_configs[0].prompt

    target_receipt = client.get(f"/api/tasks/{target['id']}/receipt")
    assert target_receipt.status_code == 200
    assert target_receipt.json()["handoff_source_run_id"] == source.id

    replay = client.post(f"/api/handoffs/{preview['id']}/start")
    assert replay.status_code == 409
    assert len(started_configs) == 1

    unchanged = task_repo.get_task(source.id)
    assert unchanged is not None
    assert unchanged.status is TaskStatus.COMPLETED
    assert unchanged.native_session_id == original.native_session_id
    assert unchanged.result == original.result


def test_expired_preview_cannot_start(client, tmp_path):
    repo = _repo(tmp_path)
    source = _source_run(repo)
    _finish_source(source, repo)
    preview = client.post(
        f"/api/tasks/{source.id}/handoff/preview", json=_preview_body()
    ).json()
    get_database().execute(
        "UPDATE run_handoffs SET expires_at = ? WHERE id = ?",
        ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), preview["id"]),
    )
    get_database().commit()

    expired = client.post(f"/api/handoffs/{preview['id']}/start")
    assert expired.status_code == 409
    assert "expired" in expired.text.lower()
