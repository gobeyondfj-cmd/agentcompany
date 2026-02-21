"""Chain definitions for supported EVM networks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    """An EVM-compatible blockchain network."""

    name: str
    chain_id: int
    rpc_url: str
    native_symbol: str
    explorer_url: str


CHAINS: dict[str, Chain] = {
    "ethereum": Chain(
        name="ethereum",
        chain_id=1,
        rpc_url="https://eth.llamarpc.com",
        native_symbol="ETH",
        explorer_url="https://etherscan.io",
    ),
    "base": Chain(
        name="base",
        chain_id=8453,
        rpc_url="https://mainnet.base.org",
        native_symbol="ETH",
        explorer_url="https://basescan.org",
    ),
    "arbitrum": Chain(
        name="arbitrum",
        chain_id=42161,
        rpc_url="https://arb1.arbitrum.io/rpc",
        native_symbol="ETH",
        explorer_url="https://arbiscan.io",
    ),
    "polygon": Chain(
        name="polygon",
        chain_id=137,
        rpc_url="https://polygon-rpc.com",
        native_symbol="POL",
        explorer_url="https://polygonscan.com",
    ),
}


def get_chain(name: str) -> Chain:
    """Get a chain by name. Raises ``KeyError`` if not found."""
    if name not in CHAINS:
        raise KeyError(
            f"Unknown chain '{name}'. Available: {list_chain_names()}"
        )
    return CHAINS[name]


def list_chain_names() -> list[str]:
    """Return the names of all supported chains."""
    return list(CHAINS.keys())
