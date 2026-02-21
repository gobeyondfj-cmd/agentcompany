"""Blockchain wallet system for Agent Company AI.

Provides Ethereum-compatible wallet management with encrypted keystore,
multi-chain support (Ethereum, Base, Arbitrum, Polygon), and a human-approval
payment queue. Agents can only queue payment requests; only humans can
approve and send transactions via the CLI.
"""
