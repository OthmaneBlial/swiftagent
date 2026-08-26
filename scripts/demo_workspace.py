"""Prepare isolated, deterministic workspaces for the public multi-agent demo."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = REPOSITORY_ROOT / "demo-workspace"
TEMPLATE_ROOT = DEMO_ROOT / "template"
REFERENCE_IMPLEMENTATION = DEMO_ROOT / "reference" / "release_badge.py"
RUNS_ROOT = DEMO_ROOT / "runs"
SUPPORTED_AGENTS = ("claude-code", "codex", "opencode")


def _run_tests(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "unittest", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def verify_template(
    template_root: Path = TEMPLATE_ROOT,
    reference_implementation: Path = REFERENCE_IMPLEMENTATION,
) -> dict[str, bool]:
    """Prove the starting bug and acceptance state without any agent call."""
    with tempfile.TemporaryDirectory(prefix="swiftagent-demo-") as raw_temp:
        workspace = Path(raw_temp) / "workspace"
        shutil.copytree(template_root, workspace)
        baseline = _run_tests(workspace)
        if baseline.returncode == 0:
            raise RuntimeError("Demo baseline unexpectedly passes; the task is no longer reproducible")

        shutil.copy2(reference_implementation, workspace / "release_badge.py")
        accepted = _run_tests(workspace)
        if accepted.returncode != 0:
            diagnostics = (accepted.stdout + accepted.stderr).strip()
            raise RuntimeError(f"Demo reference implementation failed acceptance tests: {diagnostics}")

    return {"baseline_fails": True, "reference_passes": True}


def prepare_workspace(
    agent_id: str,
    *,
    template_root: Path = TEMPLATE_ROOT,
    runs_root: Path = RUNS_ROOT,
) -> Path:
    """Create one clean nested Git repository for an allowlisted agent."""
    if agent_id not in SUPPORTED_AGENTS:
        choices = ", ".join(SUPPORTED_AGENTS)
        raise ValueError(f"Unsupported demo agent '{agent_id}'. Choose one of: {choices}")
    if shutil.which("git") is None:
        raise RuntimeError("Git is required so the demo Run Receipt can record a baseline and diff")

    target = (runs_root / agent_id).resolve()
    resolved_runs_root = runs_root.resolve()
    if target.parent != resolved_runs_root:
        raise RuntimeError("Refusing to prepare a demo workspace outside demo-workspace/runs")

    runs_root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(template_root, target)

    commands = [
        ["git", "init", "-q"],
        ["git", "config", "user.name", "SwiftAgent demo"],
        ["git", "config", "user.email", "demo@swiftagent.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "demo baseline"],
    ]
    for command in commands:
        subprocess.run(command, cwd=target, check=True, timeout=20)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="reset one isolated agent workspace")
    prepare.add_argument("agent", choices=SUPPORTED_AGENTS)
    subparsers.add_parser("prepare-all", help="reset one isolated workspace per named agent")
    subparsers.add_parser("verify", help="verify the failing baseline and passing reference")
    arguments = parser.parse_args()

    if arguments.command == "verify":
        result = verify_template()
        print("Demo fixture verified: baseline fails; reference acceptance tests pass.")
        return 0 if all(result.values()) else 1

    agents = SUPPORTED_AGENTS if arguments.command == "prepare-all" else (arguments.agent,)
    verify_template()
    for agent_id in agents:
        target = prepare_workspace(agent_id)
        print(f"Prepared {agent_id}: {target}")
        print(f"  directory: demo-workspace/runs/{agent_id}")
        print(f"  prompt:    demo-workspace/runs/{agent_id}/TASK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
