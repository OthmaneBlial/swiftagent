"""Build and execute explicit, redacted cross-agent handoffs."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.handoff import (
    HandoffContent,
    HandoffPreview,
    HandoffPreviewRequest,
    HandoffRedaction,
    HandoffVerification,
)
from swiftagent.models.task import Task, TaskConfig, TaskStatus
from swiftagent.storage import handoffs as handoff_repo
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import tasks as task_repo

PREVIEW_TTL_MINUTES = 30
MAX_INTENT_CHARS = 10_000
MAX_SUMMARY_CHARS = 10_000
MAX_DIFF_CHARS = 8_000
MAX_INSTRUCTIONS_CHARS = 10_000
MAX_QUESTION_CHARS = 2_000
MAX_QUESTIONS = 20
MAX_CHANGED_FILES = 500

EXCLUDED_BY_DESIGN = [
    "Native session IDs",
    "Raw credentials and credential-like values",
    "Hidden reasoning and thought events",
    "Native event metadata and full tool output",
    "Full environment dumps",
]

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_KNOWN_TOKEN = re.compile(
    r"(?i)\b(?:sk-(?:proj-)?[a-z0-9_-]{12,}|github_pat_[a-z0-9_]{12,}|"
    r"gh[pousr]_[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{12,}|AKIA[A-Z0-9]{16})\b"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|"
    r"client[_-]?secret|private[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_URL_CREDENTIAL = re.compile(r"\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@", re.I)
_ENV_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}=.*$")
_SENSITIVE_BASENAME = re.compile(
    r"(?i)^(?:\.env(?:\..+)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|"
    r".*(?:credential|secret|password|private[-_]?key).*)$"
)
_SENSITIVE_PATH_IN_TEXT = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])(?:\.env(?:\.[A-Za-z0-9_.-]+)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|"
    r"[A-Za-z0-9_.-]*(?:credential|secret|password|private[-_]?key)[A-Za-z0-9_.-]*"
    r"\.(?:json|ya?ml|txt|pem|key|cfg|conf|ini|toml))(?![A-Za-z0-9_.-])"
)


def _record(report: Counter[str], category: str, count: int) -> None:
    if count > 0:
        report[category] += count


def _bounded(value: str, limit: int, report: Counter[str]) -> str:
    if len(value) <= limit:
        return value
    _record(report, "content_truncated", 1)
    return value[:limit].rstrip() + "\n[CONTENT_TRUNCATED]"


def _redact_environment_dump(value: str, report: Counter[str]) -> str:
    lines = value.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        end = index
        while end < len(lines) and _ENV_LINE.fullmatch(lines[end].strip()):
            end += 1
        count = end - index
        if count >= 4:
            output.append("[ENVIRONMENT_DUMP_REDACTED]")
            _record(report, "environment_dump", count)
            index = end
            continue
        output.append(lines[index])
        index += 1
    return "\n".join(output)


def _redact_text(
    value: str,
    *,
    limit: int,
    native_session_id: str | None,
    report: Counter[str],
) -> str:
    redacted = _bounded(value, limit, report)
    redacted = _redact_environment_dump(redacted, report)
    if native_session_id and native_session_id in redacted:
        replacements = redacted.count(native_session_id)
        redacted = redacted.replace(native_session_id, "[NATIVE_SESSION_ID_REDACTED]")
        _record(report, "native_session_id", replacements)

    redacted, count = _PRIVATE_KEY.subn("[PRIVATE_KEY_REDACTED]", redacted)
    _record(report, "credential", count)
    redacted, count = _KNOWN_TOKEN.subn("[CREDENTIAL_REDACTED]", redacted)
    _record(report, "credential", count)
    redacted, count = _JWT.subn("[JWT_REDACTED]", redacted)
    _record(report, "credential", count)
    redacted, count = _BEARER.subn("Bearer [CREDENTIAL_REDACTED]", redacted)
    _record(report, "credential", count)
    redacted, count = _SECRET_ASSIGNMENT.subn(r"\1\2[CREDENTIAL_REDACTED]", redacted)
    _record(report, "credential", count)
    redacted, count = _URL_CREDENTIAL.subn(r"\1[CREDENTIAL_REDACTED]@", redacted)
    _record(report, "credential", count)
    redacted, count = _SENSITIVE_PATH_IN_TEXT.subn("[SENSITIVE_PATH_REDACTED]", redacted)
    _record(report, "sensitive_path", count)
    return redacted.strip()


def _redact_path(
    path: str,
    *,
    native_session_id: str | None,
    report: Counter[str],
) -> str:
    if _SENSITIVE_BASENAME.fullmatch(Path(path).name):
        _record(report, "sensitive_path", 1)
        return "[SENSITIVE_PATH_REDACTED]"
    return _redact_text(
        path,
        limit=4_096,
        native_session_id=native_session_id,
        report=report,
    )


def _unresolved_questions(receipt) -> list[str]:
    requested: dict[str, str] = {}
    resolved: set[str] = set()
    for entry in receipt.ledger:
        request_id = str(entry.payload.get("request_id") or f"sequence-{entry.sequence}")
        if entry.type == AgentEventType.QUESTION_REQUESTED.value:
            question = str(entry.payload.get("question") or "Agent question")
            requested[request_id] = question
        elif (
            entry.type == AgentEventType.QUESTION_RESOLVED.value
            and bool(entry.payload.get("answered"))
        ):
            resolved.add(request_id)
    return [question for request_id, question in requested.items() if request_id not in resolved]


def _redaction_rows(report: Counter[str]) -> list[HandoffRedaction]:
    explanations = {
        "credential": "Credential-like values were replaced before preview storage.",
        "native_session_id": "The source agent's native session identifier was removed.",
        "environment_dump": "A full environment-variable block was excluded.",
        "sensitive_path": "A filename commonly used for credentials was hidden.",
        "content_truncated": "Content exceeded the bounded handoff budget and was truncated.",
    }
    return [
        HandoffRedaction(
            category=category,  # type: ignore[arg-type]
            replacements=count,
            explanation=explanations[category],
        )
        for category, count in sorted(report.items())
        if count
    ]


def _render_prompt(preview_id: str, source_run_id: str, source_agent: str, content: HandoffContent) -> str:
    lines = [
        "# Explicit SwiftAgent cross-agent handoff",
        "",
        f"Handoff preview: {preview_id}",
        f"Source run: {source_run_id}",
        f"Source agent: {source_agent}",
        "",
        "This context was reviewed by the user and redacted before transfer. Inspect the current "
        "workspace yourself. Do not assume that prior verification passed, do not reuse a native "
        "session format, and ask before expanding the requested scope.",
    ]

    sections: list[tuple[str, str | None]] = [
        ("Original intent", content.original_intent),
        ("User-approved summary", content.approved_summary),
        (
            "Changed file names",
            "\n".join(f"- {path}" for path in content.changed_files)
            if content.changed_files
            else None,
        ),
        ("Bounded diff summary", content.diff_summary),
        (
            "Explicit verification",
            (
                f"Status: {content.verification.status}\n"
                f"Command: {content.verification.command or 'not recorded'}\n"
                f"Evidence: {content.verification.summary or 'not recorded'}"
            )
            if content.verification
            else None,
        ),
        (
            "Unresolved questions",
            "\n".join(f"- {question}" for question in content.unresolved_questions)
            if content.unresolved_questions
            else None,
        ),
        ("Additional user instructions", content.user_instructions),
    ]
    for heading, value in sections:
        if value:
            lines.extend(["", f"## {heading}", "", value])
    return "\n".join(lines).strip()


def create_preview(source_task_id: str, request: HandoffPreviewRequest) -> HandoffPreview:
    source = task_repo.get_task(source_task_id)
    receipt = receipt_repo.get_receipt(source_task_id)
    if source is None or receipt is None:
        raise ValueError("Source run or Local Run Receipt was not found")
    if source.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        raise ValueError("Only a terminal run can be handed to another agent")
    if request.target_agent_id == source.agent_id:
        raise ValueError("Choose a different agent for a cross-agent handoff")
    target = agent_registry.definition(request.target_agent_id)
    if request.include_summary and not request.summary_approved:
        raise ValueError("Review and approve the summary before creating a handoff preview")
    if receipt.workspace.startswith("unknown (legacy run)"):
        raise ValueError("This legacy run has no trustworthy workspace evidence for handoff")

    report: Counter[str] = Counter()
    native_session_id = source.native_session_id
    approved_summary = (request.approved_summary or "").strip()
    content = HandoffContent(
        original_intent=(
            _redact_text(
                receipt.intent,
                limit=MAX_INTENT_CHARS,
                native_session_id=native_session_id,
                report=report,
            )
            if request.include_intent
            else None
        ),
        approved_summary=(
            _redact_text(
                approved_summary,
                limit=MAX_SUMMARY_CHARS,
                native_session_id=native_session_id,
                report=report,
            )
            if request.include_summary and approved_summary
            else None
        ),
        changed_files=(
            [
                _redact_path(
                    path,
                    native_session_id=native_session_id,
                    report=report,
                )
                for path in receipt.git.changed_files[:MAX_CHANGED_FILES]
            ]
            if request.include_changed_files
            else []
        ),
        diff_summary=(
            _redact_text(
                receipt.git.post_run_diff_summary or "",
                limit=MAX_DIFF_CHARS,
                native_session_id=native_session_id,
                report=report,
            )
            or None
            if request.include_diff_summary
            else None
        ),
        verification=(
            HandoffVerification(
                status=receipt.verification.status,
                summary=_redact_text(
                    receipt.verification.summary or "",
                    limit=4_096,
                    native_session_id=native_session_id,
                    report=report,
                )
                or None,
                command=_redact_text(
                    receipt.verification.command or "",
                    limit=4_096,
                    native_session_id=native_session_id,
                    report=report,
                )
                or None,
            )
            if request.include_verification
            else None
        ),
        unresolved_questions=(
            [
                _redact_text(
                    question,
                    limit=MAX_QUESTION_CHARS,
                    native_session_id=native_session_id,
                    report=report,
                )
                for question in _unresolved_questions(receipt)[:MAX_QUESTIONS]
            ]
            if request.include_unresolved_questions
            else []
        ),
        user_instructions=(
            _redact_text(
                request.user_instructions or "",
                limit=MAX_INSTRUCTIONS_CHARS,
                native_session_id=native_session_id,
                report=report,
            )
            or None
        ),
    )
    if request.include_summary and not content.approved_summary:
        raise ValueError("An approved summary is required when summary transfer is selected")
    if not any(
        [
            content.original_intent,
            content.approved_summary,
            content.changed_files,
            content.diff_summary,
            content.verification,
            content.unresolved_questions,
            content.user_instructions,
        ]
    ):
        raise ValueError("Select at least one bounded context field for the handoff")

    now = datetime.now(UTC)
    preview_id = uuid.uuid4().hex
    rendered_prompt = _render_prompt(
        preview_id,
        source.id,
        receipt.agent.display_name,
        content,
    )
    if len(rendered_prompt) > 48_000:  # defensive; individual sections are already bounded
        raise ValueError("Selected handoff context exceeds the task prompt budget")
    preview = HandoffPreview(
        id=preview_id,
        source_run_id=source.id,
        source_agent_id=source.agent_id,
        source_agent_name=receipt.agent.display_name,
        target_agent_id=target.agent_id,
        target_agent_name=target.display_name,
        target_model_id=request.target_model_id,
        content=content,
        rendered_prompt=rendered_prompt,
        redactions=_redaction_rows(report),
        excluded_by_design=EXCLUDED_BY_DESIGN,
        created_at=now,
        expires_at=now + timedelta(minutes=PREVIEW_TTL_MINUTES),
    )
    handoff_repo.save_preview(preview)
    return preview


async def start_handoff(handoff_id: str) -> Task:
    record = handoff_repo.claim_preview(handoff_id)
    source = task_repo.get_task(record.source_task_id)
    receipt = receipt_repo.get_receipt(record.source_task_id)
    if source is None or receipt is None:
        handoff_repo.fail_handoff(handoff_id, "Source run disappeared before handoff start")
        raise ValueError("Source run disappeared before handoff start")
    if source.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        handoff_repo.fail_handoff(handoff_id, "Source run is no longer terminal")
        raise ValueError("Source run must remain terminal")

    from swiftagent.api.websocket import manager as websocket_manager
    from swiftagent.engine.manager import task_manager

    try:
        target = await task_manager.start_task(
            TaskConfig(
                prompt=record.prompt_text,
                agent_id=record.target_agent_id,
                working_directory=receipt.workspace,
                model_id=record.target_model_id,
            ),
            websocket_manager,
        )
    except Exception as exc:
        handoff_repo.fail_handoff(handoff_id, str(exc))
        raise
    handoff_repo.complete_handoff(handoff_id, target.id)
    return target
