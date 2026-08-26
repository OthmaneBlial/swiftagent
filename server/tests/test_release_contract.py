from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from swiftagent import __version__
from swiftagent.agents.registry import agent_registry
from swiftagent.main import VERSION

ROOT = Path(__file__).resolve().parents[2]
RELEASE = "v0.6.0"


def test_release_versions_workflow_and_notes_form_one_evidence_contract() -> None:
    project = tomllib.loads((ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8"))
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    client_package = json.loads((ROOT / "client" / "package.json").read_text(encoding="utf-8"))
    client_lock = json.loads((ROOT / "client" / "package-lock.json").read_text(encoding="utf-8"))

    assert {
        project["project"]["version"],
        root_package["version"],
        client_package["version"],
        client_lock["version"],
        client_lock["packages"][""]["version"],
        VERSION,
        __version__,
    } == {RELEASE.removeprefix("v")}

    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for required in (
        'tags:\n      - "v*.*.*"',
        "make adapter-kit-test",
        "make demo-verify",
        "generate_evaluation_receipts.py",
        "build_release.py",
        "verify_release_bundle.py",
        "anchore/sbom-action@v0.24.0",
        "actions/attest@v4",
        "sbom-path:",
        "SHA256SUMS",
        "gh release create",
    ):
        assert required in workflow
    for permission in ("attestations: write", "contents: write", "id-token: write"):
        assert permission in workflow

    notes = (ROOT / "docs" / "releases" / f"{RELEASE}.md").read_text(encoding="utf-8")
    for definition in agent_registry.definitions():
        expected_receipt = f"swiftagent-{RELEASE}-{definition.agent_id}-evaluation.json"
        assert definition.display_name in notes
        assert expected_receipt in notes
    assert "provider/model" in notes
    assert "five opt-in" in notes


def test_release_bundle_scripts_are_bounded_to_dist_and_exclude_local_secrets() -> None:
    builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_release_bundle.py").read_text(encoding="utf-8")

    assert 'DIST = ROOT / "dist"' in builder
    assert 'STAGING_PARENT = DIST / "release-staging"' in builder
    assert 'EXCLUDED_PREFIXES = ("research_", ".github/ISSUE_SEEDS/")' in builder
    assert "git\", \"ls-files" in builder
    assert 'root / ".env"' in verifier
    assert "Archive member escapes extraction root" in verifier
    assert '"SWIFTAGENT_NO_BROWSER": "1"' in verifier
    assert re.search(r'health\.get\("version"\).*manifest\["release"\]', verifier, re.DOTALL)


def test_focused_pages_keep_main_positioning_neutral_and_request_opt_in_evidence() -> None:
    site = ROOT / "site"
    index = (site / "index.html").read_text(encoding="utf-8")
    expected_pages = {
        "claude-code.html": ("Claude Code", "stream-json"),
        "codex.html": ("Codex", "app-server v2"),
        "opencode.html": ("OpenCode", "ACP when possible"),
        "acp.html": ("Connect an ACP agent", "Local custom"),
    }
    for filename, phrases in expected_pages.items():
        page = (site / filename).read_text(encoding="utf-8")
        assert filename in index
        assert all(phrase in page for phrase in phrases)
        assert "SwiftAgent" in page
        assert "boundary" in page.lower()

    assert "One local place to run, inspect, approve, resume, and compare" in index
    assert "uses no silent telemetry" in index
    assert "not a star counter" in index
    assert "compatibility_report.yml" in index
    assert "workflow_friction.yml" in index
    scorecard = (ROOT / "docs" / "ADOPTION_SCORECARD.md").read_text(encoding="utf-8")
    assert "0 / 5" in scorecard
    assert "no silent telemetry" in scorecard
