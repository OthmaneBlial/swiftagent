from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_public_site_is_agent_agnostic_and_links_real_demo_media() -> None:
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    docs = (ROOT / "site" / "docs.html").read_text(encoding="utf-8")

    for agent_name in ("Claude Code", "Codex", "OpenCode", "ACP v1"):
        assert agent_name in index
    assert "Your choice of agent" in index
    assert "Different instruments" in index
    assert "Native protocols behind one contract" in docs
    assert "Claude Code,<br /><em>with a flight deck" not in index
    assert "Local control for Claude Code" not in index + docs
    assert 'media="(prefers-reduced-motion: reduce)"' in index
    assert "swiftagent-v0.6.0.tar.gz" in index + docs
    assert "SHA256SUMS" in index + docs

    screenshot = ROOT / "site" / "assets" / "swiftagent-run-receipt.png"
    animation = ROOT / "site" / "assets" / "swiftagent-three-agent-demo.gif"
    assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert animation.read_bytes().startswith((b"GIF87a", b"GIF89a"))
    assert screenshot.stat().st_size > 50_000
    assert animation.stat().st_size > 50_000


def test_readme_and_demo_docs_disclose_fixture_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    demo = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")

    assert "make demo-verify" in readme
    assert "model-quality benchmark" in readme
    assert "one manually accepted approval" in demo
    assert "no provider/model call" in demo
    assert "Do not edit screenshots" in demo
