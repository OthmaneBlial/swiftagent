from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Run every API test against an isolated data directory."""
    monkeypatch.setenv("SWIFTAGENT_DATA_DIR", str(tmp_path / "swiftagent-data"))
    monkeypatch.delenv("SWIFTAGENT_WORKSPACE_DIR", raising=False)

    from swiftagent.main import app

    with TestClient(app) as test_client:
        yield test_client
