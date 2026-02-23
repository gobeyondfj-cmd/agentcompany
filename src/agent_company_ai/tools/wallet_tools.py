"""Agent-facing wallet tools.

These tools let agents check balances, view the wallet address, queue
payment requests, and create crypto payment links. Agents can NEVER send
funds directly -- they can only insert payment requests that require
human approval via the CLI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database
    from agent_company_ai.wallet.manager import WalletManager

logger = logging.getLogger("agent_company_ai.tools.wallet")

# Module-level state, set at runtime by Company
_wallet_manager: WalletManager | None = None
_current_agent_name: str = "unknown"
_db: Database | None = None
_company_dir: Path | None = None


def set_wallet_manager(manager: WalletManager) -> None:
    """Inject the WalletManager instance (called by Company on startup)."""
    global _wallet_manager
    _wallet_manager = manager


def set_current_agent(name: str) -> None:
    """Set the current agent name for payment attribution."""
    global _current_agent_name
    _current_agent_name = name


def set_wallet_db(db: Database) -> None:
    global _db
    _db = db


def set_wallet_company_dir(company_dir: Path) -> None:
    global _company_dir
    _company_dir = company_dir


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


# ------------------------------------------------------------------
# Crypto payment links
# ------------------------------------------------------------------

_CRYPTO_PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pay — {product_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f0f0f; color: #e0e0e0; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; }}
  .card {{ background: #1a1a2e; border-radius: 16px; padding: 40px;
           max-width: 480px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }}
  h1 {{ font-size: 1.5rem; margin-bottom: 8px; color: #fff; }}
  .price {{ font-size: 2.2rem; font-weight: 700; color: #00d4aa;
            margin: 16px 0; }}
  .desc {{ color: #999; margin-bottom: 24px; line-height: 1.5; }}
  .field {{ margin-bottom: 20px; }}
  .field label {{ display: block; font-size: 0.8rem; text-transform: uppercase;
                  letter-spacing: 0.5px; color: #888; margin-bottom: 6px; }}
  .addr {{ background: #0f0f1a; border: 1px solid #333; border-radius: 8px;
           padding: 12px 14px; font-family: monospace; font-size: 0.85rem;
           word-break: break-all; color: #e0e0e0; cursor: pointer;
           transition: border-color 0.2s; position: relative; }}
  .addr:hover {{ border-color: #00d4aa; }}
  .addr::after {{ content: 'click to copy'; position: absolute; right: 10px;
                  top: 50%; transform: translateY(-50%); font-size: 0.7rem;
                  color: #555; font-family: sans-serif; }}
  .chain-badge {{ display: inline-block; background: #16213e; color: #4fc3f7;
                  padding: 4px 12px; border-radius: 20px; font-size: 0.8rem;
                  margin-right: 8px; }}
  .note {{ margin-top: 24px; font-size: 0.8rem; color: #666; line-height: 1.5;
           border-top: 1px solid #222; padding-top: 16px; }}
  .copied {{ color: #00d4aa !important; }}
</style>
</head>
<body>
<div class="card">
  <h1>{product_name}</h1>
  {desc_html}
  <div class="price">{amount} {symbol}</div>
  <div class="field">
    <label>Send to wallet address</label>
    <div class="addr" id="addr" onclick="copyAddr()">{wallet_address}</div>
  </div>
  <div class="field">
    <label>Network</label>
    <span class="chain-badge">{chain_display}</span>
  </div>
  {explorer_html}
  <div class="note">
    Send <strong>exactly {amount} {symbol}</strong> on the <strong>{chain_display}</strong>
    network to the address above. The payment will be confirmed once the transaction
    is verified on-chain. Do not send tokens on any other network.
  </div>
</div>
<script>
function copyAddr() {{
  navigator.clipboard.writeText("{wallet_address}");
  var el = document.getElementById("addr");
  el.classList.add("copied");
  el.setAttribute("data-after", "copied!");
  setTimeout(function() {{ el.classList.remove("copied"); }}, 2000);
}}
</script>
</body>
</html>
"""


@tool(
    "create_crypto_payment_link",
    (
        "Create a crypto payment page that shows the company wallet address, "
        "amount, and chain so a customer can pay with cryptocurrency. "
        "Generates an HTML page and returns its file path."
    ),
    {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "Name of the product or service being purchased",
            },
            "amount": {
                "type": "string",
                "description": "Amount to pay in native token (e.g. '0.05' for 0.05 ETH)",
            },
            "chain": {
                "type": "string",
                "description": "Blockchain network: ethereum, base, arbitrum, polygon. Default: ethereum",
                "enum": ["ethereum", "base", "arbitrum", "polygon"],
            },
            "description": {
                "type": "string",
                "description": "Product description shown on the payment page",
            },
        },
        "required": ["product_name", "amount"],
    },
)
async def create_crypto_payment_link(
    product_name: str,
    amount: str,
    chain: str = "ethereum",
    description: str = "",
) -> str:
    from agent_company_ai.wallet.chains import get_chain, list_chain_names
    from agent_company_ai.tools.rate_limiter import RateLimiter
    import re

    mgr = _require_wallet()
    addr = mgr.address
    if addr is None:
        return "Error: no wallet found. Ask the owner to run 'agent-company-ai wallet create' first."

    chain = chain.strip().lower() or "ethereum"
    try:
        chain_info = get_chain(chain)
    except KeyError:
        return f"Error: unknown chain '{chain}'. Available: {list_chain_names()}"

    if not product_name.strip():
        return "Error: product_name is required."

    try:
        amount_f = float(amount)
        if amount_f <= 0:
            return "Error: amount must be positive."
    except ValueError:
        return f"Error: invalid amount '{amount}'. Provide a number like '0.05'."

    # Rate limit (shares payment_links_daily with Stripe)
    limiter = RateLimiter.get()
    if not limiter.check("payment_links_daily"):
        return "Rate limit exceeded: daily payment link limit reached. Try again later."

    # Build HTML
    desc_html = f'<div class="desc">{description}</div>' if description else ""
    explorer_html = (
        f'<div class="field"><label>Verify on explorer</label>'
        f'<a href="{chain_info.explorer_url}/address/{addr}" '
        f'target="_blank" style="color:#4fc3f7;font-size:0.85rem;">'
        f'{chain_info.explorer_url}</a></div>'
    )
    html = _CRYPTO_PAGE_TEMPLATE.format(
        product_name=product_name,
        amount=amount,
        symbol=chain_info.native_symbol,
        wallet_address=addr,
        chain_display=chain_info.name.capitalize(),
        desc_html=desc_html,
        explorer_html=explorer_html,
    )

    # Save HTML file
    if _company_dir:
        out_dir = _company_dir / "landing_pages"
    else:
        return "Error: company directory not configured."

    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", product_name.lower()).strip("-")
    slug = f"pay-crypto-{slug}"
    file_path = out_dir / f"{slug}.html"

    # Avoid overwriting — append counter if needed
    counter = 1
    while file_path.exists():
        counter += 1
        file_path = out_dir / f"{slug}-{counter}.html"

    file_path.write_text(html, encoding="utf-8")
    limiter.record("payment_links_daily")

    # Log to payment_links table
    amount_cents = int(round(amount_f * 100))
    if _db:
        await _db.execute(
            "INSERT INTO payment_links "
            "(stripe_url, stripe_price_id, stripe_payment_link_id, product_name, "
            "amount_cents, currency, status, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (
                str(file_path),  # file path instead of stripe URL
                f"crypto:{chain}",  # chain identifier instead of stripe price ID
                f"wallet:{addr}",  # wallet address instead of stripe link ID
                product_name,
                amount_cents,
                chain_info.native_symbol.lower(),
                _current_agent_name,
            ),
        )

    logger.info(f"Crypto payment page created: {file_path}")
    return (
        f"Crypto payment page created!\n"
        f"  Product: {product_name}\n"
        f"  Amount: {amount} {chain_info.native_symbol}\n"
        f"  Chain: {chain_info.name.capitalize()}\n"
        f"  Wallet: {addr}\n"
        f"  File: {file_path}\n"
        f"  Customers can send crypto to the wallet address shown on the page."
    )
