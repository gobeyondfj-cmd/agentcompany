"""High-level wallet manager used by Company and CLI."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from agent_company_ai.storage.database import Database
from agent_company_ai.storage.models import PaymentRecord, PaymentStatus
from agent_company_ai.wallet.chains import get_chain, list_chain_names
from agent_company_ai.wallet.keystore import create_wallet, decrypt_key, load_address
from agent_company_ai.wallet.provider import Web3Provider

logger = logging.getLogger("agent_company_ai.wallet.manager")


class WalletManager:
    """Orchestrates keystore, Web3 provider, and database for wallet operations."""

    def __init__(self, wallet_dir: Path, db: Database) -> None:
        self.wallet_dir = wallet_dir
        self.db = db
        self.provider = Web3Provider()

    # ------------------------------------------------------------------
    # Wallet lifecycle
    # ------------------------------------------------------------------

    def create(self, password: str) -> str:
        """Create a new wallet and return the address."""
        return create_wallet(self.wallet_dir, password)

    def has_wallet(self) -> bool:
        """Check whether a keystore exists."""
        return (self.wallet_dir / "keystore.json").exists()

    @property
    def address(self) -> str | None:
        """The wallet address, or ``None`` if no wallet exists."""
        return load_address(self.wallet_dir)

    # ------------------------------------------------------------------
    # Balances
    # ------------------------------------------------------------------

    def get_balance(self, chain_name: str | None = None) -> dict:
        """Get native token balance(s).

        If *chain_name* is ``None``, returns balances for all chains.
        """
        addr = self.address
        if addr is None:
            return {"error": "No wallet found. Run 'agent-company-ai wallet create'."}

        if chain_name:
            chain = get_chain(chain_name)
            try:
                balance = self.provider.get_native_balance(addr, chain_name)
                return {
                    chain_name: {
                        "balance": str(balance),
                        "symbol": chain.native_symbol,
                        "error": None,
                    }
                }
            except Exception as e:
                return {chain_name: {"balance": "0", "symbol": chain.native_symbol, "error": str(e)}}

        return self.provider.get_all_native_balances(addr)

    # ------------------------------------------------------------------
    # Payment queue
    # ------------------------------------------------------------------

    async def queue_payment(
        self,
        to_address: str,
        amount: str,
        chain: str,
        reason: str = "",
        requested_by: str | None = None,
    ) -> PaymentRecord:
        """Insert a payment request into the queue. Does NOT send funds."""
        record = PaymentRecord(
            to_address=to_address,
            amount=amount,
            chain=chain,
            reason=reason,
            requested_by=requested_by,
        )
        await self.db.execute(
            "INSERT INTO payment_queue "
            "(id, to_address, amount, token, chain, reason, requested_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.to_address,
                record.amount,
                record.token,
                record.chain,
                record.reason,
                record.requested_by,
                record.status.value,
            ),
        )
        logger.info(
            f"Payment queued: {record.amount} {record.token} to {record.to_address} "
            f"on {record.chain} (id={record.id})"
        )
        return record

    async def list_payments(self, status: str | None = None) -> list[dict]:
        """List payments, optionally filtered by status."""
        if status:
            return await self.db.fetch_all(
                "SELECT * FROM payment_queue WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        return await self.db.fetch_all(
            "SELECT * FROM payment_queue ORDER BY created_at DESC"
        )

    async def get_payment(self, payment_id: str) -> dict | None:
        """Fetch a single payment by ID."""
        return await self.db.fetch_one(
            "SELECT * FROM payment_queue WHERE id = ?", (payment_id,)
        )

    # ------------------------------------------------------------------
    # Approve / reject / send
    # ------------------------------------------------------------------

    async def approve_and_send(self, payment_id: str, password: str) -> str:
        """Decrypt the key, send the transaction, and update the payment record.

        This method should ONLY be called from the CLI (human-initiated).

        Returns the transaction hash.
        """
        payment = await self.get_payment(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found.")
        if payment["status"] != PaymentStatus.PENDING.value:
            raise ValueError(
                f"Payment {payment_id} is '{payment['status']}', not pending."
            )

        # Mark as approved
        await self.db.execute(
            "UPDATE payment_queue SET status = ? WHERE id = ?",
            (PaymentStatus.APPROVED.value, payment_id),
        )

        try:
            private_key = decrypt_key(self.wallet_dir, password)
            tx_hash = self.provider.send_transaction(
                private_key=private_key,
                to_address=payment["to_address"],
                amount_ether=payment["amount"],
                chain_name=payment["chain"],
            )
        except Exception as exc:
            await self.db.execute(
                "UPDATE payment_queue SET status = ? WHERE id = ?",
                (PaymentStatus.FAILED.value, payment_id),
            )
            raise RuntimeError(f"Transaction failed: {exc}") from exc

        # Mark as sent
        await self.db.execute(
            "UPDATE payment_queue SET status = ?, tx_hash = ?, executed_at = ? WHERE id = ?",
            (PaymentStatus.SENT.value, tx_hash, datetime.utcnow().isoformat(), payment_id),
        )
        logger.info(f"Payment {payment_id} sent: tx={tx_hash}")
        return tx_hash

    async def reject_payment(self, payment_id: str) -> None:
        """Reject a pending payment."""
        payment = await self.get_payment(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found.")
        if payment["status"] != PaymentStatus.PENDING.value:
            raise ValueError(
                f"Payment {payment_id} is '{payment['status']}', not pending."
            )
        await self.db.execute(
            "UPDATE payment_queue SET status = ? WHERE id = ?",
            (PaymentStatus.REJECTED.value, payment_id),
        )
        logger.info(f"Payment {payment_id} rejected.")

    # ------------------------------------------------------------------
    # DB registration
    # ------------------------------------------------------------------

    async def register_wallet_in_db(self) -> None:
        """Persist the wallet address to the wallets table (idempotent)."""
        addr = self.address
        if addr is None:
            return
        existing = await self.db.fetch_one(
            "SELECT id FROM wallets WHERE address = ?", (addr,)
        )
        if existing:
            return
        wallet_id = uuid.uuid4().hex[:12]
        await self.db.execute(
            "INSERT INTO wallets (id, address, keystore_path) VALUES (?, ?, ?)",
            (wallet_id, addr, str(self.wallet_dir / "keystore.json")),
        )
        logger.info(f"Wallet {addr} registered in DB.")
