"""Disposable preflight required before a generic command can run real tasks."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from swiftagent.agents.generic_command import settings as generic_settings
from swiftagent.agents.generic_command.manifest import (
    GenericCommandManifest,
    allowed_environment,
    build_command,
    executable_identity,
    fingerprint,
    resolve_executable,
)
from swiftagent.storage import settings as settings_repo
from swiftagent.tools.sandbox import wrap_command_for_sandbox

TEST_MARKER = "SWIFTAGENT_ADAPTER_OK"
MAX_TEST_OUTPUT_BYTES = 65_536


class GenericCommandTestResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    version_output: str | None = None
    sandbox_notice: str | None = None
    tested_at: datetime


async def _read_bounded(stream: asyncio.StreamReader | None, limit: int) -> bytes:
    if stream is None:
        return b""
    retained = bytearray()
    while True:
        chunk = await stream.read(16_384)
        if not chunk:
            return bytes(retained)
        retained.extend(chunk)
        if len(retained) > limit:
            raise RuntimeError(f"Disposable test output exceeded {limit} bytes")


async def _run_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    stdin: bytes | None,
    timeout: int,
) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=environment,
        start_new_session=True,
    )

    async def communicate() -> tuple[int, bytes, bytes]:
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        stdout_task = asyncio.create_task(_read_bounded(process.stdout, MAX_TEST_OUTPUT_BYTES))
        stderr_task = asyncio.create_task(_read_bounded(process.stderr, MAX_TEST_OUTPUT_BYTES))
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        return await process.wait(), stdout, stderr

    try:
        return await asyncio.wait_for(communicate(), timeout=timeout)
    except (Exception, asyncio.CancelledError):
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()
        raise


async def _probe_version(
    manifest: GenericCommandManifest,
    executable: str,
    workspace: Path,
) -> str | None:
    probe = manifest.version_probe
    if probe is None:
        return None
    command, _notice = wrap_command_for_sandbox(
        [executable, *probe.arguments], workspace, settings_repo.get_sandbox_mode()
    )
    returncode, stdout, stderr = await _run_process(
        command,
        cwd=workspace,
        environment=allowed_environment(manifest),
        stdin=None,
        timeout=probe.timeout_seconds,
    )
    output = (stdout or stderr).decode("utf-8", errors="replace").strip()[:4_096]
    if returncode != 0:
        raise RuntimeError(f"Version probe exited with code {returncode}: {output}")
    if probe.expected_output_prefix and not output.startswith(probe.expected_output_prefix):
        raise RuntimeError(
            "Version probe output did not match expected prefix "
            f"{probe.expected_output_prefix!r}"
        )
    return output or None


async def run_disposable_test() -> GenericCommandTestResult:
    manifest = generic_settings.get_manifest()
    if manifest is None:
        raise RuntimeError("Save a generic command manifest before running its disposable test")
    executable = resolve_executable(manifest)
    if not executable:
        raise RuntimeError(f"Generic command executable was not found: {manifest.executable}")

    with tempfile.TemporaryDirectory(prefix="swiftagent-adapter-test-") as temporary:
        workspace = Path(temporary).resolve()
        version_output = await _probe_version(manifest, executable, workspace)
        prompt = f"Print exactly this marker and nothing else: {TEST_MARKER}"
        command, stdin = build_command(manifest, executable, prompt)
        command, sandbox_notice = wrap_command_for_sandbox(
            command, workspace, settings_repo.get_sandbox_mode()
        )
        returncode, stdout_raw, stderr_raw = await _run_process(
            command,
            cwd=workspace,
            environment=allowed_environment(manifest),
            stdin=stdin,
            timeout=min(manifest.timeout_seconds, 30),
        )

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    if returncode != 0:
        raise RuntimeError(
            f"Disposable adapter test exited with code {returncode}: {stderr[-2_048:]}"
        )
    if TEST_MARKER not in stdout:
        raise RuntimeError(
            f"Disposable adapter test did not return the required marker {TEST_MARKER}"
        )

    tested_at = datetime.now(UTC)
    receipt = generic_settings.TestReceipt(
        manifest_fingerprint=fingerprint(manifest),
        executable_identity=executable_identity(executable),
        tested_at=tested_at,
        version_output=version_output,
        sandbox_notice=sandbox_notice,
    )
    generic_settings.set_receipt(receipt)
    return GenericCommandTestResult(
        success=True,
        stdout=stdout[-4_096:],
        stderr=stderr[-4_096:],
        version_output=version_output,
        sandbox_notice=sandbox_notice,
        tested_at=tested_at,
    )
