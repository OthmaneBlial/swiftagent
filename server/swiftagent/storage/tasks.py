"""
Task history repository — SQLite-backed CRUD for tasks and messages.

Ported from base/accomplish/packages/agent-core/src/storage/repositories/taskHistory.ts
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskResult, TaskStatus, TodoItem
from swiftagent.storage.database import get_database

# ── Tasks ─────────────────────────────────────────────────────


def get_tasks(limit: int = 50, offset: int = 0) -> list[Task]:
    db = get_database()
    rows = db.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def get_task(task_id: str) -> Task | None:
    db = get_database()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    task = _row_to_task(row)
    task.messages = get_task_messages(task_id)
    return task


def get_latest_task_by_native_session_id(session_id: str) -> Task | None:
    db = get_database()
    row = db.execute(
        """
        SELECT * FROM tasks
        WHERE native_session_id = ? OR session_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (session_id, session_id),
    ).fetchone()
    return _row_to_task(row) if row else None


def save_task(task: Task) -> None:
    db = get_database()
    db.execute(
        """
        INSERT INTO tasks (id, prompt, working_directory, status,
            session_id, summary, result_json, config_json, created_at, completed_at,
            agent_id, adapter_id, adapter_version, native_session_id,
            capability_snapshot_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.id,
            task.config.prompt,
            task.config.working_directory,
            task.status.value,
            task.session_id,
            task.summary,
            task.result.model_dump_json() if task.result else None,
            task.config.model_dump_json(),
            task.created_at.isoformat(),
            task.completed_at.isoformat() if task.completed_at else None,
            task.agent_id,
            task.adapter_id,
            task.adapter_version,
            task.native_session_id or task.session_id,
            json.dumps(task.capability_snapshot),
        ),
    )
    db.commit()


def update_task_status(
    task_id: str, status: TaskStatus, completed_at: datetime | None = None
) -> None:
    db = get_database()
    db.execute(
        "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
        (status.value, completed_at.isoformat() if completed_at else None, task_id),
    )
    db.commit()


def complete_task(task: Task, result: TaskResult) -> None:
    """Persist terminal state and result in one transaction."""
    db = get_database()
    completed_at = task.completed_at or datetime.now(UTC)
    native_session_id = task.native_session_id or task.session_id
    db.execute(
        """
        UPDATE tasks
        SET status = ?, completed_at = ?, session_id = ?, native_session_id = ?,
            summary = ?, result_json = ?
        WHERE id = ?
        """,
        (
            task.status.value,
            completed_at.isoformat(),
            native_session_id,
            native_session_id,
            task.summary,
            result.model_dump_json(),
            task.id,
        ),
    )
    db.commit()


def update_task_session_id(task_id: str, session_id: str) -> None:
    """Compatibility alias for native agent session persistence."""
    update_task_native_session_id(task_id, session_id)


def update_task_native_session_id(task_id: str, session_id: str) -> None:
    db = get_database()
    db.execute(
        "UPDATE tasks SET session_id = ?, native_session_id = ? WHERE id = ?",
        (session_id, session_id, task_id),
    )
    db.commit()


def update_task_capability_snapshot(task_id: str, capabilities: dict[str, object]) -> None:
    """Persist capabilities negotiated after an adapter starts."""
    db = get_database()
    db.execute(
        "UPDATE tasks SET capability_snapshot_json = ? WHERE id = ?",
        (json.dumps(capabilities), task_id),
    )
    db.commit()


def update_task_summary(task_id: str, summary: str) -> None:
    db = get_database()
    db.execute("UPDATE tasks SET summary = ? WHERE id = ?", (summary, task_id))
    db.commit()


def delete_task(task_id: str) -> bool:
    db = get_database()
    result = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return result.rowcount > 0


def clear_history() -> None:
    db = get_database()
    db.execute("DELETE FROM tasks")
    db.commit()


def recover_interrupted_tasks() -> int:
    """Mark work that could not survive a server restart as failed."""
    db = get_database()
    now = datetime.now(UTC).isoformat()
    result = db.execute(
        """
        UPDATE tasks
        SET status = ?, completed_at = ?, result_json = ?
        WHERE status IN (?, ?, ?, ?, ?)
        """,
        (
            TaskStatus.FAILED.value,
            now,
            TaskResult(
                success=False,
                error="SwiftAgent restarted before this task completed. Start a new task or resume its session.",
            ).model_dump_json(),
            TaskStatus.PENDING.value,
            TaskStatus.QUEUED.value,
            TaskStatus.RUNNING.value,
            TaskStatus.WAITING_FOR_PERMISSION.value,
            TaskStatus.WAITING_FOR_QUESTION.value,
        ),
    )
    db.commit()
    return result.rowcount


# ── Messages ──────────────────────────────────────────────────


def get_task_messages(task_id: str) -> list[TaskMessage]:
    db = get_database()
    rows = db.execute(
        "SELECT * FROM task_messages WHERE task_id = ? ORDER BY timestamp ASC",
        (task_id,),
    ).fetchall()
    return [
        TaskMessage(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            metadata=json.loads(r["metadata_json"]) if r["metadata_json"] else None,
        )
        for r in rows
    ]


def add_task_message(task_id: str, message: TaskMessage) -> None:
    db = get_database()
    db.execute(
        """
        INSERT INTO task_messages (id, task_id, role, content, timestamp, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            message.id,
            task_id,
            message.role,
            message.content,
            message.timestamp.isoformat(),
            json.dumps(message.metadata) if message.metadata else None,
        ),
    )
    db.commit()


# ── Todos ─────────────────────────────────────────────────────


def get_todos_for_task(task_id: str) -> list[TodoItem]:
    db = get_database()
    rows = db.execute("SELECT * FROM todo_items WHERE task_id = ?", (task_id,)).fetchall()
    return [
        TodoItem(id=r["id"], content=r["content"], completed=bool(r["completed"])) for r in rows
    ]


def save_todos_for_task(task_id: str, todos: list[TodoItem]) -> None:
    db = get_database()
    db.execute("DELETE FROM todo_items WHERE task_id = ?", (task_id,))
    for todo in todos:
        db.execute(
            "INSERT INTO todo_items (id, task_id, content, completed) VALUES (?, ?, ?, ?)",
            (todo.id, task_id, todo.content, int(todo.completed)),
        )
    db.commit()


def clear_todos_for_task(task_id: str) -> None:
    db = get_database()
    db.execute("DELETE FROM todo_items WHERE task_id = ?", (task_id,))
    db.commit()


# ── Helpers ───────────────────────────────────────────────────


def _row_to_task(row: dict) -> Task:
    config = TaskConfig.model_validate_json(row["config_json"])
    result = TaskResult.model_validate_json(row["result_json"]) if row["result_json"] else None

    return Task(
        id=row["id"],
        config=config,
        status=TaskStatus(row["status"]),
        agent_id=row["agent_id"],
        adapter_id=row["adapter_id"],
        adapter_version=row["adapter_version"],
        native_session_id=row["native_session_id"] or row["session_id"],
        capability_snapshot=json.loads(row["capability_snapshot_json"] or "{}"),
        session_id=row["session_id"],
        summary=row["summary"],
        result=result,
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )
