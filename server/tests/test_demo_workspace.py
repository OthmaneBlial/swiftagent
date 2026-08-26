from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "demo_workspace.py"


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("swiftagent_demo_workspace", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_fixture_has_a_failing_baseline_and_passing_reference() -> None:
    demo = _load_demo_module()
    assert demo.verify_template() == {
        "baseline_fails": True,
        "reference_passes": True,
    }


def test_each_named_agent_gets_a_fresh_isolated_git_workspace(tmp_path: Path) -> None:
    demo = _load_demo_module()
    runs_root = tmp_path / "runs"

    for agent_id in demo.SUPPORTED_AGENTS:
        workspace = demo.prepare_workspace(agent_id, runs_root=runs_root)
        assert workspace == (runs_root / agent_id).resolve()
        assert (workspace / "TASK.md").is_file()
        assert (workspace / ".git").is_dir()
        baseline = subprocess.run(
            ["python3", "-m", "unittest", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        assert baseline.returncode != 0

    marker = runs_root / "codex" / "agent-created.txt"
    marker.write_text("must disappear on reset\n", encoding="utf-8")
    demo.prepare_workspace("codex", runs_root=runs_root)
    assert not marker.exists()

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=runs_root / "codex",
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""


def test_demo_preparation_rejects_unknown_agent(tmp_path: Path) -> None:
    demo = _load_demo_module()
    with pytest.raises(ValueError, match="Unsupported demo agent"):
        demo.prepare_workspace("mystery-agent", runs_root=tmp_path / "runs")
