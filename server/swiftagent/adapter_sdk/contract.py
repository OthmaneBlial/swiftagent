"""Executable contract harness for local ACP adapter manifests."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swiftagent.adapter_sdk import ADAPTER_API_VERSION, CONTRACT_SUITE_ID
from swiftagent.adapter_sdk.loader import _environment_for
from swiftagent.adapter_sdk.manifest import AdapterManifest, load_manifest, resolve_command
from swiftagent.agents.acp import AcpAdapter
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.storage.database import close_database, init_database, is_initialized

DEFAULT_EXPECTED_EVENTS = [
    AgentEventType.RUN_STARTED.value,
    AgentEventType.MESSAGE_DELTA.value,
    AgentEventType.MESSAGE_COMPLETED.value,
    AgentEventType.RUN_COMPLETED.value,
]
CAPABILITY_EVENTS = {
    "tool_events": {AgentEventType.TOOL_STARTED.value, AgentEventType.TOOL_COMPLETED.value},
    "approvals": {
        AgentEventType.APPROVAL_REQUESTED.value,
        AgentEventType.APPROVAL_RESOLVED.value,
    },
    "plan_updates": {AgentEventType.PLAN_UPDATED.value},
    "usage": {AgentEventType.USAGE_UPDATED.value},
}


class ContractManager:
    """Minimal client surface with deterministic approval and question answers."""

    def __init__(self) -> None:
        self.agent_events: list[AgentEvent] = []
        self.legacy_events: list[Any] = []

    async def broadcast_agent_event(self, event: AgentEvent) -> None:
        self.agent_events.append(event)

    async def broadcast(self, event: Any) -> None:
        self.legacy_events.append(event)

    async def request_permission(self, _request_id: str, event: Any) -> bool:
        self.legacy_events.append(event)
        return True

    async def request_question(self, _request_id: str, event: Any) -> str:
        self.legacy_events.append(event)
        return "contract-choice"


def _task(manifest: AdapterManifest, workspace: Path, prompt: str) -> Task:
    task = Task(
        config=TaskConfig(
            prompt=prompt,
            agent_id=manifest.agent_id,
            working_directory=str(workspace),
        ),
        status=TaskStatus.RUNNING,
        agent_id=manifest.agent_id,
        adapter_id=manifest.adapter_id,
        adapter_version=manifest.adapter_version,
        capability_snapshot=manifest.capabilities.model_dump(),
    )
    task_repo.save_task(task)
    task_repo.add_task_message(task.id, TaskMessage(role="user", content=prompt))
    receipt_repo.initialize_receipt(task, workspace)
    return task


async def _completed_run(
    manifest: AdapterManifest,
    manifest_path: Path,
    workspace: Path,
    command: list[str],
    *,
    native_session_id: str | None = None,
) -> tuple[Task, ContractManager]:
    fixture = manifest.contract
    prompt = fixture.prompt if fixture else "Exercise the adapter contract without network access."
    task = _task(manifest, workspace, prompt)
    if native_session_id:
        task.native_session_id = native_session_id
        task.session_id = native_session_id
        task_repo.update_task_native_session_id(task.id, native_session_id)
    manager = ContractManager()
    adapter = AcpAdapter(
        task,
        manager,  # type: ignore[arg-type]
        command=command,
        environment=_environment_for(manifest),
    )
    await asyncio.wait_for(adapter.start(), timeout=20)
    await asyncio.wait_for(adapter.wait(), timeout=30)
    persisted = task_repo.get_task(task.id)
    if persisted is None or persisted.status is not TaskStatus.COMPLETED:
        error = persisted.result.error if persisted and persisted.result else "missing terminal task"
        raise RuntimeError(f"Adapter contract run did not complete: {error}")
    receipt_repo.finalize_receipt(task.id)
    return persisted, manager


async def _cancelled_run(
    manifest: AdapterManifest,
    workspace: Path,
    command: list[str],
) -> list[str]:
    task = _task(manifest, workspace, "Wait until SwiftAgent cancels this contract run.")
    manager = ContractManager()
    adapter = AcpAdapter(
        task,
        manager,  # type: ignore[arg-type]
        command=command,
        environment=_environment_for(manifest),
    )
    await asyncio.wait_for(adapter.start(), timeout=20)
    await asyncio.sleep(0.1)
    await asyncio.wait_for(adapter.cancel(), timeout=10)
    await asyncio.wait_for(adapter.wait(), timeout=10)
    persisted = task_repo.get_task(task.id)
    if persisted is None or persisted.status is not TaskStatus.CANCELLED:
        raise RuntimeError("Cancellation contract did not persist a cancelled terminal state")
    return [event.type.value for event in manager.agent_events]


async def _failed_run(
    manifest: AdapterManifest,
    workspace: Path,
    command: list[str],
) -> list[str]:
    """Drive a deterministic agent failure and require normalized failure evidence."""
    task = _task(manifest, workspace, "Exercise a deterministic adapter failure without network access.")
    manager = ContractManager()
    adapter = AcpAdapter(
        task,
        manager,  # type: ignore[arg-type]
        command=command,
        environment=_environment_for(manifest),
    )
    await asyncio.wait_for(adapter.start(), timeout=20)
    await asyncio.wait_for(adapter.wait(), timeout=30)
    persisted = task_repo.get_task(task.id)
    if persisted is None or persisted.status is not TaskStatus.FAILED:
        status = persisted.status.value if persisted else "missing"
        raise RuntimeError(
            f"Failure contract did not persist a failed terminal state (got {status})"
        )
    event_types = [event.type.value for event in manager.agent_events]
    if AgentEventType.RUN_FAILED.value not in event_types:
        raise RuntimeError("Failure contract did not emit a normalized run.failed event")
    return event_types


def _required_event_types(manifest: AdapterManifest) -> set[str]:
    required = set(DEFAULT_EXPECTED_EVENTS)
    for capability, event_types in CAPABILITY_EVENTS.items():
        if getattr(manifest.capabilities, capability):
            required.update(event_types)
    if manifest.contract:
        required.update(manifest.contract.expected_event_types)
    return required


async def run_contract(manifest_path: Path) -> dict[str, Any]:
    """Run new-session, optional resume, cancellation, and failure evidence in isolation."""
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    command = resolve_command(manifest, manifest_path)
    fixture = manifest.contract

    if is_initialized():
        close_database()
    with tempfile.TemporaryDirectory(prefix="swiftagent-adapter-contract-") as raw_temp:
        root = Path(raw_temp)
        workspace = root / "workspace"
        workspace.mkdir()
        for relative_path, content in (fixture.fixture_files if fixture else {}).items():
            destination = workspace / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")

        init_database(str(root / "contract.db"))
        settings_repo.set_workspace_dir(str(workspace))
        settings_repo.set_sandbox_mode("fallback")
        try:
            first_task, manager = await _completed_run(
                manifest,
                manifest_path,
                workspace,
                command,
            )
            event_types = [event.type.value for event in manager.agent_events]
            missing = sorted(_required_event_types(manifest) - set(event_types))
            if missing:
                raise RuntimeError(f"Declared capabilities lack normalized evidence: {missing}")
            if any(event.agent_id != manifest.agent_id for event in manager.agent_events):
                raise RuntimeError("Adapter emitted an event with the wrong agent identity")
            if any(event.adapter_id != manifest.adapter_id for event in manager.agent_events):
                raise RuntimeError("Adapter emitted an event with the wrong adapter identity")

            resume_checked = False
            if manifest.capabilities.session_resume:
                if not first_task.native_session_id:
                    raise RuntimeError("Adapter declares resume but did not persist a native session id")
                await _completed_run(
                    manifest,
                    manifest_path,
                    workspace,
                    command,
                    native_session_id=first_task.native_session_id,
                )
                resume_checked = True

            cancellation_checked = False
            cancellation_events: list[str] = []
            if fixture and fixture.cancellation_arguments:
                cancellation_events = await _cancelled_run(
                    manifest,
                    workspace,
                    [*command, *fixture.cancellation_arguments],
                )
                cancellation_checked = True

            failure_checked = False
            failure_events: list[str] = []
            recovery_checked = False
            if fixture and fixture.failure_arguments:
                failure_events = await _failed_run(
                    manifest,
                    workspace,
                    [*command, *fixture.failure_arguments],
                )
                failure_checked = True
                # Prove a terminal failed run does not poison the shared DB/registry path.
                await _completed_run(
                    manifest,
                    manifest_path,
                    workspace,
                    command,
                )
                recovery_checked = True

            return {
                "schema_version": 1,
                "contract_suite": CONTRACT_SUITE_ID,
                "adapter_api_version": ADAPTER_API_VERSION,
                "manifest": {
                    "agent_id": manifest.agent_id,
                    "adapter_id": manifest.adapter_id,
                    "adapter_version": manifest.adapter_version,
                    "protocol": manifest.protocol,
                },
                "result": "passed",
                "event_types": event_types,
                "required_event_types": sorted(_required_event_types(manifest)),
                "resume_checked": resume_checked,
                "cancellation_checked": cancellation_checked,
                "cancellation_event_types": cancellation_events,
                "failure_checked": failure_checked,
                "failure_event_types": failure_events,
                "failure_recovery_checked": recovery_checked,
                "security": {
                    "shell_used": False,
                    "temporary_workspace": True,
                    "network_required": False,
                    "environment_allowlist": sorted(manifest.environment_allowlist),
                },
                "generated_at": datetime.now(UTC).isoformat(),
            }
        finally:
            close_database()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional JSON receipt path")
    arguments = parser.parse_args()
    try:
        report = asyncio.run(run_contract(arguments.manifest))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"result": "failed", "error": str(exc)}, indent=2))
        return 1
    serialized = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
