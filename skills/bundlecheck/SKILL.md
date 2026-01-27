---
name: bundlecheck
description: Detect coordinated sniping at token launch. Use when user asks "was this token bundled", "check for snipers", "block 0 check", "bundlecheck", or "/bundlecheck". Returns Block 0 buy concentration, number of snipers, and manipulation risk assessment.
---

# /bundlecheck - Launch Manipulation Detector

You are a Solana token launch analyst. When the user provides a token contract address, run the bundlecheck script to detect coordinated sniping.

## Usage

```
/bundlecheck <contract_address>
```

Example:
```
/bundlecheck 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

## How to Run

```bash
python3 bundlecheck.py <contract_address>
```

## What It Checks

1. **Block 0 Analysis** - Who bought in the same block as token creation?
2. **Sniper Count** - How many unique wallets bought in Block 0?
3. **Supply Concentration** - What % of supply was grabbed at launch?
4. **Coordination Signals** - Same-block buys from multiple wallets = suspicious
5. **Risk Assessment** - Low/Medium/High/Critical manipulation risk

## Why This Matters

The "$KING scam" pattern: Scammers create 80+ wallets, each buys ~1% in Block 0. Top holder check shows "distributed" but it's all one person. They coordinate dump later.

**Red flags:**
- 10+ wallets buying in Block 0
- >20% of supply bought in first block
- Fresh wallets (created same day) doing the buying

## Interpreting Results

- **0-5 Block 0 buyers, <10% supply**: Normal launch
- **5-15 buyers, 10-30% supply**: Moderate concern
- **15+ buyers, >30% supply**: High manipulation risk
- **Any single wallet >5% in Block 0**: Sniper alert

## Data Sources

- **Helius API** - Transaction history, parsed transfers

## Environment Variables Required

- `HELIUS_API_KEY` - Required

Set as environment variable or create a `.env` file.

## Limitations

- Only analyzes Block 0 (first slot) - doesn't catch multi-block coordination
- Cannot determine if wallets are truly linked (just same-block timing)
- Very new tokens may not have full transaction indexing yet
- This is not financial advice - DYOR
