from __future__ import annotations

import json
from pathlib import Path

from swiftagent import cli


def test_onboard_show_reports_all_local_agents_without_a_model_call(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'SWIFTAGENT_ACP_COMMAND_JSON=["python3", "agent.py"]\n'
        "SWIFTAGENT_DEFAULT_AGENT_ID=codex\n",
        encoding="utf-8",
    )
    executables = {
        "claude": "/tools/claude",
        "codex": "/tools/codex",
        "opencode": "/tools/opencode",
        "bwrap": None,
    }
    monkeypatch.setattr(cli, "_env_path", lambda: env_path)
    monkeypatch.setattr(cli.shutil, "which", lambda command: executables.get(command))
    monkeypatch.setattr(cli, "_version", lambda path: f"version for {path}")

    cli.onboard_show()

    output = capsys.readouterr().out
    assert "SwiftAgent — Local Agents" in output
    assert "Claude Code" in output
    assert "Codex" in output
    assert "OpenCode" in output
    assert "ACP v1" in output
    assert "configured (2 literal arguments)" in output
    assert "no model call" in output


def test_interactive_onboarding_saves_agent_neutral_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    example = tmp_path / ".env.example"
    example.write_text(
        "SWIFTAGENT_DEFAULT_AGENT_ID=\n"
        "SWIFTAGENT_CLAUDE_PATH=\n"
        "SWIFTAGENT_CODEX_PATH=\n"
        "SWIFTAGENT_OPENCODE_PATH=\n"
        "SWIFTAGENT_ACP_COMMAND_JSON=\n"
        "SWIFTAGENT_WORKSPACE_DIR=\n"
        "SWIFTAGENT_SANDBOX_MODE=strict\n",
        encoding="utf-8",
    )
    answers = iter(
        [
            "",
            "/custom/codex",
            "",
            json.dumps(["python3", "agent.py"]),
            "codex",
            str(tmp_path / "workspace"),
            "fallback",
        ]
    )
    monkeypatch.setattr(cli, "_env_path", lambda: env_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _command: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli.onboard_interactive()

    values = cli._read_env(env_path)
    assert values["SWIFTAGENT_DEFAULT_AGENT_ID"] == "codex"
    assert values["SWIFTAGENT_CODEX_PATH"] == "/custom/codex"
    assert json.loads(values["SWIFTAGENT_ACP_COMMAND_JSON"]) == ["python3", "agent.py"]
    assert values["SWIFTAGENT_WORKSPACE_DIR"] == str(tmp_path / "workspace")
    assert values["SWIFTAGENT_SANDBOX_MODE"] == "fallback"


def test_default_agent_setting_uses_environment_when_database_has_no_override(
    client, monkeypatch
) -> None:
    from swiftagent.storage import settings as settings_repo

    monkeypatch.setenv("SWIFTAGENT_DEFAULT_AGENT_ID", "opencode")
    settings_repo.clear_app_settings()
    assert settings_repo.get_default_agent_id() == "opencode"
