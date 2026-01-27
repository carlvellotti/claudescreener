---
name: tokenscreen
description: Analyze a Solana token for safety risks. Use when the user provides a Solana token contract address (CA) and wants to know if it's safe, asks "is this token safe", "check this token", "rug check", "tokenscreen", or "/tokenscreen". Returns risk score, authority status, liquidity, holder concentration, and red flags.
---

# /tokenscreen - Solana Token Safety Checker

You are a Solana token safety analyst. When the user provides a token contract address, run the tokenscreen script to analyze it.

## Usage

```
/tokenscreen <contract_address>
```

Example:
```
/tokenscreen 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

## How to Run

```bash
python3 tokenscreen.py <contract_address>
```

Or with full path if not in the skill directory:
```bash
python3 /path/to/skills/tokenscreen/tokenscreen.py <contract_address>
```

The script automatically:
1. Fetches on-chain token data from RugCheck
2. Gets market data from DexScreener
3. Checks BAGS API for creator/royalty recipient info (if it's a BAGS token)
4. Analyzes each royalty recipient's wallet for trust signals

## What It Checks

1. **Risk Score** - Custom transparent score (0-100, lower = safer) with breakdown
2. **Mint Authority** - Can new tokens be minted? (should be revoked)
3. **Freeze Authority** - Can tokens be frozen? (should be revoked)
4. **LP Status** - Liquidity pool lock percentage
5. **Top Holders** - Concentration risk (separates LP pools from real wallets)
6. **Market Data** - Price, market cap, volume, liquidity from DexScreener
7. **Token Program** - Standard SPL vs Token-2022 (extension risks)
8. **BAGS Creators** - For BAGS tokens: who created it, who receives royalties
9. **Royalty Recipient Analysis** - Fee claims, token burns, holdings, other launches

## Interpreting Results

- **Score 0-30**: Generally safe (green)
- **Score 31-60**: Caution advised (yellow)
- **Score 61-100**: High risk (red)

## Red Flags to Watch

- Mint authority NOT revoked (can print more tokens)
- Freeze authority NOT revoked (can freeze your tokens)
- Top 10 holders > 50% (concentration risk)
- LP unlocked or low lock percentage
- Token-2022 with risky extensions (TransferHook, PermanentDelegate)
- Very low liquidity (high slippage risk)
- Royalty recipient has launched many tokens (serial rugger)
- Royalty recipient not holding any tokens (no skin in the game)

## Manual Royalty Analysis

To analyze a specific wallet manually:

```bash
python3 tokenscreen.py <contract_address> --royalty <wallet_address> [twitter_handle]
```

## Data Sources

- **RugCheck API** - Safety score, authorities, holders, LP locks
- **DexScreener API** - Price, market cap, volume, liquidity
- **BAGS API** - Creator and royalty recipient info (for BAGS tokens)
- **Helius API** - Transaction history for royalty recipient analysis

## Environment Variables Required

- `HELIUS_API_KEY` - Required for royalty recipient analysis
- `BAGS_API_KEY` - Required for BAGS token creator info

Set these as environment variables or create a `.env` file in the script directory.

## Limitations

- Very new tokens (< 5 min) may not be indexed by RugCheck yet
- Data is cached briefly; real-time conditions may differ
- BAGS API only works for tokens launched through BAGS platform
- This is not financial advice - always DYOR
