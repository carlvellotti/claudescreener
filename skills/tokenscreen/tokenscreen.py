#!/usr/bin/env python3
"""
TokenScreen - Solana Token Safety Checker
Part of ClaudeScreener

Usage:
  python3 tokenscreen.py <contract_address>
  python3 tokenscreen.py <contract_address> --royalty <wallet_address> [<twitter_handle>]
"""

import sys
import json
import os
import urllib.request
import urllib.error
from datetime import datetime

def load_env_var(var_name: str) -> str | None:
    """
    Load environment variable, checking multiple sources:
    1. Environment variables (already set)
    2. .env file in current directory
    3. .env file in script directory
    """
    # Check environment first
    value = os.environ.get(var_name)
    if value:
        return value

    # Check .env in current directory
    env_paths = [
        ".env",
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    ]

    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{var_name}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def require_api_key(var_name: str, service_name: str, signup_url: str) -> str:
    """Check for required API key and exit with helpful message if missing."""
    value = load_env_var(var_name)
    if not value:
        print(f"ERROR: {var_name} not found", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"To use ClaudeScreener, you need a {service_name} API key.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Setup:", file=sys.stderr)
        print(f"  1. Get a free API key at: {signup_url}", file=sys.stderr)
        print(f"  2. Set it: export {var_name}=your_key_here", file=sys.stderr)
        print(f"     Or add to .env file: {var_name}=your_key_here", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run /claudescreener:setup for guided setup help.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_json(url: str, headers: dict = None, timeout: int = 10) -> dict | None:
    """Fetch JSON from URL with error handling."""
    try:
        req_headers = {"User-Agent": "TokenScreen/1.0"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def get_rugcheck_report(mint: str) -> dict | None:
    """Fetch full RugCheck report for a token."""
    url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
    return fetch_json(url)


# Known DEX/AMM patterns for LP pool detection
DEX_PATTERNS = [
    "pool", "amm", "liquidity", "vault", "reserve",
    "raydium", "orca", "meteora", "whirlpool",
    "lifinity", "phoenix", "openbook", "serum",
    "invariant", "saber", "aldrin", "crema",
    "cpmm", "clmm", "damm",  # Pool type abbreviations
]

# Known burn addresses to exclude from holder analysis
BURN_ADDRESSES = [
    "1111111111111111111111111111111111",
    "1nc1nerator11111111111111111111111111111111",
]


def is_lp_or_dex_account(account_type: str, account_name: str, address: str = "") -> bool:
    """
    Check if an account is a known LP pool or DEX account.

    Args:
        account_type: Type from RugCheck knownAccounts (e.g., "AMM", "LP")
        account_name: Name from RugCheck knownAccounts
        address: Wallet address to check against burn addresses

    Returns:
        True if this is an LP/DEX account that should be excluded from holder concentration
    """
    # Check account type
    if account_type in ("AMM", "LP", "POOL", "DEX"):
        return True

    # Check burn addresses
    if address in BURN_ADDRESSES:
        return True

    # Check name against DEX patterns
    name_lower = account_name.lower()
    for pattern in DEX_PATTERNS:
        if pattern in name_lower:
            return True

    return False


def get_bags_creators(token_mint: str) -> list | None:
    """
    Fetch creator/royalty info from BAGS API.
    Returns list of creators with isCreator, wallet, royaltyBps, twitterUsername.
    Returns None if token is not a BAGS token or API unavailable.
    """
    api_key = load_env_var("BAGS_API_KEY")
    if not api_key:
        return None

    url = f"https://public-api-v2.bags.fm/api/v1/token-launch/creator/v3?tokenMint={token_mint}"
    headers = {"x-api-key": api_key}
    data = fetch_json(url, headers=headers, timeout=15)

    if data and data.get("success") and data.get("response"):
        return data["response"]
    return None


def get_helius_transactions(wallet: str, limit: int = 100) -> list | None:
    """Fetch transaction history from Helius."""
    api_key = load_env_var("HELIUS_API_KEY")
    if not api_key:
        return None

    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}&limit={limit}"
    return fetch_json(url, timeout=30)


def get_helius_balances(wallet: str) -> dict | None:
    """Fetch token balances from Helius."""
    api_key = load_env_var("HELIUS_API_KEY")
    if not api_key:
        return None

    url = f"https://api.helius.xyz/v0/addresses/{wallet}/balances?api-key={api_key}"
    return fetch_json(url, timeout=30)


def classify_token_outcome(mint: str) -> dict:
    """
    Classify a token's current status using DexScreener and RugCheck.

    Returns dict with: status, emoji, liquidity, symbol
    """
    result = {
        "status": "UNKNOWN",
        "emoji": "❓",
        "liquidity": None,
        "symbol": "???",
    }

    # Get RugCheck data first (for rugged status)
    rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
    rugcheck = fetch_json(rugcheck_url)

    if rugcheck:
        result["symbol"] = rugcheck.get("tokenMeta", {}).get("symbol", "???")
        if rugcheck.get("rugged"):
            result["status"] = "RUGGED"
            result["emoji"] = "💀"
            return result

    # Get DexScreener data for liquidity
    dex = get_dexscreener_data(mint)
    if dex:
        result["liquidity"] = dex.get("liquidity", {}).get("usd", 0)
        result["symbol"] = dex.get("baseToken", {}).get("symbol", result["symbol"])

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
        # No DexScreener, use RugCheck score
        score = rugcheck.get("score", 100)
        if score > 70:
            result["status"] = "HIGH_RISK"
            result["emoji"] = "🔴"
        else:
            result["status"] = "UNKNOWN"
            result["emoji"] = "❓"

    return result


def is_valid_solana_address(address: str) -> bool:
    """Basic validation for Solana address format."""
    return len(address) >= 32 and len(address) <= 44


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


def analyze_royalty_recipient(wallet: str, token_mint: str, twitter_handle: str = None) -> str:
    """
    Analyze a royalty recipient's wallet for trust signals.

    Checks:
    - Fee claims (transfers from vaults)
    - Token burns (buyback & burn = bullish)
    - Current holdings of the token
    - Token launches (serial rugger check)
    """
    lines = []

    display_name = f"@{twitter_handle}" if twitter_handle else f"`{wallet[:8]}...{wallet[-4:]}`"
    lines.append(f"## Royalty Recipient Analysis: {display_name}")
    lines.append("")

    # Get transaction history (Helius max limit is 100)
    txs = get_helius_transactions(wallet, limit=100)
    if not txs:
        lines.append("*Could not fetch transaction history*")
        lines.append("")
        lines.append("**Setup required:** Get a free Helius API key at https://helius.dev")
        lines.append("Then: `export HELIUS_API_KEY=your_key` or add to .env file")
        return "\n".join(lines)

    # Analyze transactions
    token_burns = []
    token_swaps = []
    incoming_sol = []
    created_mints = []  # Store actual mint addresses
    seen_mints = set()

    for tx in txs:
        tx_type = tx.get("type", "UNKNOWN")
        desc = tx.get("description", "")
        tx_str = json.dumps(tx)

        # Check for burns of the specific token
        if tx_type == "BURN" and token_mint in tx_str:
            # Extract burn amount from description
            token_burns.append(desc)

        # Check for swaps involving this token
        if tx_type == "SWAP" and token_mint in tx_str:
            token_swaps.append(desc)

        # Check for incoming SOL (potential fee claims)
        if tx_type == "TRANSFER" and f"SOL to {wallet[:8]}" in desc:
            # Extract amount
            import re
            match = re.search(r'transferred ([\d.]+) SOL', desc)
            if match:
                incoming_sol.append(float(match.group(1)))

        # Check for token creation events - capture the mint address
        if tx_type in ("TOKEN_MINT", "CREATE") or "InitializeMint" in tx_str:
            mint = extract_mint_from_tx(tx)
            if mint and mint not in seen_mints and mint != token_mint:
                seen_mints.add(mint)
                created_mints.append(mint)

    # Get current holdings
    balances = get_helius_balances(wallet)
    token_balance = 0
    sol_balance = 0

    if balances:
        sol_balance = balances.get("nativeBalance", 0) / 1e9
        for token in balances.get("tokens", []):
            if token.get("mint") == token_mint:
                decimals = token.get("decimals", 9)
                token_balance = token.get("amount", 0) / (10 ** decimals)

    # Calculate totals
    total_burned = 0
    for burn_desc in token_burns:
        import re
        match = re.search(r'burned ([\d,]+(?:\.\d+)?)', burn_desc)
        if match:
            total_burned += float(match.group(1).replace(",", ""))

    total_sol_received = sum(incoming_sol)

    # Build assessment
    signals = []
    red_flags = []

    # Fee claims
    if total_sol_received > 0:
        signals.append(f"✅ Claimed ~{total_sol_received:.2f} SOL in fees")
    else:
        signals.append("ℹ️ No fee claims detected yet")

    # Token burns
    if total_burned > 0:
        signals.append(f"✅ Burned {total_burned:,.0f} tokens (buyback & burn)")

    # Current holdings
    if token_balance > 0:
        signals.append(f"✅ Holding {token_balance:,.0f} tokens (skin in the game)")
    else:
        red_flags.append("⚠️ Not holding any tokens")

    # Token launches - check outcomes
    launch_outcomes = {"active": 0, "dead": 0, "rugged": 0, "unknown": 0}
    if created_mints:
        for mint in created_mints[:10]:  # Limit to 10 to avoid slow API calls
            outcome = classify_token_outcome(mint)
            status = outcome["status"]
            if status == "ACTIVE":
                launch_outcomes["active"] += 1
            elif status in ("DEAD", "LOW_LIQ"):
                launch_outcomes["dead"] += 1
            elif status == "RUGGED":
                launch_outcomes["rugged"] += 1
            else:
                launch_outcomes["unknown"] += 1

    total_launches = len(created_mints)
    bad_launches = launch_outcomes["dead"] + launch_outcomes["rugged"]

    if total_launches > 0:
        outcome_str = f"{launch_outcomes['active']} active, {launch_outcomes['dead']} dead"
        if launch_outcomes["rugged"] > 0:
            outcome_str += f", {launch_outcomes['rugged']} rugged"
        if total_launches > 10:
            outcome_str += f" (checked 10 of {total_launches})"

        if launch_outcomes["rugged"] > 0:
            red_flags.append(f"🚨 Has {launch_outcomes['rugged']} CONFIRMED RUG(S) in history")
        if bad_launches > 0 and bad_launches == total_launches:
            red_flags.append(f"⚠️ ALL {total_launches} other tokens are dead/rugged")
        elif bad_launches > total_launches * 0.5:
            red_flags.append(f"⚠️ {bad_launches}/{total_launches} other tokens failed ({outcome_str})")
        elif total_launches > 5:
            red_flags.append(f"⚠️ Serial launcher: {total_launches} tokens ({outcome_str})")
        else:
            signals.append(f"ℹ️ {total_launches} other tokens ({outcome_str})")
    else:
        signals.append("✅ No other token launches detected")

    # Output table
    launch_signal = "✅ Clean"
    if total_launches > 0:
        if launch_outcomes["rugged"] > 0:
            launch_signal = "🚨 Has rugs"
        elif bad_launches > total_launches * 0.5:
            launch_signal = "⚠️ Mostly failed"
        elif total_launches > 5:
            launch_signal = "⚠️ Serial launcher"
        else:
            launch_signal = "ℹ️ Check history"

    lines.append("| Metric | Value | Signal |")
    lines.append("|--------|-------|--------|")
    lines.append(f"| Fee Claims | {total_sol_received:.2f} SOL | {'✅ Active' if total_sol_received > 0 else 'ℹ️ None yet'} |")
    lines.append(f"| Tokens Burned | {total_burned:,.0f} | {'✅ Buyback & burn' if total_burned > 0 else '—'} |")
    lines.append(f"| Current Holdings | {token_balance:,.0f} | {'✅ Aligned' if token_balance > 0 else '⚠️ None'} |")
    lines.append(f"| Other Launches | {total_launches} | {launch_signal} |")
    lines.append("")

    # Narrative assessment
    if red_flags:
        lines.append("**Concerns:**")
        for flag in red_flags:
            lines.append(f"- {flag}")
        lines.append("")

    if signals:
        lines.append("**Positive Signals:**")
        for sig in signals:
            lines.append(f"- {sig}")
        lines.append("")

    # Overall assessment
    trust_score = len(signals) - len(red_flags) * 2
    if trust_score >= 3:
        lines.append("**Assessment:** This royalty recipient shows positive alignment with the project (claiming fees, burning tokens, holding).")
    elif trust_score >= 0:
        lines.append("**Assessment:** Mixed signals - do additional research on this recipient.")
    else:
        lines.append("**Assessment:** ⚠️ Concerning pattern - proceed with caution.")

    return "\n".join(lines)


def get_dexscreener_data(mint: str) -> dict | None:
    """Fetch DexScreener data for price/volume/liquidity."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    data = fetch_json(url)
    if data and data.get("pairs"):
        # Return the most liquid pair (first one is usually highest)
        return data["pairs"][0]
    return None


def format_bags_creators(creators: list, token_mint: str) -> str:
    """Format BAGS creator/royalty info section."""
    lines = []
    lines.append("## BAGS Token: Creators & Royalty Recipients")
    lines.append("")

    if not creators:
        lines.append("*No BAGS creator data found*")
        return "\n".join(lines)

    # Separate creator from royalty-only recipients
    actual_creator = None
    royalty_recipients = []

    for c in creators:
        if c.get("isCreator"):
            actual_creator = c
        else:
            royalty_recipients.append(c)

    lines.append("| Role | Identity | Royalty Share | Wallet |")
    lines.append("|------|----------|---------------|--------|")

    # Show creator first
    if actual_creator:
        twitter = actual_creator.get("twitterUsername")
        wallet = actual_creator.get("wallet", "")
        bps = actual_creator.get("royaltyBps", 0)
        pct = bps / 100 if bps else 0

        identity = f"[@{twitter}](https://x.com/{twitter})" if twitter else f"`{wallet[:6]}...{wallet[-4:]}`"
        short_wallet = f"`{wallet[:6]}...{wallet[-4:]}`" if wallet else "N/A"
        lines.append(f"| 🎨 **Creator** | {identity} | {pct:.1f}% | {short_wallet} |")

    # Show other royalty recipients
    for r in royalty_recipients:
        twitter = r.get("twitterUsername")
        wallet = r.get("wallet", "")
        bps = r.get("royaltyBps", 0)
        pct = bps / 100 if bps else 0

        identity = f"[@{twitter}](https://x.com/{twitter})" if twitter else f"`{wallet[:6]}...{wallet[-4:]}`"
        short_wallet = f"`{wallet[:6]}...{wallet[-4:]}`" if wallet else "N/A"
        lines.append(f"| 💰 Royalty | {identity} | {pct:.1f}% | {short_wallet} |")

    lines.append("")

    # Add context about BAGS tokens
    lines.append("*Note: For BAGS tokens, the on-chain creator is the BAGS platform wallet. The real creator and royalty recipients are shown above.*")
    lines.append("")

    return "\n".join(lines)


def format_number(n: float | int | None) -> str:
    """Format large numbers with K/M/B suffixes."""
    if n is None:
        return "N/A"
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.2f}K"
    return f"${n:.2f}"


def format_percent(n: float | None) -> str:
    """Format percentage."""
    if n is None:
        return "N/A"
    return f"{n:.1f}%"


def get_risk_label(score: int) -> str:
    """Convert numeric score to risk label with emoji."""
    if score <= 25:
        return "🟢 LOW RISK"
    elif score <= 50:
        return "🟡 CAUTION"
    elif score <= 75:
        return "🟠 HIGH RISK"
    else:
        return "🔴 CRITICAL RISK"


def generate_narrative(rugcheck: dict, dex: dict | None, score: int, reasons: list[str]) -> str:
    """Generate a plain English narrative analysis of the token."""
    parts = []

    token_meta = rugcheck.get("tokenMeta", {})
    name = token_meta.get("name", "This token")
    symbol = token_meta.get("symbol", "")

    # Opening assessment
    if score <= 25:
        parts.append(f"**{name} looks relatively safe** based on the on-chain data.")
    elif score <= 50:
        parts.append(f"**{name} has some yellow flags** worth noting before you ape in.")
    elif score <= 75:
        parts.append(f"**{name} shows concerning signals** - proceed with caution.")
    else:
        parts.append(f"**{name} has serious red flags** - high probability of being a scam or rug.")

    # Authority analysis
    mint_auth = rugcheck.get("mintAuthority")
    freeze_auth = rugcheck.get("freezeAuthority")

    if not mint_auth and not freeze_auth:
        parts.append("The dev has renounced both mint and freeze authorities, meaning they can't create more tokens or freeze your wallet.")
    elif mint_auth and freeze_auth:
        parts.append("⚠️ The dev still controls both mint and freeze authorities - they could print more tokens or freeze holders at any time.")
    elif mint_auth:
        parts.append("⚠️ Mint authority is still active - the dev can create more tokens, diluting your holdings.")
    elif freeze_auth:
        parts.append("⚠️ Freeze authority is still active - the dev could freeze your tokens.")

    # Liquidity analysis
    markets = rugcheck.get("markets", [])
    max_lp_locked = 0
    for market in markets:
        lp_info = market.get("lp", {})
        locked_pct = lp_info.get("lpLockedPct", 0) or 0
        max_lp_locked = max(max_lp_locked, locked_pct)

    liq_usd = None
    if dex:
        liq_usd = dex.get("liquidity", {}).get("usd")
    if liq_usd is None:
        liq_usd = rugcheck.get("totalMarketLiquidity", 0)

    if max_lp_locked >= 90:
        parts.append(f"Liquidity is {max_lp_locked:.0f}% locked, which means the dev can't pull the rug by removing liquidity.")
    elif max_lp_locked >= 50:
        parts.append(f"LP is partially locked ({max_lp_locked:.0f}%), but some liquidity could still be pulled.")
    elif liq_usd and liq_usd > 0:
        parts.append(f"No LP lock detected - liquidity (${liq_usd:,.0f}) could theoretically be pulled.")

    # Holder analysis
    holders = rugcheck.get("topHolders", [])
    known_accounts = rugcheck.get("knownAccounts", {})

    lp_holders = []
    real_holders = []
    for h in holders[:10]:
        addr = h.get("address", "")
        account_info = known_accounts.get(addr, {})
        is_lp = is_lp_or_dex_account(account_info.get("type", ""), account_info.get("name", ""), addr)
        if is_lp:
            lp_holders.append((h, account_info.get("name", "LP Pool")))
        else:
            real_holders.append(h)

    if lp_holders:
        lp_name = lp_holders[0][1]
        lp_pct = lp_holders[0][0].get("pct", 0)
        parts.append(f"The largest holder ({lp_pct:.1f}%) is a {lp_name} - that's the trading liquidity, not a whale.")

    if real_holders:
        top_real_pct = real_holders[0].get("pct", 0)
        real_total = sum(h.get("pct", 0) for h in real_holders[:5])
        if top_real_pct > 20:
            parts.append(f"One wallet holds {top_real_pct:.1f}% of supply - that's significant concentration risk.")
        elif real_total > 40:
            parts.append(f"Top 5 non-LP wallets hold {real_total:.1f}% combined - moderate concentration.")
        else:
            parts.append(f"Holder distribution looks healthy - top wallet is only {top_real_pct:.1f}%.")

    # Creator analysis
    creator_balance = rugcheck.get("creatorBalance", 0)
    if creator_balance == 0:
        parts.append("The creator wallet holds 0 tokens - they've either sold or distributed their allocation.")
    elif creator_balance > 0:
        total_supply = rugcheck.get("token", {}).get("supply", 1)
        if total_supply:
            creator_pct = (creator_balance / total_supply) * 100
            if creator_pct > 10:
                parts.append(f"⚠️ Creator still holds {creator_pct:.1f}% of supply.")

    # Volume/activity
    if dex:
        vol_24h = dex.get("volume", {}).get("h24", 0)
        mc = dex.get("marketCap", 0)
        if vol_24h and mc and mc > 0:
            vol_mc_ratio = vol_24h / mc
            if vol_mc_ratio > 0.5:
                parts.append(f"High trading activity (24h volume is {vol_mc_ratio*100:.0f}% of market cap).")
            elif vol_24h < 1000:
                parts.append(f"Very low trading volume (${vol_24h:,.0f}/24h) - may be hard to exit.")

    return " ".join(parts)


def calculate_custom_score(rugcheck: dict, dex: dict | None) -> tuple[int, list[str]]:
    """
    Calculate our own transparent risk score based on available data.
    Returns (score, list of reasons).

    Score 0-100: 0 = safest, 100 = most risky
    """
    score = 0
    reasons = []

    # === AUTHORITY CHECKS (most important) ===
    if rugcheck.get("mintAuthority"):
        score += 30
        reasons.append("+30: Mint authority active (can create more tokens)")

    if rugcheck.get("freezeAuthority"):
        score += 25
        reasons.append("+25: Freeze authority active (can freeze holders)")

    # === METADATA ===
    # Check risks array for mutable metadata
    risks = rugcheck.get("risks", [])
    for risk in risks:
        if "mutable" in risk.get("name", "").lower():
            score += 5  # Minor risk
            reasons.append("+5: Mutable metadata")
            break

    # === TOKEN-2022 EXTENSIONS ===
    extensions = rugcheck.get("token_extensions") or []
    for ext in extensions:
        ext_name = ext.get("extension") if isinstance(ext, dict) else str(ext)
        if ext_name == "transferHook":
            score += 25
            reasons.append("+25: TransferHook extension (can block/tax transfers)")
        elif ext_name == "permanentDelegate":
            score += 30
            reasons.append("+30: PermanentDelegate (can drain tokens)")
        elif ext_name == "transferFeeConfig":
            score += 10
            reasons.append("+10: TransferFee extension")

    # === LIQUIDITY ===
    liq_usd = None
    if dex:
        liq_usd = dex.get("liquidity", {}).get("usd")
    if liq_usd is None:
        liq_usd = rugcheck.get("totalMarketLiquidity", 0)

    if liq_usd is not None:
        if liq_usd < 1000:
            score += 20
            reasons.append(f"+20: Very low liquidity (${liq_usd:,.0f})")
        elif liq_usd < 10000:
            score += 10
            reasons.append(f"+10: Low liquidity (${liq_usd:,.0f})")

    # === HOLDER CONCENTRATION (excluding LP pools) ===
    holders = rugcheck.get("topHolders", [])
    known_accounts = rugcheck.get("knownAccounts", {})

    # Filter out LP pools and known AMMs
    real_holders = []
    for h in holders:
        addr = h.get("address", "")
        account_info = known_accounts.get(addr, {})
        account_type = account_info.get("type", "")
        account_name = account_info.get("name", "")

        # Skip LP/DEX accounts
        if is_lp_or_dex_account(account_type, account_name, addr):
            continue

        real_holders.append(h)

    if real_holders:
        top_10_real_pct = sum(h.get("pct", 0) for h in real_holders[:10])

        if top_10_real_pct > 80:
            score += 20
            reasons.append(f"+20: Extreme holder concentration ({top_10_real_pct:.1f}% in top 10 non-LP wallets)")
        elif top_10_real_pct > 50:
            score += 10
            reasons.append(f"+10: High holder concentration ({top_10_real_pct:.1f}% in top 10 non-LP wallets)")

        # Single large holder check
        if real_holders[0].get("pct", 0) > 30:
            score += 15
            reasons.append(f"+15: Single wallet holds {real_holders[0]['pct']:.1f}%")
        elif real_holders[0].get("pct", 0) > 20:
            score += 8
            reasons.append(f"+8: Single wallet holds {real_holders[0]['pct']:.1f}%")

    # === CREATOR BALANCE ===
    creator_balance = rugcheck.get("creatorBalance", 0)
    total_supply = rugcheck.get("token", {}).get("supply", 1)
    decimals = rugcheck.get("token", {}).get("decimals", 9)

    if total_supply and creator_balance:
        creator_pct = (creator_balance / total_supply) * 100
        if creator_pct > 20:
            score += 15
            reasons.append(f"+15: Creator still holds {creator_pct:.1f}%")
        elif creator_pct > 10:
            score += 8
            reasons.append(f"+8: Creator holds {creator_pct:.1f}%")

    # === RUGCHECK FLAGS ===
    for risk in risks:
        level = risk.get("level", "")
        name = risk.get("name", "")
        # Skip mutable metadata (already counted)
        if "mutable" in name.lower():
            continue
        if level in ("error", "danger"):
            score += 15
            reasons.append(f"+15: {name}")
        elif level == "warn":
            score += 5
            reasons.append(f"+5: {name}")

    # === POSITIVE SIGNALS (reduce score) ===
    # LP locked
    markets = rugcheck.get("markets", [])
    max_lp_locked = 0
    for market in markets:
        lp_info = market.get("lp", {})
        locked_pct = lp_info.get("lpLockedPct", 0) or 0
        max_lp_locked = max(max_lp_locked, locked_pct)

    if max_lp_locked >= 90:
        score -= 10
        reasons.append(f"-10: LP {max_lp_locked:.0f}% locked")
    elif max_lp_locked >= 50:
        score -= 5
        reasons.append(f"-5: LP {max_lp_locked:.0f}% locked")

    # Creator sold/distributed
    if creator_balance == 0:
        score -= 5
        reasons.append("-5: Creator holds 0 tokens")

    # Clamp score to 0-100
    score = max(0, min(100, score))

    return score, reasons


def check_token_program(program: str, extensions: list | None) -> list[str]:
    """Check for Token-2022 and risky extensions."""
    warnings = []

    if program == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb":
        warnings.append("⚠️ Token-2022 program (check extensions)")

        if extensions:
            risky_extensions = {
                "transferHook": "🚨 TransferHook (can block/tax transfers)",
                "permanentDelegate": "🚨 PermanentDelegate (can drain tokens)",
                "transferFeeConfig": "⚠️ TransferFee (hidden fees on transfers)",
                "defaultAccountState": "⚠️ DefaultAccountState (accounts may default frozen)",
            }
            for ext in extensions:
                ext_name = ext.get("extension") if isinstance(ext, dict) else str(ext)
                if ext_name in risky_extensions:
                    warnings.append(risky_extensions[ext_name])

    return warnings


def analyze_holders(holders: list, known_accounts: dict) -> tuple[float, float, list[str]]:
    """
    Analyze top holder concentration and return warnings.
    Returns (total_top_10_pct, real_holder_pct, warnings)
    """
    warnings = []

    if not holders:
        return 0, 0, ["⚠️ No holder data available"]

    # Separate LP pools from real holders
    lp_pct = 0
    real_holders = []

    for h in holders:
        addr = h.get("address", "")
        account_info = known_accounts.get(addr, {})
        account_type = account_info.get("type", "")
        account_name = account_info.get("name", "")

        is_lp = is_lp_or_dex_account(account_type, account_name, addr)

        if is_lp:
            lp_pct += h.get("pct", 0)
        else:
            real_holders.append(h)

    # Calculate concentrations
    top_10_pct = sum(h.get("pct", 0) for h in holders[:10])
    real_top_10_pct = sum(h.get("pct", 0) for h in real_holders[:10])

    # Only warn about real holder concentration
    if real_top_10_pct > 80:
        warnings.append(f"🚨 Extreme concentration: Top 10 non-LP wallets hold {real_top_10_pct:.1f}%")
    elif real_top_10_pct > 50:
        warnings.append(f"⚠️ High concentration: Top 10 non-LP wallets hold {real_top_10_pct:.1f}%")

    # Check for single large real holder
    if real_holders and real_holders[0].get("pct", 0) > 20:
        warnings.append(f"⚠️ Largest non-LP holder owns {real_holders[0]['pct']:.1f}%")

    return top_10_pct, real_top_10_pct, warnings


def format_report(mint: str, rugcheck: dict, dex: dict | None, bags_creators: list | None = None) -> str:
    """Format the final report."""
    lines = []

    # Header
    token_meta = rugcheck.get("tokenMeta", {})
    name = token_meta.get("name", "Unknown")
    symbol = token_meta.get("symbol", "???")

    lines.append(f"# Token Analysis: {name} (${symbol})")
    lines.append(f"**Mint:** `{mint}`")
    lines.append("")

    # Calculate our own score
    custom_score, score_reasons = calculate_custom_score(rugcheck, dex)
    risk_label = get_risk_label(custom_score)

    lines.append(f"## Overall Risk: {risk_label} (Score: {custom_score}/100)")
    lines.append("")

    # Generate narrative analysis
    narrative = generate_narrative(rugcheck, dex, custom_score, score_reasons)
    lines.append(narrative)
    lines.append("")

    # Show scoring breakdown (collapsible detail)
    if score_reasons:
        lines.append("<details>")
        lines.append("<summary><b>Score Breakdown</b></summary>")
        lines.append("")
        for reason in score_reasons:
            lines.append(f"- {reason}")
        lines.append("</details>")
        lines.append("")

    # Market Data (from DexScreener)
    lines.append("## Market Data")
    if dex:
        price = dex.get("priceUsd", "N/A")
        mc = dex.get("marketCap")
        liq = dex.get("liquidity", {}).get("usd")
        vol_24h = dex.get("volume", {}).get("h24")
        price_change = dex.get("priceChange", {}).get("h24")

        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Price | ${price} |")
        lines.append(f"| Market Cap | {format_number(mc)} |")
        lines.append(f"| Liquidity | {format_number(liq)} |")
        lines.append(f"| 24h Volume | {format_number(vol_24h)} |")
        if price_change:
            emoji = "📈" if float(price_change) > 0 else "📉"
            lines.append(f"| 24h Change | {emoji} {price_change}% |")
        lines.append("")
    else:
        lines.append("*No market data available (token may not be trading yet)*")
        lines.append("")

    # Authority Status
    lines.append("## Authority Status")
    lines.append("| Check | Status |")
    lines.append("|-------|--------|")

    mint_auth = rugcheck.get("mintAuthority")
    freeze_auth = rugcheck.get("freezeAuthority")

    mint_status = "❌ ACTIVE (can mint more)" if mint_auth else "✅ Revoked"
    freeze_status = "❌ ACTIVE (can freeze)" if freeze_auth else "✅ Revoked"

    lines.append(f"| Mint Authority | {mint_status} |")
    lines.append(f"| Freeze Authority | {freeze_status} |")

    # Mutable metadata check
    mutable = rugcheck.get("mutableMetadata", False)
    if mutable:
        lines.append(f"| Mutable Metadata | ⚠️ Yes (can change) |")
    else:
        lines.append(f"| Mutable Metadata | ✅ No |")
    lines.append("")

    # LP Status
    lines.append("## Liquidity")
    lp_locked_pct = rugcheck.get("lpLockedPct")

    if lp_locked_pct is not None:
        lines.append(f"- **LP Locked:** {format_percent(lp_locked_pct)}")
        if lp_locked_pct < 50:
            lines.append("- ⚠️ Low LP lock - liquidity could be pulled")
        elif lp_locked_pct >= 90:
            lines.append("- ✅ Strong LP lock")
    else:
        lines.append("- **LP Locked:** Unknown (no locker data)")
    lines.append("")

    # Holder Analysis
    lines.append("## Top Holders")
    holders = rugcheck.get("topHolders", [])
    known_accounts = rugcheck.get("knownAccounts", {})
    top_10_pct, real_top_10_pct, holder_warnings = analyze_holders(holders, known_accounts)

    lines.append(f"**Top 10 Concentration:** {format_percent(top_10_pct)} (Non-LP wallets: {format_percent(real_top_10_pct)})")
    lines.append("")

    if holders:
        lines.append("| Rank | Address | % Supply | Type |")
        lines.append("|------|---------|----------|------|")
        for i, h in enumerate(holders[:7], 1):
            addr = h.get("address", "???")
            short_addr = f"{addr[:4]}...{addr[-4:]}" if len(addr) > 8 else addr
            pct = h.get("pct", 0)

            # Check if this is a known account (LP pool, etc)
            account_info = known_accounts.get(addr, {})
            account_name = account_info.get("name", "")
            account_type = account_info.get("type", "")

            if account_name:
                type_label = f"🏊 {account_name}" if is_lp_or_dex_account(account_type, account_name, addr) else account_name
            elif account_type:
                type_label = account_type
            else:
                type_label = "Wallet"

            lines.append(f"| {i} | `{short_addr}` | {pct:.2f}% | {type_label} |")
        lines.append("")

    # Token Program Warnings
    program = rugcheck.get("tokenProgram", "")
    extensions = rugcheck.get("token_extensions")
    program_warnings = check_token_program(program, extensions)

    # Collect red flags (high-level summary; details in score breakdown)
    lines.append("## Summary")
    red_flags = []

    # Authority flags
    if mint_auth:
        red_flags.append("🚨 Mint authority active - can create more tokens")
    if freeze_auth:
        red_flags.append("🚨 Freeze authority active - can freeze your tokens")

    # Holder flags
    red_flags.extend(holder_warnings)

    # Program flags
    red_flags.extend(program_warnings)

    # RugCheck risks (only danger/error level - warnings in score breakdown)
    risks = rugcheck.get("risks", [])
    for risk in risks:
        level = risk.get("level", "")
        name = risk.get("name", "Unknown risk")
        if level in ["error", "danger"]:
            red_flags.append(f"🚨 {name}")

    if red_flags:
        for flag in red_flags:
            lines.append(f"- {flag}")
    else:
        lines.append("- ✅ No major red flags detected")
    lines.append("")

    # Creator info (on-chain)
    creator = rugcheck.get("creator")
    if creator:
        lines.append("## On-Chain Creator")
        short_creator = f"{creator[:8]}...{creator[-8:]}"
        lines.append(f"**Wallet:** `{short_creator}`")
        creator_balance = rugcheck.get("creatorBalance", 0)
        lines.append(f"**Creator Token Balance:** {creator_balance:,.0f}")
        lines.append("")

    # BAGS creators/royalty recipients (if available)
    if bags_creators:
        lines.append(format_bags_creators(bags_creators, mint))

    # Links
    lines.append("## Links")
    lines.append(f"- [RugCheck](https://rugcheck.xyz/tokens/{mint})")
    lines.append(f"- [DexScreener](https://dexscreener.com/solana/{mint})")
    lines.append(f"- [Solscan](https://solscan.io/token/{mint})")

    if dex:
        # Social links from DexScreener
        info = dex.get("info", {})
        socials = info.get("socials", [])
        for social in socials:
            platform = social.get("type", "")
            url = social.get("url", "")
            if platform and url:
                lines.append(f"- [{platform.title()}]({url})")

    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC · Data from RugCheck + DexScreener*")
    lines.append("")
    lines.append("⚠️ **No analysis can guarantee safety.** On-chain data can't detect team coordination, social engineering, or planned dumps. Even \"safe\" tokens can fail. This is not financial advice - DYOR and never risk more than you can lose!")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tokenscreen.py <contract_address> [--royalty <wallet> [twitter_handle]]")
        print("Example: python3 tokenscreen.py 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
        print("         python3 tokenscreen.py 7GC... --royalty ABC123... @handle")
        sys.exit(1)

    mint = sys.argv[1].strip()

    # Parse optional --royalty flag
    royalty_wallet = None
    royalty_twitter = None
    if "--royalty" in sys.argv:
        royalty_idx = sys.argv.index("--royalty")
        if royalty_idx + 1 < len(sys.argv):
            royalty_wallet = sys.argv[royalty_idx + 1].strip()
        if royalty_idx + 2 < len(sys.argv) and not sys.argv[royalty_idx + 2].startswith("--"):
            royalty_twitter = sys.argv[royalty_idx + 2].strip().lstrip("@")

    # Validate address format (basic check)
    if len(mint) < 32 or len(mint) > 44:
        print(f"Error: Invalid Solana address format: {mint}")
        print("Solana addresses are typically 32-44 characters (base58)")
        sys.exit(1)

    # Fetch data
    print(f"Analyzing token: {mint}...", file=sys.stderr)

    rugcheck = get_rugcheck_report(mint)
    if not rugcheck:
        print(f"Error: Token not found on RugCheck. It may be too new or invalid.")
        print(f"Try checking manually: https://rugcheck.xyz/tokens/{mint}")
        sys.exit(1)

    dex = get_dexscreener_data(mint)

    # Try to fetch BAGS creators (returns None if not a BAGS token)
    print(f"Checking BAGS API for creator info...", file=sys.stderr)
    bags_creators = get_bags_creators(mint)
    if bags_creators:
        print(f"Found {len(bags_creators)} BAGS creator(s)/recipient(s)", file=sys.stderr)
    else:
        print(f"Not a BAGS token or no creator data", file=sys.stderr)

    # Generate and print report
    report = format_report(mint, rugcheck, dex, bags_creators)
    print(report)

    # Run royalty recipient analysis if requested manually
    if royalty_wallet:
        print("")
        print("---")
        print("")
        royalty_report = analyze_royalty_recipient(royalty_wallet, mint, royalty_twitter)
        print(royalty_report)
    # Auto-analyze BAGS recipients if we have them (and no manual override)
    elif bags_creators:
        for creator in bags_creators:
            wallet = creator.get("wallet")
            twitter = creator.get("twitterUsername")
            if wallet:
                print("")
                print("---")
                print("")
                print(f"Analyzing {'creator' if creator.get('isCreator') else 'royalty recipient'}: {twitter or wallet[:12]}...", file=sys.stderr)
                royalty_report = analyze_royalty_recipient(wallet, mint, twitter)
                print(royalty_report)


if __name__ == "__main__":
    main()
