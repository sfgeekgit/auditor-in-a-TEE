"""
Ed25519 signing utilities for the auditor CLI.

Users generate a keypair once. The private key stays local,
the public key is shared with the plan.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


def generate_keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair. Returns (private_key_hex, public_key_hex)."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return private_bytes.hex(), public_bytes.hex()


def sign(private_key_hex: str, message: str) -> str:
    """Sign a message with an Ed25519 private key. Returns signature hex."""
    private_bytes = bytes.fromhex(private_key_hex)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    signature = private_key.sign(message.encode())
    return signature.hex()


def verify(public_key_hex: str, message: str, signature_hex: str) -> bool:
    """Verify an Ed25519 signature. Returns True if valid."""
    try:
        public_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, message.encode())
        return True
    except Exception:
        return False


def public_key_from_private(private_key_hex: str) -> str:
    """Derive the public key from a private key."""
    private_bytes = bytes.fromhex(private_key_hex)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public_bytes.hex()
