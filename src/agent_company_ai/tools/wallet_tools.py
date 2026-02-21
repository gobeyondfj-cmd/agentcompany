"""Agent-facing wallet tools.

These tools let agents check balances, view the wallet address, and queue
payment requests. Agents can NEVER send funds directly -- they can only
insert payment requests that require human approval via the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.wallet.manager import WalletManager

# Module-level state, set at runtime by Company
_wallet_manager: WalletManager | None = None
_current_agent_name: str = "unknown"


def set_wallet_manager(manager: WalletManager) -> None:
    """Inject the WalletManager instance (called by Company on startup)."""
    global _wallet_manager
    _wallet_manager = manager


def set_current_agent(name: str) -> None:
    """Set the current agent name for payment attribution."""
    global _current_agent_name
    _current_agent_name = name


def _require_wallet() -> WalletManager:
    if _wallet_manager is None:
        raise RuntimeError(
            "Wallet not configured. Run 'agent-company-ai wallet create' first."
        )
    return _wallet_manager


@tool(
    "check_balance",
    "Check the company wallet's native token balance on one or all supported chains.",
    {
        "type": "object",
        "properties": {
            "chain": {
                "type": "string",
                "description": (
                    "Chain to check (ethereum, base, arbitrum, polygon). "
                    "Omit or pass empty string for all chains."
                ),
            }
        },
        "required": [],
    },
)
def check_balance(chain: str = "") -> str:
    mgr = _require_wallet()
    chain_name = chain.strip().lower() or None
    result = mgr.get_balance(chain_name)

    if "error" in result:
        return f"Error: {result['error']}"

    lines = ["Company wallet balances:"]
    for name, info in result.items():
        bal = info["balance"]
        sym = info["symbol"]
        err = info.get("error")
        if err:
            lines.append(f"  {name}: error ({err})")
        else:
            lines.append(f"  {name}: {bal} {sym}")
    return "\n".join(lines)


@tool(
    "get_wallet_address",
    "Get the company wallet's Ethereum address (same address on all EVM chains).",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def get_wallet_address() -> str:
    mgr = _require_wallet()
    addr = mgr.address
    if addr is None:
        return "No wallet found. Ask the owner to create one."
    return f"Company wallet address: {addr}"


@tool(
    "request_payment",
    (
        "Queue a payment request for human approval. This does NOT send any funds. "
        "The payment will be reviewed and approved/rejected by the company owner via CLI."
    ),
    {
        "type": "object",
        "properties": {
            "to_address": {
                "type": "string",
                "description": "Recipient Ethereum address (0x...)",
            },
            "amount": {
                "type": "string",
                "description": "Amount in native token (e.g. '0.01' for 0.01 ETH)",
            },
            "chain": {
                "type": "string",
                "description": "Target chain (ethereum, base, arbitrum, polygon). Default: ethereum",
            },
            "reason": {
                "type": "string",
                "description": "Business reason for this payment",
            },
        },
        "required": ["to_address", "amount", "reason"],
    },
)
async def request_payment(
    to_address: str,
    amount: str,
    reason: str,
    chain: str = "ethereum",
) -> str:
    mgr = _require_wallet()
    record = await mgr.queue_payment(
        to_address=to_address,
        amount=amount,
        chain=chain.strip().lower(),
        reason=reason,
        requested_by=_current_agent_name,
    )
    return (
        f"Payment request queued (ID: {record.id}).\n"
        f"  To: {record.to_address}\n"
        f"  Amount: {record.amount} {record.token}\n"
        f"  Chain: {record.chain}\n"
        f"  Reason: {record.reason}\n"
        f"  Status: pending (awaiting human approval)"
    )


@tool(
    "list_payments",
    "List payment requests in the queue, optionally filtered by status.",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status: pending, approved, rejected, sent, failed. Leave empty for all.",
            },
        },
        "required": [],
    },
)
async def list_payments(status: str = "") -> str:
    mgr = _require_wallet()
    status_filter = status.strip().lower() or None
    payments = await mgr.list_payments(status=status_filter)

    if not payments:
        return "No payments found."

    lines = [f"Payment queue ({len(payments)} entries):"]
    for p in payments:
        lines.append(
            f"  [{p['id']}] {p['amount']} {p['token']} -> {p['to_address'][:10]}... "
            f"on {p['chain']} | {p['status']} | {p['reason'][:50]}"
        )
    return "\n".join(lines)
