# ClaudeScreener

**Three Claude Code skills to detect scams and stay safe in Solana meme coins. A $CCFE project.**

Before you ape into a token, run 3 checks in 30 seconds:

| Skill | Question | What It Checks |
|-------|----------|----------------|
| `/tokenscreen` | Is this token safe? | Rug score, mint/freeze authority, LP locks, holder concentration, creator history |
| `/walletscreen` | Is this developer legit? | Launch history, rug rate, serial launcher detection, wallet age |
| `/bundlecheck` | Was this launch manipulated? | Block 0 sniping, coordinated buys, supply concentration at launch |
| `/setup` | How do I configure this? | Guided API key setup and troubleshooting |

## $CCFE Project

This is a $CCFE project. Claude Code for Everyone aims to bring the power of Claude Code to everyone with free, accessible courses done IN Claude Code.

- **Website:** [ccforeveryone.com](https://ccforeveryone.com)
- **Coin:** [https://bags.fm/9vVh1mamReHwwHx8GShKr7vZsVWCKYWN514BmRvSBAGS](https://bags.fm/9vVh1mamReHwwHx8GShKr7vZsVWCKYWN514BmRvSBAGS)

---

## ⚠️ Disclaimer

**This is not financial advice. No investment is 100% safe.**

These tools analyze on-chain data to help identify potential risks, but they **cannot guarantee safety**. They cannot detect:
- Team coordination and insider planning
- Social engineering and fake communities
- "Slow rugs" where devs gradually sell over weeks
- Scams that happen after the analysis window
- Wallets that appear independent but are controlled by one person

Even tokens that pass all checks can still fail or rug. **Never invest more than you can afford to lose.** Always do your own research (DYOR) and treat any meme coin investment as high-risk speculation.

---

## The Problem

- **98.7%** of Pump.fun tokens exhibit scam characteristics
- Manual validation takes **5-10 minutes** across 5-6 tools
- Rug pulls execute in **under 60 seconds**
- You can't check fast enough

## The Solution

ClaudeScreener consolidates data from multiple sources (RugCheck, DexScreener, Helius, BAGS) and has Claude interpret it for you. What took 5-10 minutes now takes 10 seconds.

---

## Quick Start

### Option A: Install as Plugin (Recommended)

```bash
/plugin install carlvellotti/claudescreener
```

That's it! The plugin will be available immediately. Skills are namespaced as:
- `/claudescreener:tokenscreen`
- `/claudescreener:walletscreen`
- `/claudescreener:bundlecheck`
- `/claudescreener:setup`

### Option B: Manual Installation

Copy the `skills/` folder to your Claude Code skills directory:

```bash
cp -r skills/* ~/.claude/skills/
```

With manual installation, skills are available as `/tokenscreen`, `/walletscreen`, etc.

---

### API Keys

You need **one required API key** (Helius). BAGS is optional.

| API | Required? | Cost | Get it at |
|-----|-----------|------|-----------|
| **Helius** | Yes | Free (1M credits/mo) | [helius.dev](https://www.helius.dev/) |
| **BAGS** | Optional | Free | [dev.bags.fm](https://dev.bags.fm) |
| DexScreener | — | Free, no key needed | — |
| RugCheck | — | Free, no key needed | — |

### 3. Set up your `.env` file

Create a `.env` file in your skills directory (or set environment variables):

```bash
HELIUS_API_KEY=your_helius_key_here
BAGS_API_KEY=your_bags_key_here  # Optional, for BAGS token creator info
```

### 4. Configure API keys

Run the setup skill for guided configuration:

```
/setup
```

Or manually set environment variables:
```bash
export HELIUS_API_KEY=your_key_here
```

### 5. Use the skills

```
/tokenscreen 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
/walletscreen Dzp1SrZ474xwGp6ZEP6cNKo39u9zeXe1YAuTkyZyv3t4
/bundlecheck 9vVh1mamReHwwHx8GShKr7vZsVWCKYWN514BmRvSBAGS
```

---

## API Setup Details

### Helius (Required)

Helius provides parsed Solana transaction data. You need this for all three skills.

1. Go to [helius.dev](https://www.helius.dev/)
2. Sign up for a free account
3. Create a new API key
4. Copy the key to your `.env` file

Free tier includes 1M credits/month - plenty for personal use.

### BAGS (Optional)

BAGS API provides creator and royalty recipient info for tokens launched on [bags.fm](https://bags.fm). Without this, `/tokenscreen` will still work but won't show BAGS-specific creator data.

1. Go to [dev.bags.fm](https://dev.bags.fm)
2. Connect your wallet
3. Generate an API key
4. Copy the key to your `.env` file

---

## Usage Examples

### /tokenscreen - Check if a token is safe

```
/tokenscreen 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

**Output includes:**
- Risk score (0-100) with breakdown
- Mint/freeze authority status
- LP lock percentage
- Top holder concentration (excludes LP pools)
- Creator wallet and balance
- For BAGS tokens: creator identity and royalty recipients with their history

### /walletscreen - Check if a developer is legit

```
/walletscreen Dzp1SrZ474xwGp6ZEP6cNKo39u9zeXe1YAuTkyZyv3t4
```

**Output includes:**
- Wallet age (< 3 days = EXTREME RISK)
- Total tokens launched
- Outcome of each token (active, dead, rugged)
- Rug rate percentage
- Serial launcher detection

### /bundlecheck - Check if launch was manipulated

```
/bundlecheck 9vVh1mamReHwwHx8GShKr7vZsVWCKYWN514BmRvSBAGS
```

**Output includes:**
- Number of Block 0 buyers
- % of supply sniped at launch
- List of snipers with amounts
- Manipulation risk score

---

## What's Next

Features we'd love to add:

### Coordinated Wallet Detection
The holy grail of scam detection. Scammers create 80+ wallets, each buying ~1% at launch. They look independent but are controlled by one person. Detecting this requires:
- Timing correlation analysis (did these wallets receive funding in the same time window?)
- Cross-wallet pattern matching
- This needs infrastructure (database indexing) beyond API calls

### Other Ideas
- **LP unlock warnings** - Alert when LP unlock date is approaching
- **Whale movement alerts** - Notify when top holders sell
- **Historical price integration** - More accurate P&L for wallet analysis
- **Community flagging** - Integrate known scam wallet databases

Want to contribute? PRs welcome!

---

## How It Works

ClaudeScreener aggregates data from multiple free APIs:

| Source | Data Provided |
|--------|---------------|
| **RugCheck** | Token safety score, mint/freeze authority, holder list, LP locks |
| **DexScreener** | Price, market cap, volume, liquidity, social links |
| **Helius** | Transaction history, wallet balances, token transfers |
| **BAGS** | Creator identity, royalty recipients (for BAGS tokens) |

The skills fetch this data, combine it, and apply heuristics to produce actionable risk assessments. Claude interprets the results in plain English.

---

## Limitations

**What these tools CAN'T detect:**
- Coordinated multi-wallet operations (wallets that look independent but aren't)
- Team coordination and insider planning
- Social engineering and fake communities
- "Slow rugs" where devs gradually sell over weeks
- Rugs that happen after the analysis window

**General caveats:**
- Very new tokens (< 5 min) may not be indexed yet
- Helius free tier limits to 100 transactions per call
- Bundle detection is probabilistic - same-block buying could be legit
- This is not financial advice - always DYOR

---

## License

MIT License - use it, modify it, share it.

---

## Credits

Built for the [BAGS](https://bags.fm) community and Solana meme coin traders everywhere.

Research synthesized from: Solidus Labs reports, DexScreener/RugCheck/Birdeye comparisons, trader testimonials, and AI council review (GPT, Gemini, Grok, Claude).

**The core insight:** You can't manually check faster than scammers can rug. Automation isn't optional - it's survival.
