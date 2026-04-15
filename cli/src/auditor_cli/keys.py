"""ed25519 key generation, storage, and signing."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


KEY_FILE_VERSION = 1
DEFAULT_KEY_DIR = Path.home() / ".auditor" / "keys"
DEFAULT_KEY_PATH = DEFAULT_KEY_DIR / "default.json"


@dataclass
class KeyPair:
    """An ed25519 keypair loaded from disk."""

    public_key_hex: str  # 64 hex chars
    secret_key_hex: str  # 64 hex chars (raw 32-byte seed)

    @property
    def _private(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.secret_key_hex))

    def sign(self, message: bytes) -> str:
        """Return hex-encoded 64-byte ed25519 signature."""
        return self._private.sign(message).hex()

    def verify(self, message: bytes, signature_hex: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.public_key_hex)).verify(
                bytes.fromhex(signature_hex), message
            )
            return True
        except (InvalidSignature, ValueError):
            return False


def generate_keypair() -> KeyPair:
    sk = Ed25519PrivateKey.generate()
    sk_bytes = sk.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pk_bytes = sk.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    return KeyPair(public_key_hex=pk_bytes.hex(), secret_key_hex=sk_bytes.hex())


def save_keypair(kp: KeyPair, path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)")

    path.parent.mkdir(parents=True, exist_ok=True)
    # Best-effort 0700 on the parent dir (no-op on non-POSIX).
    try:
        os.chmod(path.parent, stat.S_IRWXU)
    except OSError:
        pass

    payload = {
        "version": KEY_FILE_VERSION,
        "alg": "ed25519",
        "public_key": kp.public_key_hex,
        "secret_key": kp.secret_key_hex,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    tmp.replace(path)


def load_keypair(path: Path) -> KeyPair:
    data = json.loads(path.read_text())
    if data.get("alg") != "ed25519":
        raise ValueError(f"unsupported key alg: {data.get('alg')!r}")
    pk = data["public_key"]
    sk = data["secret_key"]
    if len(pk) != 64 or len(sk) != 64:
        raise ValueError("key file must contain 64-hex public_key and secret_key")

    # Sanity check: derived pubkey must match stored pubkey.
    derived_pk = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sk))
        .public_key()
        .public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
        .hex()
    )
    if derived_pk.lower() != pk.lower():
        raise ValueError(f"key file is corrupt: stored pubkey does not match secret ({path})")

    return KeyPair(public_key_hex=pk, secret_key_hex=sk)


def resolve_key_path(explicit: str | None) -> Path:
    """Resolve a key path from flag > env > default."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("AUDITOR_KEY")
    if env:
        return Path(env).expanduser()
    return DEFAULT_KEY_PATH
