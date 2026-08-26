"""Build a bounded tagged SwiftAgent archive with a prebuilt web client."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
STAGING_PARENT = DIST / "release-staging"
EXCLUDED_PREFIXES = ("research_", ".github/ISSUE_SEEDS/")


def _run(*arguments: str) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _project_version() -> str:
    payload = tomllib.loads((ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def _assert_versions(version: str) -> None:
    client_lock = json.loads(
        (ROOT / "client" / "package-lock.json").read_text(encoding="utf-8")
    )
    json_versions = {
        json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"],
        json.loads((ROOT / "client" / "package.json").read_text(encoding="utf-8"))["version"],
        client_lock["version"],
        client_lock["packages"][""]["version"],
    }
    source_versions = set()
    for path, pattern in (
        (ROOT / "server" / "swiftagent" / "__init__.py", r'__version__ = "([^"]+)"'),
        (ROOT / "server" / "swiftagent" / "main.py", r'VERSION = "([^"]+)"'),
    ):
        match = re.search(pattern, path.read_text(encoding="utf-8"))
        if not match:
            raise RuntimeError(f"Version declaration was not found in {path.relative_to(ROOT)}")
        source_versions.add(match.group(1))
    found = json_versions | source_versions | {version}
    if found != {version}:
        raise RuntimeError(f"Release versions disagree: {sorted(found)}")


def _tracked_paths() -> list[Path]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    paths = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        relative = Path(item.decode("utf-8"))
        normalized = relative.as_posix()
        if normalized.startswith(EXCLUDED_PREFIXES):
            continue
        paths.append(relative)
    return sorted(paths, key=lambda path: path.as_posix())


def _copy_release_tree(destination: Path) -> None:
    for relative in _tracked_paths():
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    client_dist = ROOT / "client" / "dist"
    if not (client_dist / "index.html").is_file():
        raise RuntimeError("Build the client before creating a release bundle")
    shutil.copytree(client_dist, destination / "client" / "dist")


def _write_manifest(destination: Path, version: str, commit: str) -> None:
    files = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file():
            continue
        content = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(destination).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest = {
        "schema_version": 1,
        "release": f"v{version}",
        "source_commit": commit,
        "files": files,
    }
    (destination / "RELEASE-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _archive_tree(source: Path, output: Path, source_epoch: int) -> None:
    with (
        output.open("wb") as raw_output,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=source_epoch) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source.parent)
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = source_epoch
            if path.is_file():
                with path.open("rb") as source_file:
                    archive.addfile(info, source_file)
            else:
                archive.addfile(info)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="exact vX.Y.Z release tag")
    arguments = parser.parse_args()

    version = _project_version()
    expected_tag = f"v{version}"
    if arguments.tag != expected_tag:
        raise RuntimeError(f"Tag {arguments.tag!r} does not match project version {expected_tag!r}")
    _assert_versions(version)

    commit = _run("git", "rev-parse", "HEAD")
    source_epoch = int(_run("git", "show", "-s", "--format=%ct", "HEAD"))
    bundle_root = STAGING_PARENT / f"swiftagent-{expected_tag}"
    if STAGING_PARENT.exists():
        shutil.rmtree(STAGING_PARENT)
    bundle_root.mkdir(parents=True)
    _copy_release_tree(bundle_root)
    _write_manifest(bundle_root, version, commit)

    DIST.mkdir(exist_ok=True)
    output = DIST / f"swiftagent-{expected_tag}.tar.gz"
    _archive_tree(bundle_root, output, source_epoch)
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
