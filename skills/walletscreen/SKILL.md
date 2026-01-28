---
name: walletscreen
description: Analyze any Solana wallet's token launch history. Use when user asks "check this wallet", "is this wallet a rugger", "walletscreen", "/walletscreen", or wants to investigate a wallet's history. Returns launch history, rug rate, wallet age risk, and recommendation.
---

# /walletscreen - Wallet History Analyzer

You are a Solana wallet analyst. When the user provides a wallet address, run the walletscreen script to analyze their token launch history.

## Usage

```
/walletscreen <wallet_address>
```

Examples:
```
/walletscreen Dzp1SrZ474xwGp6ZEP6cNKo39u9zeXe1YAuTkyZyv3t4
/walletscreen EPjKowxJFK7i6aCTFb18XXHptKSZEbKdapZpJdtW1t8h
```

## How to Run

```bash
python3 walletscreen.py <wallet_address>
```

## What It Checks

1. **Wallet Age** - Fresh wallet (< 3 days) is extreme risk
2. **Launch History** - All tokens created by this wallet
3. **Token Outcomes** - Active, dead (< $1k liquidity), or rugged
4. **Rug Rate** - Percentage of tokens that rugged/died
5. **Launch Frequency** - Serial launcher detection
6. **Risk Score** - 0-100 with transparent breakdown

## Interpreting Results

- **Score 0-30**: Established wallet with good track record
- **Score 31-60**: Mixed history, proceed with caution
- **Score 61-80**: High risk wallet
- **Score 81-100**: Extreme risk (fresh wallet, serial rugger, etc.)

## Red Flags

- Wallet age < 3 days (burner wallet)
- First-ever token launch (no track record)
- Any confirmed rugs in history
- Serial launcher (> 1 token per week)
- High concentration of dead tokens

## Use Cases

- **Copy trading** - Check if a wallet you want to follow is legit
- **Post-rug investigation** - See if a wallet has rugged before
- **Verifying claims** - Someone says "I'm a legit dev" → check their history
- **Deep dive** - After `/tokenscreen` shows a creator, dig deeper on that wallet

## Data Sources

- **RugCheck API** - Token rug status
- **Helius API** - Transaction history, wallet age
- **DexScreener API** - Current liquidity for outcome status

## Environment Variables Required

- `HELIUS_API_KEY` - Required

Set as environment variable or create a `.env` file.

## Limitations

- Helius free tier: max 100 transactions per call
- Very new tokens may not have RugCheck data yet
- Cannot detect coordinated multi-wallet operations

## ⚠️ Disclaimer

**This is not financial advice. No investment is 100% safe.** Wallet history is just one factor. Even clean wallets can rug, and new wallets can be legitimate. Never invest more than you can afford to lose. DYOR.
