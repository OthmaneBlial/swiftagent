"""
SQLite storage layer using Python's built-in sqlite3 module.

Replaces better-sqlite3 (native C++ dependency).
Ported from base/accomplish/packages/agent-core/src/storage/database.ts
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime

_db: sqlite3.Connection | None = None
_db_path: str | None = None
_lock = threading.RLock()

CURRENT_SCHEMA_VERSION = 5


def init_database(db_path: str) -> sqlite3.Connection:
    """Initialize the database, run migrations, and return the connection."""
    global _db, _db_path

    with _lock:
        if _db is not None and _db_path == db_path:
            return _db

        if _db is not None:
            close_database()

        print(f"[DB] Opening database at: {db_path}")
        _db = sqlite3.connect(db_path, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db_path = db_path

        # Enable WAL mode and foreign keys (same as original)
        _db.execute("PRAGMA journal_mode = WAL")
        _db.execute("PRAGMA foreign_keys = ON")
        _db.execute("PRAGMA busy_timeout = 5000")

        _run_migrations(_db)
        print("[DB] Database initialized and migrations complete")

        return _db


def get_database() -> sqlite3.Connection:
    """Get the active database connection."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db


def close_database() -> None:
    """Close the database connection."""
    global _db, _db_path

    with _lock:
        if _db is not None:
            print("[DB] Closing database connection")
            _db.close()
            _db = None
            _db_path = None


def is_initialized() -> bool:
    return _db is not None


def _run_migrations(db: sqlite3.Connection) -> None:
    """Run schema migrations."""
    # Create version tracking table
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)

    row = db.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    current_version = row["version"] if row else 0

    if current_version < 1:
        _migrate_v1(db)
    if current_version < 2:
        _migrate_v2(db)
    if current_version < 3:
        _migrate_v3(db)
    if current_version < 4:
        _migrate_v4(db)
    if current_version < 5:
        _migrate_v5(db)

    if current_version == 0:
        db.execute("INSERT INTO schema_version (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,))
    elif current_version < CURRENT_SCHEMA_VERSION:
        db.execute("UPDATE schema_version SET version = ?", (CURRENT_SCHEMA_VERSION,))

    db.commit()


def _migrate_v1(db: sqlite3.Connection) -> None:
    """Initial schema: tasks, messages, settings, providers."""

    # Tasks table
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            working_directory TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            session_id TEXT,
            summary TEXT,
            result_json TEXT,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)

    # Task messages
    db.execute("""
        CREATE TABLE IF NOT EXISTS task_messages (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata_json TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    # App settings (key-value)
    db.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Provider settings
    db.execute("""
        CREATE TABLE IF NOT EXISTS provider_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL
        )
    """)

    # Todo items
    db.execute("""
        CREATE TABLE IF NOT EXISTS todo_items (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            content TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    # Create indexes
    db.execute("CREATE INDEX IF NOT EXISTS idx_messages_task ON task_messages(task_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_todos_task ON todo_items(task_id)")


def _migrate_v2(db: sqlite3.Connection) -> None:
    """Indexes for bounded history and interrupted-task recovery."""
    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at DESC)"
    )


def _migrate_v3(db: sqlite3.Connection) -> None:
    """Persist agent identity, adapter identity, and run capability snapshots."""
    columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)").fetchall()}
    additions = {
        "agent_id": "TEXT NOT NULL DEFAULT 'claude-code'",
        "adapter_id": "TEXT NOT NULL DEFAULT 'claude-stream-json'",
        "adapter_version": "TEXT NOT NULL DEFAULT '0.3.0'",
        "native_session_id": "TEXT",
        "capability_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, declaration in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {declaration}")

    db.execute(
        "UPDATE tasks SET native_session_id = session_id "
        "WHERE native_session_id IS NULL AND session_id IS NOT NULL"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_agent_created_at ON tasks(agent_id, created_at DESC)")


def _migrate_v4(db: sqlite3.Connection) -> None:
    """Persist normalized agent events and durable Local Run Receipt evidence."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_json TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_events_task_sequence "
        "ON agent_events(task_id, sequence)"
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS run_receipts (
            task_id TEXT PRIMARY KEY,
            workspace TEXT NOT NULL,
            git_baseline_json TEXT NOT NULL,
            git_final_json TEXT,
            verification_json TEXT NOT NULL,
            finalized_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
        """
    )
    now = datetime.now(UTC).isoformat()
    legacy_git = json.dumps(
        {
            "available": False,
            "repo_root": None,
            "head_sha": None,
            "branch": None,
            "dirty": False,
            "changed_files": [],
            "diff_summary": None,
            "captured_at": now,
            "error": "Legacy run predates Local Run Receipt Git capture.",
            "fingerprints": {},
        }
    )
    legacy_verification = json.dumps(
        {
            "status": "not_run",
            "summary": None,
            "command": None,
            "source": "system",
            "recorded_at": now,
        }
    )
    # Older history remains inspectable, but missing evidence is explicit. It
    # would be misleading to capture today's Git tree for a historical run.
    for task in db.execute(
        "SELECT id, working_directory FROM tasks "
        "WHERE id NOT IN (SELECT task_id FROM run_receipts)"
    ).fetchall():
        db.execute(
            """
            INSERT INTO run_receipts (
                task_id, workspace, git_baseline_json, git_final_json,
                verification_json, finalized_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task["id"],
                task["working_directory"] or "unknown (legacy run)",
                legacy_git,
                legacy_git,
                legacy_verification,
                now,
            ),
        )


def _migrate_v5(db: sqlite3.Connection) -> None:
    """Persist sanitized, single-use cross-agent handoff previews."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS run_handoffs (
            id TEXT PRIMARY KEY,
            source_task_id TEXT NOT NULL,
            target_task_id TEXT UNIQUE,
            target_agent_id TEXT NOT NULL,
            target_model_id TEXT,
            content_json TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            redactions_json TEXT NOT NULL,
            excluded_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'prepared',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            error TEXT,
            FOREIGN KEY (source_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (target_task_id) REFERENCES tasks(id) ON DELETE SET NULL
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_handoffs_source_created "
        "ON run_handoffs(source_task_id, created_at DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_handoffs_target ON run_handoffs(target_task_id)"
    )
