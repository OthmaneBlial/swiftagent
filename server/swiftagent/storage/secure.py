"""
AES-256-GCM encrypted secure storage for API keys.

Ported from base/accomplish/packages/agent-core/src/storage/secure-storage.ts
Uses the same machine-derived key approach (PBKDF2 with platform+homedir+username+appId).
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecureStorage:
    """
    AES-256-GCM encrypted JSON file storage.

    Less secure than OS Keychain (key derivation is reversible)
    but avoids native dependencies and permission prompts.
    Suitable for API keys that can be rotated if compromised.
    """

    def __init__(
        self,
        storage_path: str,
        app_id: str = "ai.swiftagent.app",
        file_name: str = "secure-storage.json",
    ):
        self._storage_path = Path(storage_path)
        self._app_id = app_id
        self._file_path = self._storage_path / file_name
        self._derived_key: bytes | None = None
        self._data: dict | None = None

    # ── Data I/O ──────────────────────────────────────────────

    def _load_data(self) -> dict:
        if self._data is not None:
            return self._data

        try:
            if self._file_path.exists():
                self._data = json.loads(self._file_path.read_text("utf-8"))
            else:
                self._data = {"values": {}}
        except Exception:
            self._data = {"values": {}}

        return self._data

    def _save_data(self) -> None:
        if self._data is None:
            return

        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp, then rename
        tmp_path = self._file_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            tmp_path.write_text(json.dumps(self._data, indent=2), "utf-8")
            os.chmod(tmp_path, 0o600)
            tmp_path.rename(self._file_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    # ── Key Derivation ────────────────────────────────────────

    def _get_salt(self) -> bytes:
        data = self._load_data()
        if "salt" not in data:
            salt = os.urandom(32)
            data["salt"] = salt.hex()
            self._save_data()
        return bytes.fromhex(data["salt"])

    def _get_derived_key(self) -> bytes:
        if self._derived_key is not None:
            return self._derived_key

        machine_data = ":".join([
            platform.system(),
            str(Path.home()),
            os.getlogin() if hasattr(os, "getlogin") else os.environ.get("USER", "unknown"),
            self._app_id,
        ])

        salt = self._get_salt()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        self._derived_key = kdf.derive(machine_data.encode("utf-8"))
        return self._derived_key

    # ── Encrypt / Decrypt ─────────────────────────────────────

    def _encrypt(self, value: str) -> str:
        key = self._get_derived_key()
        nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
        return f"{nonce.hex()}:{ciphertext.hex()}"

    def _decrypt(self, encrypted: str) -> str | None:
        try:
            parts = encrypted.split(":")
            if len(parts) != 2:
                return None
            nonce = bytes.fromhex(parts[0])
            ciphertext = bytes.fromhex(parts[1])
            key = self._get_derived_key()
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception:
            return None

    # ── API Key Management ────────────────────────────────────

    def store_api_key(self, provider: str, api_key: str) -> None:
        data = self._load_data()
        data["values"][f"apiKey:{provider}"] = self._encrypt(api_key)
        self._save_data()

    def get_api_key(self, provider: str) -> str | None:
        data = self._load_data()
        encrypted = data["values"].get(f"apiKey:{provider}")
        if not encrypted:
            return None
        return self._decrypt(encrypted)

    def delete_api_key(self, provider: str) -> bool:
        data = self._load_data()
        key = f"apiKey:{provider}"
        if key not in data["values"]:
            return False
        del data["values"][key]
        self._save_data()
        return True

    def get_all_api_keys(self) -> dict[str, str | None]:
        providers = ["anthropic", "openai"]
        result: dict[str, str | None] = {}
        for p in providers:
            result[p] = self.get_api_key(p)
        return result

    def has_any_api_key(self) -> bool:
        keys = self.get_all_api_keys()
        return any(v is not None for v in keys.values())

    # ── Generic Key-Value ─────────────────────────────────────

    def set(self, key: str, value: str) -> None:
        data = self._load_data()
        data["values"][key] = self._encrypt(value)
        self._save_data()

    def get(self, key: str) -> str | None:
        data = self._load_data()
        encrypted = data["values"].get(key)
        if not encrypted:
            return None
        return self._decrypt(encrypted)

    def delete(self, key: str) -> bool:
        data = self._load_data()
        if key not in data["values"]:
            return False
        del data["values"][key]
        self._save_data()
        return True

    def has(self, key: str) -> bool:
        data = self._load_data()
        return key in data["values"]

    def clear(self) -> None:
        self._data = {"values": {}}
        self._derived_key = None
        self._save_data()
