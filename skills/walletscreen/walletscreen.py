#!/usr/bin/env python3
"""
WalletScreen - Solana Wallet History Analyzer
Part of ClaudeScreener

Usage:
  python3 walletscreen.py <wallet_address>
"""

import sys
import json
import os
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Known BAGS platform deployer wallets (these are infrastructure, not real creators)
BAGS_PLATFORM_WALLETS = [
    "BAGSB9TpGrZxQbEsrEznv5jXXdwyP6AXerN8aVRiAmcv",
]


def fetch_json(url: str, timeout: int = 15) -> dict | None:
    """Fetch JSON from URL with error handling."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WalletScreen/1.0"})
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


def get_helius_api_key() -> str | None:
    """Load Helius API key."""
    return load_env_var("HELIUS_API_KEY")


def require_helius_api_key() -> str:
    """Check for Helius API key and exit with helpful message if missing."""
    value = get_helius_api_key()
    if not value:
        print("ERROR: HELIUS_API_KEY not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("WalletScreen requires a Helius API key to fetch transaction history.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Setup:", file=sys.stderr)
        print("  1. Get a free API key at: https://helius.dev", file=sys.stderr)
        print("  2. Set it: export HELIUS_API_KEY=your_key_here", file=sys.stderr)
        print("     Or add to .env file: HELIUS_API_KEY=your_key_here", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run /claudescreener:setup for guided setup help.", file=sys.stderr)
        sys.exit(1)
    return value


def get_rugcheck_summary(mint: str) -> dict | None:
    """Fetch lightweight RugCheck summary for a token."""
    url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
    data = fetch_json(url)
    # If summary fails, try full report
    if not data:
        full_url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        full = fetch_json(full_url)
        if full:
            return {
                "score": full.get("score", 100),
                "rugged": full.get("rugged", False),
                "tokenMeta": full.get("tokenMeta", {}),
            }
    return data


def get_dexscreener_data(mint: str) -> dict | None:
    """Fetch DexScreener data for price/liquidity."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    data = fetch_json(url)
    if data and data.get("pairs"):
        return data["pairs"][0]
    return None


def get_helius_transactions(wallet: str, limit: int = 100) -> list | None:
    """Fetch transaction history from Helius."""
    api_key = get_helius_api_key()
    if not api_key:
        return None

    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}&limit={limit}"
    return fetch_json(url, timeout=30)


def is_valid_solana_address(address: str) -> bool:
    """Basic validation for Solana address format."""
    return len(address) >= 32 and len(address) <= 44


def get_wallet_age_days(transactions: list) -> float:
    """Calculate wallet age from oldest transaction."""
    if not transactions:
        return 0

    oldest_timestamp = min(tx.get("timestamp", 0) for tx in transactions)
    if oldest_timestamp == 0:
        return 0

    oldest_date = datetime.fromtimestamp(oldest_timestamp, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    age = now - oldest_date
    return age.days + age.seconds / 86400


def find_token_creations(transactions: list, wallet: str) -> list[dict]:
    """
    Find all token creation events in transaction history.

    Looks for:
    - TOKEN_MINT type where wallet is involved
    - InitializeMint instructions

    Excludes:
    - CREATE_MERKLE_TREE (compressed NFTs, not tradable tokens)
    """
    created_tokens = []
    seen_mints = set()

    for tx in transactions:
        tx_type = tx.get("type", "")

        # Skip Merkle Trees (cNFTs, spam)
        if "MERKLE" in tx_type.upper():
            continue

        # Check for token creation events
        if tx_type in ("TOKEN_MINT", "CREATE", "COMPRESSED_NFT_MINT"):
            # Skip compressed NFTs
            if tx_type == "COMPRESSED_NFT_MINT":
                continue

            # Extract mint address from token transfers or instructions
            mint = extract_mint_from_tx(tx)
            if mint and mint not in seen_mints:
                seen_mints.add(mint)
                created_tokens.append({
                    "mint": mint,
                    "timestamp": tx.get("timestamp", 0),
                    "signature": tx.get("signature", ""),
                    "type": tx_type,
                })

        # Also check instructions for InitializeMint
        for instr in tx.get("instructions", []):
            if "InitializeMint" in str(instr.get("data", "")):
                # Try to extract mint from accounts
                accounts = instr.get("accounts", [])
                if accounts:
                    mint = accounts[0]  # First account is usually the mint
                    if mint not in seen_mints and is_valid_solana_address(mint):
                        seen_mints.add(mint)
                        created_tokens.append({
                            "mint": mint,
                            "timestamp": tx.get("timestamp", 0),
                            "signature": tx.get("signature", ""),
                            "type": "InitializeMint",
                        })

    # Sort by timestamp (oldest first)
    created_tokens.sort(key=lambda x: x["timestamp"])
    return created_tokens


def extract_mint_from_tx(tx: dict) -> str | None:
    """Extract mint address from a transaction."""
    # Check token transfers
    for transfer in tx.get("tokenTransfers", []):
        mint = transfer.get("mint")
        if mint and is_valid_solana_address(mint):
            return mint

    # Check account data for token changes
    for account in tx.get("accountData", []):
        for change in account.get("tokenBalanceChanges", []):
            mint = change.get("mint")
            if mint and is_valid_solana_address(mint):
                return mint

    return None


def classify_token_outcome(mint: str) -> dict:
    """
    Classify a token's current status.

    Returns:
    - status: 'RUGGED', 'DEAD', 'HIGH_RISK', 'CAUTION', 'ACTIVE', 'UNKNOWN'
    - liquidity: current liquidity in USD
    - symbol: token symbol
    - name: token name
    """
    result = {
        "status": "UNKNOWN",
        "emoji": "❓",
        "liquidity": None,
        "symbol": "???",
        "name": "Unknown",
        "market_cap": None,
    }

    # Get RugCheck data
    rugcheck = get_rugcheck_summary(mint)
    if rugcheck:
        result["symbol"] = rugcheck.get("tokenMeta", {}).get("symbol", "???")
        result["name"] = rugcheck.get("tokenMeta", {}).get("name", "Unknown")

        if rugcheck.get("rugged"):
            result["status"] = "RUGGED"
            result["emoji"] = "💀"
            return result

    # Get DexScreener data for liquidity
    dex = get_dexscreener_data(mint)
    if dex:
        result["liquidity"] = dex.get("liquidity", {}).get("usd", 0)
        result["market_cap"] = dex.get("marketCap", 0)
        result["symbol"] = dex.get("baseToken", {}).get("symbol", result["symbol"])
        result["name"] = dex.get("baseToken", {}).get("name", result["name"])

        liq = result["liquidity"] or 0

        if liq < 1000:
            result["status"] = "DEAD"
            result["emoji"] = "💀"
        elif liq < 5000:
            result["status"] = "LOW_LIQ"
            result["emoji"] = "⚠️"
        else:
            result["status"] = "ACTIVE"
            result["emoji"] = "🟢"
    elif rugcheck:
        # No DexScreener data, use RugCheck score
        score = rugcheck.get("score", 100)
        if score > 70:
            result["status"] = "HIGH_RISK"
            result["emoji"] = "🔴"
        elif score > 40:
            result["status"] = "CAUTION"
            result["emoji"] = "⚠️"
        else:
            result["status"] = "ACTIVE"
            result["emoji"] = "🟢"

    return result


def calculate_dev_risk_score(
    wallet_age_days: float,
    total_launches: int,
    rug_count: int,
    dead_count: int,
    launches_per_week: float,
) -> tuple[int, list[str]]:
    """
    Calculate developer risk score (0-100, higher = more risky).

    Returns (score, list of reasons).

    Key principles from council review:
    - Fresh wallet (< 3 days) = EXTREME RISK (95)
    - First-ever launch = HIGH RISK (80)
    - 100% rug rate should = near-100 score
    - Single confirmed rug = minimum 40 points
    """
    score = 0
    reasons = []

    # FRESH WALLET CHECK (auto-high risk)
    if wallet_age_days < 3:
        score = 95
        reasons.append(f"+95: BURNER WALLET (age: {wallet_age_days:.1f} days)")
        return score, reasons
    elif wallet_age_days < 7:
        score += 30
        reasons.append(f"+30: Very new wallet ({wallet_age_days:.1f} days old)")
    elif wallet_age_days < 30:
        score += 10
        reasons.append(f"+10: Newer wallet ({wallet_age_days:.0f} days old)")

    # FIRST LAUNCH CHECK
    if total_launches == 0:
        score = max(score, 80)
        reasons.append("+80: First-ever token launch (no track record)")
        return min(100, score), reasons

    # RUG RATE (0-70 points)
    bad_count = rug_count + dead_count
    bad_rate = bad_count / total_launches if total_launches > 0 else 0
    rug_rate = rug_count / total_launches if total_launches > 0 else 0

    rug_points = int(rug_rate * 70)
    if rug_points > 0:
        score += rug_points
        reasons.append(f"+{rug_points}: {rug_rate*100:.0f}% confirmed rug rate")

    # Minimum for ANY confirmed rug
    if rug_count > 0 and score < 40:
        score = 40
        reasons.append("+40 (min): Has confirmed rug(s)")

    # DEAD TOKEN PENALTY (less severe than rugs)
    if dead_count > 0 and rug_count == 0:
        dead_points = min(30, dead_count * 10)
        score += dead_points
        reasons.append(f"+{dead_points}: {dead_count} dead token(s)")

    # SERIAL LAUNCHER PENALTY
    if launches_per_week > 2:
        serial_points = min(20, int(launches_per_week * 5))
        score += serial_points
        reasons.append(f"+{serial_points}: Serial launcher ({launches_per_week:.1f} tokens/week)")
    elif launches_per_week > 1:
        score += 10
        reasons.append(f"+10: Frequent launcher ({launches_per_week:.1f} tokens/week)")

    # VOLUME PENALTY (many launches)
    if total_launches > 10:
        score += 15
        reasons.append(f"+15: Industrial scale ({total_launches} tokens)")
    elif total_launches > 5:
        score += 10
        reasons.append(f"+10: High volume ({total_launches} tokens)")

    # POSITIVE: Good track record
    if total_launches >= 3 and bad_count == 0:
        score -= 15
        reasons.append("-15: Clean track record (3+ tokens, no rugs)")

    return max(0, min(100, score)), reasons


def get_risk_label(score: int) -> str:
    """Convert numeric score to risk label."""
    if score <= 25:
        return "🟢 LOW RISK"
    elif score <= 50:
        return "🟡 CAUTION"
    elif score <= 75:
        return "🟠 HIGH RISK"
    else:
        return "🔴 EXTREME RISK"


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp to readable date."""
    if not ts:
        return "Unknown"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def format_number(n: float | int | None) -> str:
    """Format large numbers with K/M/B suffixes."""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:.0f}"


def format_report(
    wallet: str,
    wallet_age_days: float,
    token_outcomes: list[dict],
    risk_score: int,
    score_reasons: list[str],
    tx_count: int = 0,
) -> str:
    """Format the wallet analysis report."""
    lines = []

    # Header
    short_wallet = f"{wallet[:8]}...{wallet[-8:]}"
    lines.append(f"# Wallet Analysis")
    lines.append(f"**Wallet:** `{short_wallet}`")
    lines.append(f"**Wallet Age:** {wallet_age_days:.1f} days")
    lines.append("")

    # Risk Assessment
    risk_label = get_risk_label(risk_score)
    lines.append(f"## Risk Assessment: {risk_label} (Score: {risk_score}/100)")
    lines.append("")

    # Score breakdown
    if score_reasons:
        lines.append("<details>")
        lines.append("<summary><b>Score Breakdown</b></summary>")
        lines.append("")
        for reason in score_reasons:
            lines.append(f"- {reason}")
        lines.append("</details>")
        lines.append("")

    # Statistics
    total = len(token_outcomes)
    rugged = sum(1 for t in token_outcomes if t["outcome"]["status"] == "RUGGED")
    dead = sum(1 for t in token_outcomes if t["outcome"]["status"] == "DEAD")
    active = sum(1 for t in token_outcomes if t["outcome"]["status"] == "ACTIVE")

    lines.append("## Statistics")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Tokens Launched | {total} |")
    if total > 0:
        lines.append(f"| 🟢 Active | {active} ({active/total*100:.0f}%) |")
        lines.append(f"| 💀 Dead/Rugged | {rugged + dead} ({(rugged+dead)/total*100:.0f}%) |")
        if rugged > 0:
            lines.append(f"| Confirmed Rugs | {rugged} |")
    lines.append("")

    # Launch History
    if token_outcomes:
        lines.append("## Launch History")
        lines.append("")
        lines.append("| Token | Launched | Liquidity | Status |")
        lines.append("|-------|----------|-----------|--------|")

        # Show most recent first, limit to 15
        for item in reversed(token_outcomes[-15:]):
            token = item["token"]
            outcome = item["outcome"]

            symbol = outcome.get("symbol", "???")
            date = format_timestamp(token.get("timestamp", 0))
            liq = format_number(outcome.get("liquidity"))
            status = f"{outcome['emoji']} {outcome['status']}"

            lines.append(f"| ${symbol} | {date} | {liq} | {status} |")

        if len(token_outcomes) > 15:
            lines.append(f"| ... | *{len(token_outcomes) - 15} more* | | |")
        lines.append("")
    else:
        lines.append("## Launch History")
        lines.append("*No token launches found in transaction history*")
        lines.append("")

    # Red Flags Summary
    lines.append("## Summary")

    flags = []
    if wallet_age_days < 3:
        flags.append("🚨 BURNER WALLET - Created less than 3 days ago")
    elif wallet_age_days < 7:
        flags.append("⚠️ Very new wallet (< 1 week old)")

    if total == 0:
        flags.append("⚠️ First-ever token launch - no track record")

    if rugged > 0:
        flags.append(f"🚨 {rugged} CONFIRMED RUG(S) in history")

    if dead > 0 and rugged == 0:
        flags.append(f"⚠️ {dead} dead token(s) - failed or abandoned")

    if total > 5:
        flags.append(f"⚠️ Serial launcher ({total} tokens)")

    if total > 0 and active == total:
        flags.append("✅ All tokens still active")

    if total >= 3 and rugged == 0 and dead == 0:
        flags.append("✅ Clean track record")

    if flags:
        for flag in flags:
            lines.append(f"- {flag}")
    else:
        lines.append("- No major flags detected")

    lines.append("")

    # Recommendation
    lines.append("## Recommendation")
    if risk_score >= 80:
        lines.append("**AVOID** - This developer shows extreme risk signals.")
    elif risk_score >= 60:
        lines.append("**HIGH CAUTION** - Significant concerns with this developer.")
    elif risk_score >= 40:
        lines.append("**PROCEED WITH CAUTION** - Some yellow flags present.")
    elif risk_score >= 20:
        lines.append("**MODERATE CONFIDENCE** - Limited concerns, but always DYOR.")
    else:
        lines.append("**REASONABLE CONFIDENCE** - Good track record, but always DYOR.")
    lines.append("")

    # Footer
    lines.append("---")
    footer_note = f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC · Data from Helius + RugCheck + DexScreener*"
    if tx_count >= 100:
        footer_note += f" · *Note: Only analyzed last {tx_count} transactions*"
    lines.append(footer_note)
    lines.append("")
    lines.append("⚠️ **Wallet history is just one factor.** Even clean wallets can rug, and new wallets can be legitimate. This is not financial advice - DYOR!")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 walletscreen.py <wallet_address>")
        print("Example: python3 walletscreen.py Dzp1SrZ474xwGp6ZEP6cNKo39u9zeXe1YAuTkyZyv3t4")
        sys.exit(1)

    wallet = sys.argv[1].strip()

    # Validate address format
    if not is_valid_solana_address(wallet):
        print(f"Error: Invalid Solana address format: {wallet}")
        sys.exit(1)

    # Check if this is a known BAGS platform wallet
    if wallet in BAGS_PLATFORM_WALLETS:
        print("# BAGS Platform Deployer Wallet")
        print("")
        print(f"**Wallet:** `{wallet[:8]}...{wallet[-8:]}`")
        print("")
        print("## Analysis Not Available")
        print("")
        print("This wallet is the **BAGS platform deployer** - it's infrastructure that deploys")
        print("tokens on behalf of creators, not a real person's wallet.")
        print("")
        print("Analyzing this wallet won't give you useful information about any specific token creator.")
        print("")
        print("**Instead, use `/tokenscreen <token_address>`** to analyze a specific BAGS token.")
        print("TokenScreen will automatically identify the real creator and royalty recipients.")
        print("")
        print("---")
        print("*BAGS tokens are created through bags.fm - the platform handles deployment*")
        sys.exit(0)

    # Check for Helius API key
    require_helius_api_key()

    print(f"Analyzing wallet: {wallet}...", file=sys.stderr)

    # 2. Fetch transaction history
    transactions = get_helius_transactions(wallet, limit=100)
    if not transactions:
        print("Error: Could not fetch transaction history")
        sys.exit(1)

    print(f"  Found {len(transactions)} transactions", file=sys.stderr)

    # 3. Calculate wallet age
    wallet_age_days = get_wallet_age_days(transactions)
    print(f"  Wallet age: {wallet_age_days:.1f} days", file=sys.stderr)

    # 4. Find token creations
    created_tokens = find_token_creations(transactions, wallet)
    print(f"  Found {len(created_tokens)} token launches", file=sys.stderr)

    # 5. Check outcome of each token
    token_outcomes = []
    for i, token in enumerate(created_tokens):
        print(f"  Checking token {i+1}/{len(created_tokens)}: {token['mint'][:8]}...", file=sys.stderr)
        outcome = classify_token_outcome(token["mint"])
        token_outcomes.append({
            "token": token,
            "outcome": outcome,
        })

    # 6. Calculate launch frequency
    if len(created_tokens) >= 2:
        first_ts = created_tokens[0]["timestamp"]
        last_ts = created_tokens[-1]["timestamp"]
        weeks = max(1, (last_ts - first_ts) / (7 * 24 * 60 * 60))
        launches_per_week = len(created_tokens) / weeks
    else:
        launches_per_week = 0

    # 7. Count outcomes
    rug_count = sum(1 for t in token_outcomes if t["outcome"]["status"] == "RUGGED")
    dead_count = sum(1 for t in token_outcomes if t["outcome"]["status"] == "DEAD")

    # 8. Calculate risk score
    risk_score, score_reasons = calculate_dev_risk_score(
        wallet_age_days=wallet_age_days,
        total_launches=len(created_tokens),
        rug_count=rug_count,
        dead_count=dead_count,
        launches_per_week=launches_per_week,
    )

    # 9. Format and print report
    report = format_report(
        wallet=wallet,
        wallet_age_days=wallet_age_days,
        token_outcomes=token_outcomes,
        risk_score=risk_score,
        score_reasons=score_reasons,
        tx_count=len(transactions),
    )
    print(report)


if __name__ == "__main__":
    main()
