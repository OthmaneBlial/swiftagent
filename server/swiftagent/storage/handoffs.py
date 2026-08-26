"""SQLite repository for sanitized, single-use handoff previews."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from swiftagent.models.handoff import HandoffPreview, HandoffRecord
from swiftagent.storage.database import get_database


def save_preview(preview: HandoffPreview) -> None:
    db = get_database()
    # Expired unconsumed previews contain only redacted context, but removing
    # them keeps local history focused on previews that became real handoffs.
    db.execute(
        "DELETE FROM run_handoffs WHERE status = 'prepared' AND expires_at < ?",
        (datetime.now(UTC).isoformat(),),
    )
    db.execute(
        """
        INSERT INTO run_handoffs (
            id, source_task_id, target_agent_id, target_model_id, content_json,
            prompt_text, redactions_json, excluded_json, status, created_at,
            expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            preview.id,
            preview.source_run_id,
            preview.target_agent_id,
            preview.target_model_id,
            preview.content.model_dump_json(),
            preview.rendered_prompt,
            json.dumps([row.model_dump(mode="json") for row in preview.redactions]),
            json.dumps(preview.excluded_by_design),
            preview.status,
            preview.created_at.isoformat(),
            preview.expires_at.isoformat(),
        ),
    )
    db.commit()


def _row_to_record(row) -> HandoffRecord:
    return HandoffRecord(
        id=row["id"],
        source_task_id=row["source_task_id"],
        target_task_id=row["target_task_id"],
        target_agent_id=row["target_agent_id"],
        target_model_id=row["target_model_id"],
        content=json.loads(row["content_json"]),
        prompt_text=row["prompt_text"],
        redactions=json.loads(row["redactions_json"]),
        excluded_by_design=json.loads(row["excluded_json"]),
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        consumed_at=datetime.fromisoformat(row["consumed_at"]) if row["consumed_at"] else None,
        error=row["error"],
    )


def get_handoff(handoff_id: str) -> HandoffRecord | None:
    db = get_database()
    row = db.execute("SELECT * FROM run_handoffs WHERE id = ?", (handoff_id,)).fetchone()
    return _row_to_record(row) if row else None


def claim_preview(handoff_id: str) -> HandoffRecord:
    db = get_database()
    now = datetime.now(UTC)
    row = db.execute("SELECT * FROM run_handoffs WHERE id = ?", (handoff_id,)).fetchone()
    if row is None:
        raise ValueError("Handoff preview not found")
    record = _row_to_record(row)
    if record.status != "prepared":
        raise ValueError("Handoff preview was already used")
    if record.expires_at <= now:
        raise ValueError("Handoff preview expired; review the content again")
    result = db.execute(
        "UPDATE run_handoffs SET status = 'starting', consumed_at = ? "
        "WHERE id = ? AND status = 'prepared'",
        (now.isoformat(), handoff_id),
    )
    db.commit()
    if result.rowcount != 1:
        raise ValueError("Handoff preview was already used")
    return record.model_copy(update={"status": "starting", "consumed_at": now})


def complete_handoff(handoff_id: str, target_task_id: str) -> None:
    db = get_database()
    db.execute(
        "UPDATE run_handoffs SET status = 'started', target_task_id = ?, error = NULL "
        "WHERE id = ? AND status = 'starting'",
        (target_task_id, handoff_id),
    )
    db.commit()


def fail_handoff(handoff_id: str, error: str) -> None:
    db = get_database()
    db.execute(
        "UPDATE run_handoffs SET status = 'failed', error = ? WHERE id = ?",
        (error[:4_096], handoff_id),
    )
    db.commit()


def get_source_run_id(target_task_id: str) -> str | None:
    db = get_database()
    row = db.execute(
        "SELECT source_task_id FROM run_handoffs "
        "WHERE target_task_id = ? AND status = 'started'",
        (target_task_id,),
    ).fetchone()
    return row["source_task_id"] if row else None
