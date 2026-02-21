"""Encrypted keystore management using eth-account."""

from __future__ import annotations

import json
from pathlib import Path

from eth_account import Account


def create_wallet(wallet_dir: Path, password: str) -> str:
    """Generate a new Ethereum keypair and save an encrypted keystore file.

    Parameters
    ----------
    wallet_dir:
        Directory where ``keystore.json`` will be written.
    password:
        Password used to encrypt the private key.

    Returns
    -------
    str
        The checksummed Ethereum address of the new wallet.

    Raises
    ------
    FileExistsError
        If a keystore already exists in *wallet_dir*.
    """
    keystore_path = wallet_dir / "keystore.json"
    if keystore_path.exists():
        raise FileExistsError(
            f"Wallet already exists at {keystore_path}. "
            "Delete it first if you want to create a new one."
        )

    acct = Account.create()
    encrypted = Account.encrypt(acct.key, password)

    wallet_dir.mkdir(parents=True, exist_ok=True)
    keystore_path.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")

    return acct.address


def load_address(wallet_dir: Path) -> str | None:
    """Read the wallet address from a keystore file without decrypting.

    Returns ``None`` if no keystore file exists.
    """
    keystore_path = wallet_dir / "keystore.json"
    if not keystore_path.exists():
        return None

    data = json.loads(keystore_path.read_text(encoding="utf-8"))
    raw_address = data.get("address", "")
    if not raw_address.startswith("0x"):
        raw_address = "0x" + raw_address
    from web3 import Web3

    return Web3.to_checksum_address(raw_address)


def decrypt_key(wallet_dir: Path, password: str) -> bytes:
    """Decrypt the private key from the keystore.

    Parameters
    ----------
    wallet_dir:
        Directory containing ``keystore.json``.
    password:
        Password that was used to encrypt the key.

    Returns
    -------
    bytes
        The raw 32-byte private key.

    Raises
    ------
    FileNotFoundError
        If no keystore file exists.
    ValueError
        If the password is incorrect.
    """
    keystore_path = wallet_dir / "keystore.json"
    if not keystore_path.exists():
        raise FileNotFoundError(f"No keystore found at {keystore_path}")

    data = json.loads(keystore_path.read_text(encoding="utf-8"))
    try:
        return Account.decrypt(data, password)
    except Exception as exc:
        raise ValueError(f"Failed to decrypt keystore: {exc}") from exc
