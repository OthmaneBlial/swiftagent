"""
SQLite storage layer using Python's built-in sqlite3 module.

Replaces better-sqlite3 (native C++ dependency).
Ported from base/accomplish/packages/agent-core/src/storage/database.ts
"""

from __future__ import annotations

import sqlite3
import threading

_db: sqlite3.Connection | None = None
_db_path: str | None = None
_lock = threading.RLock()

CURRENT_SCHEMA_VERSION = 3


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
