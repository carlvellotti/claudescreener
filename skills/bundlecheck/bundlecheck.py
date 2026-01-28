#!/usr/bin/env python3
"""
BundleCheck - Solana Token Launch Manipulation Detector
Part of ClaudeScreener

Detects coordinated sniping at token launch by analyzing Block 0 purchases.

Usage:
  python3 bundlecheck.py <contract_address>
"""

import sys
import json
import os
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone
from collections import defaultdict

def load_env_var(var_name: str) -> str | None:
    """
    Load environment variable, checking multiple sources:
    1. Environment variables (already set)
    2. .env file in current directory
    3. .env file in script directory
    """
    value = os.environ.get(var_name)
    if value:
        return value

    script_dir = os.path.dirname(__file__)
    env_paths = [
        ".env",
        os.path.join(script_dir, ".env"),
        os.path.join(script_dir, "..", ".env"),
        os.path.join(script_dir, "..", "..", ".env"),
        os.path.join(script_dir, "..", "..", "..", ".env"),  # vault root
    ]

    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{var_name}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def require_helius_api_key() -> str:
    """Check for Helius API key and exit with helpful message if missing."""
    value = load_env_var("HELIUS_API_KEY")
    if not value:
        print("ERROR: HELIUS_API_KEY not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("BundleCheck requires a Helius API key to fetch transaction history.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Setup:", file=sys.stderr)
        print("  1. Get a free API key at: https://helius.dev", file=sys.stderr)
        print("  2. Set it: export HELIUS_API_KEY=your_key_here", file=sys.stderr)
        print("     Or add to .env file: HELIUS_API_KEY=your_key_here", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run /claudescreener:setup for guided setup help.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_json(url: str, headers: dict = None, timeout: int = 30) -> dict | None:
    """Fetch JSON from URL with error handling."""
    try:
        req_headers = {"User-Agent": "BundleCheck/1.0"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def get_helius_transactions(address: str, limit: int = 100) -> list | None:
    """Fetch transaction history from Helius."""
    api_key = load_env_var("HELIUS_API_KEY")
    if not api_key:
        return None

    url = f"https://api.helius.xyz/v0/addresses/{address}/transactions?api-key={api_key}&limit={limit}"
    return fetch_json(url, timeout=30)


def get_token_info(mint: str) -> dict | None:
    """Get basic token info from DexScreener."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    data = fetch_json(url)
    if data and data.get("pairs"):
        pair = data["pairs"][0]
        return {
            "name": pair.get("baseToken", {}).get("name", "Unknown"),
            "symbol": pair.get("baseToken", {}).get("symbol", "???"),
            "liquidity": pair.get("liquidity", {}).get("usd", 0),
            "marketCap": pair.get("marketCap", 0),
        }
    return None


def analyze_launch_transactions(transactions: list, mint: str) -> dict:
    """
    Analyze transactions to detect Block 0 sniping.

    Returns:
    - creation_slot: The slot where token was created
    - block0_buyers: List of wallets that bought in Block 0
    - block0_supply_pct: Estimated % of supply bought in Block 0
    - early_buyers: Buyers in first few blocks
    """
    if not transactions:
        return {"error": "No transactions found"}

    # Sort by timestamp (oldest first)
    sorted_txs = sorted(transactions, key=lambda x: x.get("timestamp", 0))

    # Find the creation slot (earliest transaction)
    creation_slot = None
    creation_timestamp = None

    for tx in sorted_txs:
        slot = tx.get("slot")
        if slot:
            creation_slot = slot
            creation_timestamp = tx.get("timestamp", 0)
            break

    if not creation_slot:
        return {"error": "Could not determine creation slot"}

    # Analyze buyers by slot
    buyers_by_slot = defaultdict(list)
    wallet_purchases = defaultdict(lambda: {"amount": 0, "slot": None, "is_block0": False})

    for tx in sorted_txs:
        slot = tx.get("slot", 0)
        slot_diff = slot - creation_slot if creation_slot else 0

        # Look for token transfers (buys)
        for transfer in tx.get("tokenTransfers", []):
            if transfer.get("mint") != mint:
                continue

            to_wallet = transfer.get("toUserAccount")
            from_wallet = transfer.get("fromUserAccount")
            amount = transfer.get("tokenAmount", 0)

            # Skip if it's from a known LP/pool pattern
            if not to_wallet or not amount:
                continue

            # This is a buy if tokens are going TO a wallet
            # and FROM a pool/program (not another user wallet)
            if to_wallet and amount > 0:
                is_block0 = slot_diff <= 1  # Same slot or next slot

                buyers_by_slot[slot_diff].append({
                    "wallet": to_wallet,
                    "amount": amount,
                    "slot": slot,
                })

                wallet_purchases[to_wallet]["amount"] += amount
                if wallet_purchases[to_wallet]["slot"] is None:
                    wallet_purchases[to_wallet]["slot"] = slot
                    wallet_purchases[to_wallet]["is_block0"] = is_block0

    # Calculate Block 0 stats
    block0_buyers = []
    block0_total = 0

    for wallet, data in wallet_purchases.items():
        if data["is_block0"]:
            block0_buyers.append({
                "wallet": wallet,
                "amount": data["amount"],
            })
            block0_total += data["amount"]

    # Sort by amount (largest first)
    block0_buyers.sort(key=lambda x: x["amount"], reverse=True)

    # Calculate total supply from all transfers (rough estimate)
    total_transferred = sum(d["amount"] for d in wallet_purchases.values())

    # Block 0 as percentage
    block0_pct = (block0_total / total_transferred * 100) if total_transferred > 0 else 0

    # Early buyers (first 5 slots)
    early_slots = [0, 1, 2, 3, 4, 5]
    early_buyer_count = sum(len(buyers_by_slot.get(s, [])) for s in early_slots)

    return {
        "creation_slot": creation_slot,
        "creation_timestamp": creation_timestamp,
        "block0_buyers": block0_buyers,
        "block0_count": len(block0_buyers),
        "block0_total": block0_total,
        "block0_pct": block0_pct,
        "total_transferred": total_transferred,
        "early_buyer_count": early_buyer_count,
        "all_buyers": len(wallet_purchases),
        "buyers_by_slot": {k: len(v) for k, v in sorted(buyers_by_slot.items())[:10]},
    }


def calculate_risk_score(analysis: dict) -> tuple[int, list[str]]:
    """
    Calculate manipulation risk score (0-100).

    Returns (score, list of reasons).
    """
    score = 0
    reasons = []

    block0_count = analysis.get("block0_count", 0)
    block0_pct = analysis.get("block0_pct", 0)
    block0_buyers = analysis.get("block0_buyers", [])

    # Number of Block 0 buyers
    if block0_count >= 20:
        score += 40
        reasons.append(f"+40: {block0_count} wallets bought in Block 0 (highly coordinated)")
    elif block0_count >= 10:
        score += 25
        reasons.append(f"+25: {block0_count} wallets bought in Block 0 (suspicious)")
    elif block0_count >= 5:
        score += 10
        reasons.append(f"+10: {block0_count} wallets bought in Block 0")

    # Block 0 supply concentration
    if block0_pct >= 50:
        score += 35
        reasons.append(f"+35: {block0_pct:.1f}% of supply grabbed in Block 0")
    elif block0_pct >= 30:
        score += 25
        reasons.append(f"+25: {block0_pct:.1f}% of supply grabbed in Block 0")
    elif block0_pct >= 15:
        score += 15
        reasons.append(f"+15: {block0_pct:.1f}% of supply grabbed in Block 0")
    elif block0_pct >= 5:
        score += 5
        reasons.append(f"+5: {block0_pct:.1f}% of supply grabbed in Block 0")

    # Single large sniper
    if block0_buyers:
        largest_buyer_pct = (block0_buyers[0]["amount"] / analysis.get("total_transferred", 1)) * 100
        if largest_buyer_pct >= 10:
            score += 20
            reasons.append(f"+20: Single wallet sniped {largest_buyer_pct:.1f}% in Block 0")
        elif largest_buyer_pct >= 5:
            score += 10
            reasons.append(f"+10: Single wallet sniped {largest_buyer_pct:.1f}% in Block 0")

    # Positive: Clean launch
    if block0_count <= 2 and block0_pct < 5:
        score -= 10
        reasons.append("-10: Clean launch (minimal Block 0 activity)")

    return max(0, min(100, score)), reasons


def get_risk_label(score: int) -> str:
    """Convert numeric score to risk label."""
    if score <= 15:
        return "🟢 LOW RISK"
    elif score <= 35:
        return "🟡 MODERATE"
    elif score <= 60:
        return "🟠 HIGH RISK"
    else:
        return "🔴 CRITICAL"


def format_number(n: float | int | None) -> str:
    """Format large numbers."""
    if n is None:
        return "N/A"
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:.0f}"


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp."""
    if not ts:
        return "Unknown"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_report(mint: str, token_info: dict | None, analysis: dict, score: int, reasons: list) -> str:
    """Format the final report."""
    lines = []

    # Header
    if token_info:
        name = token_info.get("name", "Unknown")
        symbol = token_info.get("symbol", "???")
        lines.append(f"# Bundle Check: {name} (${symbol})")
    else:
        lines.append(f"# Bundle Check")

    lines.append(f"**Token:** `{mint}`")

    if analysis.get("creation_timestamp"):
        lines.append(f"**Launched:** {format_timestamp(analysis['creation_timestamp'])}")
    lines.append("")

    # Risk Assessment
    risk_label = get_risk_label(score)
    lines.append(f"## Manipulation Risk: {risk_label} (Score: {score}/100)")
    lines.append("")

    # Score breakdown
    if reasons:
        lines.append("<details>")
        lines.append("<summary><b>Score Breakdown</b></summary>")
        lines.append("")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("</details>")
        lines.append("")

    # Block 0 Stats
    lines.append("## Block 0 Analysis")
    lines.append("")
    lines.append("| Metric | Value | Signal |")
    lines.append("|--------|-------|--------|")

    block0_count = analysis.get("block0_count", 0)
    block0_pct = analysis.get("block0_pct", 0)

    # Buyer count signal
    if block0_count >= 15:
        count_signal = "🚨 Highly coordinated"
    elif block0_count >= 8:
        count_signal = "⚠️ Suspicious"
    elif block0_count >= 3:
        count_signal = "ℹ️ Some activity"
    else:
        count_signal = "✅ Normal"

    lines.append(f"| Block 0 Buyers | {block0_count} wallets | {count_signal} |")

    # Supply concentration signal
    if block0_pct >= 30:
        pct_signal = "🚨 Major concentration"
    elif block0_pct >= 15:
        pct_signal = "⚠️ Elevated"
    elif block0_pct >= 5:
        pct_signal = "ℹ️ Moderate"
    else:
        pct_signal = "✅ Low"

    lines.append(f"| Supply Sniped | {block0_pct:.1f}% | {pct_signal} |")
    lines.append(f"| Total Early Buyers | {analysis.get('early_buyer_count', 0)} | First 5 blocks |")
    lines.append(f"| All Buyers Analyzed | {analysis.get('all_buyers', 0)} | — |")
    lines.append("")

    # Block 0 Buyers Table
    block0_buyers = analysis.get("block0_buyers", [])
    if block0_buyers:
        lines.append("## Block 0 Snipers")
        lines.append("")
        lines.append("| Rank | Wallet | Amount | % of Total |")
        lines.append("|------|--------|--------|------------|")

        total = analysis.get("total_transferred", 1)
        for i, buyer in enumerate(block0_buyers[:10], 1):
            wallet = buyer["wallet"]
            short_wallet = f"{wallet[:6]}...{wallet[-4:]}"
            amount = format_number(buyer["amount"])
            pct = (buyer["amount"] / total) * 100

            flag = "🚨" if pct >= 5 else "⚠️" if pct >= 2 else ""
            lines.append(f"| {i} | `{short_wallet}` | {amount} | {pct:.2f}% {flag} |")

        if len(block0_buyers) > 10:
            lines.append(f"| ... | *{len(block0_buyers) - 10} more* | | |")
        lines.append("")
    else:
        lines.append("## Block 0 Snipers")
        lines.append("*No Block 0 buyers detected - clean launch*")
        lines.append("")

    # Buyers by slot distribution
    buyers_by_slot = analysis.get("buyers_by_slot", {})
    if buyers_by_slot:
        lines.append("## Buy Distribution by Block")
        lines.append("")
        lines.append("| Block | Buyers |")
        lines.append("|-------|--------|")
        for slot_diff, count in list(buyers_by_slot.items())[:8]:
            label = "Block 0 (Launch)" if slot_diff == 0 else f"Block +{slot_diff}"
            lines.append(f"| {label} | {count} |")
        lines.append("")

    # Interpretation
    lines.append("## What This Means")
    lines.append("")

    if score >= 60:
        lines.append("🚨 **HIGH MANIPULATION RISK** - This launch shows strong signs of coordinated sniping.")
        lines.append("")
        lines.append("Multiple wallets buying in the same block as token creation is a classic bundling pattern.")
        lines.append("These wallets may be controlled by the same person/group and could coordinate a dump.")
    elif score >= 35:
        lines.append("⚠️ **MODERATE CONCERN** - Some suspicious Block 0 activity detected.")
        lines.append("")
        lines.append("This could be legitimate early buyers or coordinated snipers. Check if these")
        lines.append("wallets are linked using BubbleMaps or similar tools before investing heavily.")
    elif score >= 15:
        lines.append("ℹ️ **MINOR FLAGS** - Some early buying activity but within normal range.")
        lines.append("")
        lines.append("A few Block 0 buyers is common (bots, insiders). This alone isn't alarming,")
        lines.append("but combine with other checks (tokenscreen, walletscreen) for full picture.")
    else:
        lines.append("✅ **CLEAN LAUNCH** - No significant Block 0 manipulation detected.")
        lines.append("")
        lines.append("This token appears to have had a fair launch without coordinated sniping.")
        lines.append("Still verify other factors (contract safety, dev history) before investing.")

    lines.append("")

    # Current market data
    if token_info:
        lines.append("## Current Market")
        lines.append(f"- **Liquidity:** ${token_info.get('liquidity', 0):,.0f}")
        lines.append(f"- **Market Cap:** ${token_info.get('marketCap', 0):,.0f}")
        lines.append("")

    # Links
    lines.append("## Links")
    lines.append(f"- [DexScreener](https://dexscreener.com/solana/{mint})")
    lines.append(f"- [Solscan](https://solscan.io/token/{mint})")
    lines.append(f"- [RugCheck](https://rugcheck.xyz/tokens/{mint})")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC · Data from Helius*")
    lines.append("")
    lines.append("⚠️ **Bundle detection is probabilistic.** Same-block buying could be bots, insiders, or")
    lines.append("coordinated scammers - this tool can't distinguish. Use alongside other checks. DYOR!")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 bundlecheck.py <contract_address>")
        print("Example: python3 bundlecheck.py 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
        sys.exit(1)

    mint = sys.argv[1].strip()

    # Validate address format
    if len(mint) < 32 or len(mint) > 44:
        print(f"Error: Invalid Solana address format: {mint}")
        sys.exit(1)

    # Check for Helius API key
    require_helius_api_key()

    print(f"Analyzing launch: {mint}...", file=sys.stderr)

    # Get token info
    print("  Fetching token info...", file=sys.stderr)
    token_info = get_token_info(mint)

    # Get transaction history for the token
    print("  Fetching transaction history...", file=sys.stderr)
    transactions = get_helius_transactions(mint, limit=100)

    if not transactions:
        print("Error: Could not fetch transaction history. Token may be too new or invalid.")
        sys.exit(1)

    print(f"  Found {len(transactions)} transactions", file=sys.stderr)

    # Analyze launch
    print("  Analyzing Block 0 activity...", file=sys.stderr)
    analysis = analyze_launch_transactions(transactions, mint)

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        sys.exit(1)

    print(f"  Found {analysis.get('block0_count', 0)} Block 0 buyers", file=sys.stderr)

    # Calculate risk score
    score, reasons = calculate_risk_score(analysis)

    # Format and print report
    report = format_report(mint, token_info, analysis, score, reasons)
    print(report)


if __name__ == "__main__":
    main()
