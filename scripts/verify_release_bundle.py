"""Verify a SwiftAgent release archive, clean runtime install, health, and SPA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    resolved_destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != resolved_destination and resolved_destination not in target.parents:
            raise RuntimeError(f"Archive member escapes extraction root: {member.name}")
    archive.extractall(destination, filter="data")


def _verify_manifest(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = root / entry["path"]
        content = path.read_bytes()
        if len(content) != entry["bytes"]:
            raise RuntimeError(f"Release file size mismatch: {entry['path']}")
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Release file hash mismatch: {entry['path']}")
    if (root / ".env").exists():
        raise RuntimeError("Release archive must not contain .env")
    if not (root / "client" / "dist" / "index.html").is_file():
        raise RuntimeError("Release archive has no prebuilt client")
    return manifest


def _fetch_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    archive_path = arguments.archive.expanduser().resolve()
    if not archive_path.is_file():
        raise RuntimeError(f"Release archive not found: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="swiftagent-release-verify-") as raw_temp:
        temp = Path(raw_temp)
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, temp)
        roots = [path for path in temp.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("Release archive must contain exactly one root directory")
        root = roots[0]
        manifest = _verify_manifest(root)

        venv = root / "server" / ".venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = venv / "bin" / "python"
        if os.name == "nt":
            python = venv / "Scripts" / "python.exe"
        subprocess.run(
            [str(python), "-m", "pip", "install", "-e", str(root / "server")],
            check=True,
        )

        port = _free_port()
        environment = os.environ.copy()
        environment.update(
            {
                "SWIFTAGENT_DATA_DIR": str(temp / "data"),
                "SWIFTAGENT_HOST": "127.0.0.1",
                "SWIFTAGENT_PORT": str(port),
                "SWIFTAGENT_NO_BROWSER": "1",
            }
        )
        process = subprocess.Popen(
            [str(python), "-m", "swiftagent.main"],
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            health = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    health = _fetch_json(f"http://127.0.0.1:{port}/health")
                    break
                except OSError:
                    time.sleep(0.2)
            if health is None:
                output = (
                    process.stdout.read()[-4_000:]
                    if process.poll() is not None and process.stdout
                    else "process remained alive without a health response"
                )
                raise RuntimeError(f"Release server did not become healthy:\n{output}")
            if health.get("version") != str(manifest["release"]).removeprefix("v"):
                raise RuntimeError(f"Health version does not match release: {health}")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/settings", timeout=2
            ) as response:
                html = response.read().decode("utf-8")
            if "<title>SwiftAgent</title>" not in html:
                raise RuntimeError("Bundled SPA did not serve on a client-side route")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print(f"Release bundle verified: {archive_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
