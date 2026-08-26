"""Local manifest and disposable-test receipt persistence."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from swiftagent.agents.generic_command.manifest import (
    GenericCommandManifest,
    fingerprint,
    parse_manifest,
)
from swiftagent.storage import settings as settings_repo

MANIFEST_KEY = "generic_command_manifest_json"
RECEIPT_KEY = "generic_command_test_receipt"


class TestReceipt(BaseModel):
    manifest_fingerprint: str
    executable_identity: str
    tested_at: datetime
    version_output: str | None = None
    sandbox_notice: str | None = None


def get_manifest_json() -> str:
    return settings_repo.get_value(MANIFEST_KEY, "").strip()


def get_manifest() -> GenericCommandManifest | None:
    return parse_manifest(get_manifest_json())


def set_manifest_json(raw: str) -> GenericCommandManifest | None:
    manifest = parse_manifest(raw)
    try:
        previous = get_manifest()
    except ValueError:
        previous = None
    changed = (
        (fingerprint(previous) if previous else None)
        != (fingerprint(manifest) if manifest else None)
    )
    normalized = (
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
        if manifest
        else ""
    )
    settings_repo.set_value(MANIFEST_KEY, normalized)
    if changed:
        settings_repo.set_value(RECEIPT_KEY, "")
    return manifest


def get_receipt() -> TestReceipt | None:
    raw = settings_repo.get_value(RECEIPT_KEY, "").strip()
    if not raw:
        return None
    try:
        return TestReceipt.model_validate_json(raw)
    except Exception:
        return None


def set_receipt(receipt: TestReceipt) -> None:
    settings_repo.set_value(RECEIPT_KEY, receipt.model_dump_json())
