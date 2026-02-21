"""Web3 multi-chain provider for Ethereum-compatible networks."""

from __future__ import annotations

import logging
from decimal import Decimal

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from agent_company_ai.wallet.chains import CHAINS, get_chain

logger = logging.getLogger("agent_company_ai.wallet.provider")


class Web3Provider:
    """Manages Web3 connections across multiple EVM chains."""

    def __init__(self) -> None:
        self._instances: dict[str, Web3] = {}

    def get_web3(self, chain_name: str) -> Web3:
        """Return a (cached) Web3 instance for the given chain.

        Injects POA middleware for non-mainnet chains.
        """
        if chain_name in self._instances:
            return self._instances[chain_name]

        chain = get_chain(chain_name)
        w3 = Web3(Web3.HTTPProvider(chain.rpc_url))

        # Inject POA middleware for non-mainnet chains (Base, Arbitrum, Polygon)
        if chain.chain_id != 1:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self._instances[chain_name] = w3
        return w3

    def get_native_balance(self, address: str, chain_name: str) -> Decimal:
        """Get the native token balance in human-readable units (e.g. ETH)."""
        w3 = self.get_web3(chain_name)
        checksum = Web3.to_checksum_address(address)
        balance_wei = w3.eth.get_balance(checksum)
        return Decimal(str(Web3.from_wei(balance_wei, "ether")))

    def get_all_native_balances(self, address: str) -> dict[str, dict]:
        """Get native balances across all supported chains.

        Returns a dict mapping chain name to {balance, symbol, error}.
        Errors on individual chains don't abort the whole operation.
        """
        results = {}
        for chain_name, chain in CHAINS.items():
            try:
                balance = self.get_native_balance(address, chain_name)
                results[chain_name] = {
                    "balance": str(balance),
                    "symbol": chain.native_symbol,
                    "error": None,
                }
            except Exception as e:
                logger.warning(f"Failed to get balance on {chain_name}: {e}")
                results[chain_name] = {
                    "balance": "0",
                    "symbol": chain.native_symbol,
                    "error": str(e),
                }
        return results

    def send_transaction(
        self,
        private_key: bytes,
        to_address: str,
        amount_ether: str | Decimal,
        chain_name: str,
    ) -> str:
        """Build, sign, and send a native-token transfer.

        Uses EIP-1559 fee parameters with a legacy gas price fallback.

        Returns the transaction hash as a hex string.
        """
        w3 = self.get_web3(chain_name)
        chain = get_chain(chain_name)
        checksum_to = Web3.to_checksum_address(to_address)
        from_account = w3.eth.account.from_key(private_key)
        nonce = w3.eth.get_transaction_count(from_account.address)
        value = Web3.to_wei(Decimal(str(amount_ether)), "ether")

        tx: dict = {
            "to": checksum_to,
            "value": value,
            "nonce": nonce,
            "chainId": chain.chain_id,
        }

        # Try EIP-1559 first, fall back to legacy gas price
        try:
            latest = w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas")
            if base_fee is not None:
                max_priority = Web3.to_wei(1.5, "gwei")
                tx["maxFeePerGas"] = base_fee * 2 + max_priority
                tx["maxPriorityFeePerGas"] = max_priority
                tx["gas"] = w3.eth.estimate_gas(tx)
            else:
                raise ValueError("No baseFeePerGas")
        except Exception:
            tx["gasPrice"] = w3.eth.gas_price
            tx["gas"] = w3.eth.estimate_gas(tx)

        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()
