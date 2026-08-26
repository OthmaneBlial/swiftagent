"""Persistence and assembly for Local Run Receipts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.receipt import (
    ActivityLedgerEntry,
    GitState,
    ReceiptActions,
    ReceiptAgent,
    ReceiptGitImpact,
    ReceiptInteractions,
    ReceiptSafety,
    RunReceipt,
    SafetyLayer,
    VerificationEvidence,
)
from swiftagent.models.task import Task, TaskStatus
from swiftagent.storage import tasks as task_repo
from swiftagent.storage.database import get_database

MAX_GIT_STATUS_BYTES = 2 * 1024 * 1024
MAX_GIT_FILES = 2_000
MAX_HASH_FILE_BYTES = 8 * 1024 * 1024
MAX_LEDGER_EVENTS = 5_000


def _now() -> datetime:
    return datetime.now(UTC)


def _default_verification() -> VerificationEvidence:
    return VerificationEvidence(status="not_run", source="system", recorded_at=_now())


def _run_git(workspace: Path, *args: str, timeout: float = 6) -> tuple[int, bytes, bytes]:
    try:
        process = subprocess.run(
            ["git", "-C", str(workspace), *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, b"", str(exc).encode("utf-8", errors="replace")
    return process.returncode, process.stdout[:MAX_GIT_STATUS_BYTES], process.stderr[:16_384]


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip()


def _porcelain_paths(raw: bytes) -> list[str]:
    """Parse `git status --porcelain=v1 -z`, including rename source records."""
    records = raw.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record or len(record) < 4:
            continue
        status = record[:2]
        path = record[3:].decode("utf-8", errors="replace")
        paths.append(path)
        if b"R" in status or b"C" in status:
            if index < len(records) and records[index]:
                paths.append(records[index].decode("utf-8", errors="replace"))
                index += 1
    return sorted(dict.fromkeys(paths))[:MAX_GIT_FILES]


def _fingerprint(root: Path, relative_path: str) -> str:
    target = root / relative_path
    try:
        if target.is_symlink():
            return "symlink:" + os.readlink(target)
        if not target.exists():
            return "missing"
        stat = target.stat()
        if not target.is_file() or stat.st_size > MAX_HASH_FILE_BYTES:
            return f"metadata:{stat.st_mode}:{stat.st_size}:{stat.st_mtime_ns}"
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(128 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    except OSError as exc:
        return "error:" + str(exc)[:256]


def capture_git_state(workspace: Path) -> dict[str, Any]:
    captured_at = _now()
    code, root_raw, error_raw = _run_git(workspace, "rev-parse", "--show-toplevel")
    if code != 0:
        return {
            **GitState(
                captured_at=captured_at, error="Workspace is not a Git repository."
            ).model_dump(mode="json"),
            "fingerprints": {},
        }

    root = Path(_decode(root_raw)).resolve()
    head_code, head_raw, _ = _run_git(root, "rev-parse", "HEAD")
    branch_code, branch_raw, _ = _run_git(root, "symbolic-ref", "--short", "-q", "HEAD")
    status_code, status_raw, status_error = _run_git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    if status_code != 0:
        return {
            **GitState(
                available=True,
                repo_root=str(root),
                head_sha=_decode(head_raw) if head_code == 0 else None,
                branch=_decode(branch_raw) if branch_code == 0 else None,
                captured_at=captured_at,
                error=_decode(status_error) or "Git status failed.",
            ).model_dump(mode="json"),
            "fingerprints": {},
        }

    paths = _porcelain_paths(status_raw)
    diff_args = ["diff", "--stat", "--no-ext-diff"]
    if head_code == 0:
        diff_args.append("HEAD")
    _, diff_raw, _ = _run_git(root, *diff_args)
    diff_summary = _decode(diff_raw) or None
    untracked = sum(1 for record in status_raw.split(b"\0") if record.startswith(b"?? "))
    if untracked:
        suffix = f"{untracked} untracked file{'s' if untracked != 1 else ''}"
        diff_summary = f"{diff_summary}\n{suffix}" if diff_summary else suffix

    state = GitState(
        available=True,
        repo_root=str(root),
        head_sha=_decode(head_raw) if head_code == 0 else None,
        branch=_decode(branch_raw) if branch_code == 0 else None,
        dirty=bool(paths),
        changed_files=paths,
        diff_summary=diff_summary,
        captured_at=captured_at,
    ).model_dump(mode="json")
    state["fingerprints"] = {path: _fingerprint(root, path) for path in paths}
    return state


def initialize_receipt(
    task: Task,
    workspace: Path,
    baseline: dict[str, Any] | None = None,
) -> None:
    db = get_database()
    baseline = baseline or capture_git_state(workspace)
    db.execute(
        """
        INSERT OR REPLACE INTO run_receipts (
            task_id, workspace, git_baseline_json, git_final_json,
            verification_json, finalized_at
        ) VALUES (?, ?, ?, NULL, ?, NULL)
        """,
        (
            task.id,
            str(workspace.resolve()),
            json.dumps(baseline),
            _default_verification().model_dump_json(),
        ),
    )
    db.commit()


def get_pending_receipt_workspace(task_id: str) -> Path | None:
    db = get_database()
    row = db.execute(
        "SELECT workspace, finalized_at FROM run_receipts WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row or row["finalized_at"]:
        return None
    return Path(row["workspace"])


def finalize_receipt(task_id: str, final_state: dict[str, Any] | None = None) -> None:
    workspace = get_pending_receipt_workspace(task_id)
    if workspace is None:
        return
    final_state = final_state or capture_git_state(workspace)
    db = get_database()
    db.execute(
        "UPDATE run_receipts SET git_final_json = ?, finalized_at = ? "
        "WHERE task_id = ? AND finalized_at IS NULL",
        (json.dumps(final_state), _now().isoformat(), task_id),
    )
    db.commit()


def add_agent_event(event: AgentEvent) -> None:
    db = get_database()
    db.execute(
        """
        INSERT INTO agent_events (task_id, event_type, timestamp, event_json)
        VALUES (?, ?, ?, ?)
        """,
        (event.run_id, event.type.value, event.timestamp.isoformat(), event.model_dump_json()),
    )
    db.commit()


def get_agent_events(task_id: str) -> list[tuple[int, AgentEvent]]:
    db = get_database()
    rows = db.execute(
        "SELECT sequence, event_json FROM agent_events WHERE task_id = ? "
        "ORDER BY sequence ASC LIMIT ?",
        (task_id, MAX_LEDGER_EVENTS),
    ).fetchall()
    return [(row["sequence"], AgentEvent.model_validate_json(row["event_json"])) for row in rows]


def get_agent_event_count(task_id: str) -> int:
    db = get_database()
    row = db.execute(
        "SELECT COUNT(*) AS count FROM agent_events WHERE task_id = ?", (task_id,)
    ).fetchone()
    return int(row["count"])


def record_verification(task_id: str, evidence: VerificationEvidence) -> None:
    db = get_database()
    result = db.execute(
        "UPDATE run_receipts SET verification_json = ? WHERE task_id = ?",
        (evidence.model_dump_json(), task_id),
    )
    if result.rowcount == 0:
        raise ValueError("Run receipt not found")
    db.commit()


def _ledger_summary(event: AgentEvent) -> str:
    payload = event.payload
    if event.type is AgentEventType.RUN_STARTED:
        return "Run started"
    if event.type is AgentEventType.MESSAGE_DELTA:
        content = str(payload.get("content") or "").replace("\n", " ").strip()
        return f"Message streamed: {content[:120]}" if content else "Message streamed"
    if event.type is AgentEventType.MESSAGE_COMPLETED:
        return "Assistant message completed"
    if event.type in {
        AgentEventType.TOOL_STARTED,
        AgentEventType.TOOL_UPDATED,
        AgentEventType.TOOL_COMPLETED,
    }:
        name = payload.get("name") or payload.get("tool_name") or "tool"
        return f"{name}: {event.type.value.split('.')[-1]}"
    if event.type is AgentEventType.APPROVAL_REQUESTED:
        return "Approval requested"
    if event.type is AgentEventType.APPROVAL_RESOLVED:
        return f"Approval resolved: {payload.get('outcome') or 'unknown'}"
    if event.type is AgentEventType.QUESTION_REQUESTED:
        return "Question requested"
    if event.type is AgentEventType.PLAN_UPDATED:
        return "Plan updated"
    if event.type is AgentEventType.USAGE_UPDATED:
        return "Usage updated"
    if event.type is AgentEventType.RUN_FAILED:
        return "Run failed"
    return "Run completed"


def _interaction_summary(events: list[tuple[int, AgentEvent]]) -> ReceiptInteractions:
    summary = ReceiptInteractions()
    requests: dict[str, dict[str, Any]] = {}
    for _, event in events:
        if event.type is AgentEventType.TOOL_STARTED:
            summary.tools_started += 1
        elif event.type is AgentEventType.TOOL_COMPLETED:
            summary.tools_completed += 1
        elif event.type is AgentEventType.APPROVAL_REQUESTED:
            summary.approvals_requested += 1
            request_id = str(event.payload.get("request_id") or "")
            if request_id:
                requests[request_id] = event.payload
        elif event.type is AgentEventType.APPROVAL_RESOLVED:
            outcome = str(event.payload.get("outcome") or "").lower()
            request = requests.get(str(event.payload.get("request_id") or ""), {})
            selected_id = event.payload.get("option_id")
            selected_kind = ""
            for option in request.get("options") or []:
                if isinstance(option, dict) and option.get("id") == selected_id:
                    selected_kind = str(option.get("kind") or "").lower()
                    break
            if outcome in {"decline", "denied", "reject", "cancelled"} or selected_kind.startswith(
                "reject"
            ):
                summary.approvals_denied += 1
            elif outcome in {"accept", "approved", "allow", "selected"}:
                summary.approvals_approved += 1
        elif event.type is AgentEventType.QUESTION_REQUESTED:
            summary.questions_requested += 1
        elif event.type is AgentEventType.PLAN_UPDATED:
            summary.latest_plan = event.payload
        elif event.type is AgentEventType.USAGE_UPDATED:
            summary.latest_usage = event.payload
    return summary


def _safety(task: Task, events: list[tuple[int, AgentEvent]]) -> ReceiptSafety:
    capabilities = task.capability_snapshot
    start_payload: dict[str, Any] = {}
    for _, event in events:
        if event.type is AgentEventType.RUN_STARTED:
            start_payload = event.payload
            break

    native_supported = bool(capabilities.get("native_sandbox"))
    native_mode = capabilities.get("native_sandbox_mode")
    permission_policy = capabilities.get("native_approval_policy") or capabilities.get(
        "native_permission_mode"
    )
    native = SafetyLayer(
        supported=native_supported,
        mode=str(native_mode) if native_mode else None,
        permission_policy=str(permission_policy) if permission_policy else None,
        active=native_supported if native_mode else None,
        evidence_status="verified"
        if native_supported and native_mode
        else "unsupported"
        if not native_supported
        else "unknown",
        notice=None
        if native_supported
        else "This adapter did not expose a native sandbox to SwiftAgent.",
    )

    requested = str(capabilities.get("effective_sandbox_mode") or "unknown")
    notice_value = start_payload.get("sandbox_notice")
    notice = str(notice_value) if notice_value else None
    external_active = (
        True
        if requested == "strict" and not notice and start_payload
        else False
        if requested == "fallback"
        else None
    )
    external = SafetyLayer(
        supported=capabilities.get("external_sandbox") != "unsupported",
        mode=requested,
        active=external_active,
        evidence_status="verified"
        if external_active
        else "unsupported"
        if external_active is False
        else "unknown",
        notice=notice,
    )

    native_text = (
        f"native sandbox {native.mode}"
        if native.active and native.mode
        else "native sandbox reported but its active mode is unknown"
        if native_supported
        else "no native sandbox exposed"
    )
    permission_text = f", permission policy {permission_policy}" if permission_policy else ""
    external_text = (
        "SwiftAgent strict OS isolation active"
        if external.active
        else "SwiftAgent fallback mode active; no OS isolation"
        if external.active is False
        else "SwiftAgent isolation could not be verified"
    )
    return ReceiptSafety(
        native=native,
        swiftagent_isolation=external,
        effective_summary=f"{external_text}; {native_text}{permission_text}.",
    )


def _changed_across_commits(baseline: dict[str, Any], final: dict[str, Any]) -> list[str]:
    root = final.get("repo_root") or baseline.get("repo_root")
    before = baseline.get("head_sha")
    after = final.get("head_sha")
    if not root or not before or not after or before == after:
        return []
    code, stdout, _ = _run_git(Path(root), "diff", "--name-only", "-z", before, after)
    if code != 0:
        return []
    return [part.decode("utf-8", errors="replace") for part in stdout.split(b"\0") if part]


def _git_impact(baseline: dict[str, Any], final: dict[str, Any] | None) -> ReceiptGitImpact:
    final = final or baseline
    if not baseline.get("available"):
        return ReceiptGitImpact(error=baseline.get("error") or "Git evidence unavailable.")
    before_fingerprints = baseline.get("fingerprints") or {}
    after_fingerprints = final.get("fingerprints") or {}
    changed = {
        path
        for path in set(before_fingerprints) | set(after_fingerprints)
        if before_fingerprints.get(path) != after_fingerprints.get(path)
    }
    changed.update(_changed_across_commits(baseline, final))
    summary = final.get("diff_summary")
    if changed and not summary:
        summary = f"{len(changed)} file{'s' if len(changed) != 1 else ''} changed during the run."
    return ReceiptGitImpact(
        available=True,
        baseline_sha=baseline.get("head_sha"),
        final_sha=final.get("head_sha"),
        branch=final.get("branch") or baseline.get("branch"),
        initial_dirty=bool(baseline.get("dirty")),
        initial_changed_files=list(baseline.get("changed_files") or []),
        changed_files=sorted(changed),
        post_run_diff_summary=summary,
        error=final.get("error"),
    )


def get_receipt(task_id: str) -> RunReceipt | None:
    task = task_repo.get_task(task_id)
    if task is None:
        return None
    db = get_database()
    row = db.execute("SELECT * FROM run_receipts WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    if (
        task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        and not row["finalized_at"]
    ):
        finalize_receipt(task_id)
        row = db.execute("SELECT * FROM run_receipts WHERE task_id = ?", (task_id,)).fetchone()

    events = get_agent_events(task_id)
    ledger = [
        ActivityLedgerEntry(
            sequence=sequence,
            type=event.type.value,
            timestamp=event.timestamp,
            summary=_ledger_summary(event),
            payload=event.payload,
            native_event_type=event.native_event_type,
            native_metadata=event.native_metadata,
        )
        for sequence, event in events
    ]
    try:
        definition = agent_registry.definition(task.agent_id)
        display_name = definition.display_name
        protocol = str(task.capability_snapshot.get("protocol") or definition.protocol)
    except ValueError:
        display_name = task.agent_id
        protocol = str(task.capability_snapshot.get("protocol") or "unknown")
    model = task.capability_snapshot.get("effective_model") or task.config.model_id
    completed_at = task.completed_at
    duration_ms = (
        max(0, int((completed_at - task.created_at).total_seconds() * 1000))
        if completed_at
        else None
    )
    baseline = json.loads(row["git_baseline_json"])
    final = json.loads(row["git_final_json"]) if row["git_final_json"] else None
    terminal = task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    return RunReceipt(
        run_id=task.id,
        intent=task.config.prompt,
        status=task.status.value,
        agent=ReceiptAgent(
            agent_id=task.agent_id,
            display_name=display_name,
            adapter_id=task.adapter_id,
            adapter_version=task.adapter_version,
            protocol=protocol,
            model=str(model) if model else None,
            native_session_id=task.native_session_id,
        ),
        workspace=row["workspace"],
        started_at=task.created_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        result=task.result,
        safety=_safety(task, events),
        interactions=_interaction_summary(events),
        git=_git_impact(baseline, final),
        verification=VerificationEvidence.model_validate_json(row["verification_json"]),
        ledger=ledger,
        ledger_total=get_agent_event_count(task_id),
        actions=ReceiptActions(
            inspect=True,
            resume_same_agent=bool(
                terminal
                and task.native_session_id
                and task.capability_snapshot.get("session_resume", False)
            ),
            create_handoff=terminal,
        ),
    )


def receipt_as_markdown(receipt: RunReceipt) -> str:
    result = receipt.result
    result_text = (
        result.summary
        or (f"Error: {result.error}" if result and result.error else "No result recorded")
        if result
        else "Run is not complete"
    )
    lines = [
        f"# SwiftAgent Local Run Receipt `{receipt.run_id}`",
        "",
        f"- Status: **{receipt.status}**",
        f"- Agent: **{receipt.agent.display_name}** (`{receipt.agent.agent_id}`)",
        f"- Adapter: `{receipt.agent.adapter_id}` v{receipt.agent.adapter_version}",
        f"- Protocol: `{receipt.agent.protocol}`",
        f"- Model: `{receipt.agent.model or 'not reported'}`",
        f"- Workspace: `{receipt.workspace}`",
        f"- Started: {receipt.started_at.isoformat()}",
        f"- Completed: {receipt.completed_at.isoformat() if receipt.completed_at else 'not complete'}",
        "",
        "## Intent",
        "",
        receipt.intent,
        "",
        "## Result",
        "",
        result_text,
        "",
        "## Safety",
        "",
        receipt.safety.effective_summary,
        "",
        "## Git impact",
        "",
        f"- Initial dirty state: {'yes' if receipt.git.initial_dirty else 'no'}",
        f"- Initial dirty paths: {', '.join(receipt.git.initial_changed_files) or 'none'}",
        f"- Changed during run: {', '.join(receipt.git.changed_files) or 'none detected'}",
        f"- Post-run diff: {receipt.git.post_run_diff_summary or 'none'}",
        "",
        "## Verification",
        "",
        f"- Status: **{receipt.verification.status.replace('_', ' ')}**",
        f"- Evidence: {receipt.verification.summary or 'none recorded'}",
        "",
        "## Activity ledger",
        "",
    ]
    for entry in receipt.ledger:
        native = f"; native `{entry.native_event_type}`" if entry.native_event_type else ""
        lines.append(f"- {entry.timestamp.isoformat()} — `{entry.type}` — {entry.summary}{native}")
    return "\n".join(lines) + "\n"
