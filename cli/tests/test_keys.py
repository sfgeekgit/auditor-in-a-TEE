"""Keypair roundtrip: generate, save, load, sign, verify."""

from pathlib import Path

import pytest

from auditor_cli.keys import (
    KeyPair,
    generate_keypair,
    load_keypair,
    save_keypair,
)


def test_generated_pubkey_is_64_hex():
    kp = generate_keypair()
    assert len(kp.public_key_hex) == 64
    assert len(kp.secret_key_hex) == 64
    int(kp.public_key_hex, 16)  # valid hex
    int(kp.secret_key_hex, 16)


def test_sign_verify_roundtrip():
    kp = generate_keypair()
    msg = b"hello world"
    sig = kp.sign(msg)
    assert len(sig) == 128
    assert kp.verify(msg, sig) is True


def test_verify_fails_on_tampered_message():
    kp = generate_keypair()
    sig = kp.sign(b"message A")
    assert kp.verify(b"message B", sig) is False


def test_save_and_load_roundtrip(tmp_path: Path):
    kp = generate_keypair()
    path = tmp_path / "k.json"
    save_keypair(kp, path)
    loaded = load_keypair(path)
    assert loaded.public_key_hex == kp.public_key_hex
    assert loaded.secret_key_hex == kp.secret_key_hex


def test_save_refuses_overwrite(tmp_path: Path):
    kp = generate_keypair()
    path = tmp_path / "k.json"
    save_keypair(kp, path)
    with pytest.raises(FileExistsError):
        save_keypair(generate_keypair(), path)
    save_keypair(generate_keypair(), path, force=True)  # force ok


def test_load_rejects_mismatched_keypair(tmp_path: Path):
    """If someone hand-edits the file to put a mismatched pubkey, we catch it."""
    kp = generate_keypair()
    other = generate_keypair()
    path = tmp_path / "k.json"
    import json

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "alg": "ed25519",
                "public_key": other.public_key_hex,  # wrong!
                "secret_key": kp.secret_key_hex,
            }
        )
    )
    with pytest.raises(ValueError, match="corrupt"):
        load_keypair(path)
