r"""Generate an RSA key pair for Snowflake key-pair authentication.

Writes the private key OUTSIDE the repository (default: ~/.snowflake/) and
prints only the PUBLIC key, which is safe to paste into Snowsight:

    ALTER USER DATAMIND_SVC SET RSA_PUBLIC_KEY = '<printed value>';

Usage (PowerShell, from the repo root):
    .\.venv\Scripts\python.exe backend\scripts\generate_snowflake_keypair.py
    .\.venv\Scripts\python.exe backend\scripts\generate_snowflake_keypair.py --passphrase
"""

from __future__ import annotations

import argparse
import base64
import getpass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home() / ".snowflake" / "datamind_rsa_key.p8",
        help="Private key path (must be outside the repository).",
    )
    parser.add_argument(
        "--passphrase",
        action="store_true",
        help="Encrypt the private key with a passphrase (prompted, not echoed).",
    )
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    if REPO_ROOT in out.parents:
        raise SystemExit("Refusing to write a private key inside the repository.")
    if out.exists():
        raise SystemExit(f"{out} already exists; not overwriting.")

    encryption: serialization.KeySerializationEncryption = serialization.NoEncryption()
    if args.passphrase:
        first = getpass.getpass("Passphrase: ")
        if not first or first != getpass.getpass("Repeat passphrase: "):
            raise SystemExit("Passphrases were empty or did not match.")
        encryption = serialization.BestAvailableEncryption(first.encode())

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
        )
    )
    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    print(f"Private key written to: {out}")
    print("Set SNOWFLAKE_PRIVATE_KEY_PATH to that path in backend\\.env.\n")
    print("Run in Snowsight (public key only, safe to share):")
    print(
        "ALTER USER DATAMIND_SVC SET RSA_PUBLIC_KEY = '"
        + base64.b64encode(public_der).decode()
        + "';"
    )


if __name__ == "__main__":
    main()
