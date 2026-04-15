from __future__ import annotations

import argparse
from pathlib import Path

from ..keys import DEFAULT_KEY_PATH, generate_keypair, save_keypair


def run(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser() if args.out else DEFAULT_KEY_PATH
    kp = generate_keypair()
    save_keypair(kp, out, force=args.force)
    print(f"Wrote ed25519 keypair to {out}")
    print(f"  public_key: {kp.public_key_hex}")
    return 0
