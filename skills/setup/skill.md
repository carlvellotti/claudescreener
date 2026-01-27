# ClaudeScreener Setup

Help users configure API keys for ClaudeScreener tools.

## Check Current Status

First, check which API keys are configured:

```bash
# Check for HELIUS_API_KEY
if [ -n "$HELIUS_API_KEY" ]; then
    echo "HELIUS_API_KEY: configured (in environment)"
elif [ -f .env ] && grep -q "HELIUS_API_KEY=" .env; then
    echo "HELIUS_API_KEY: configured (in .env)"
else
    echo "HELIUS_API_KEY: NOT CONFIGURED"
fi

# Check for BAGS_API_KEY (optional)
if [ -n "$BAGS_API_KEY" ]; then
    echo "BAGS_API_KEY: configured (in environment)"
elif [ -f .env ] && grep -q "BAGS_API_KEY=" .env; then
    echo "BAGS_API_KEY: configured (in .env)"
else
    echo "BAGS_API_KEY: not configured (optional)"
fi
```

## Required APIs

### Helius (Required)
**What it does:** Provides Solana transaction history data
**Skills that need it:** All three (/tokenscreen, /walletscreen, /bundlecheck)

**Setup steps:**
1. Go to https://helius.dev
2. Create a free account
3. Copy your API key
4. Set it up (choose one method):

**Option A - Environment variable:**
```bash
export HELIUS_API_KEY=your_key_here
```

**Option B - Add to .env file:**
```bash
echo "HELIUS_API_KEY=your_key_here" >> .env
```

### BAGS (Optional)
**What it does:** Provides creator/royalty info for tokens launched on bags.fm
**Skills that need it:** /tokenscreen (enhanced creator info)

**Setup steps:**
1. Go to https://dev.bags.fm
2. Create an account and get an API key
3. Set it up (same options as above)

## Verify Setup

After configuring, test with:
```bash
/tokenscreen 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

If you see a report instead of an error, you're all set!

## Troubleshooting

**"HELIUS_API_KEY not found" error:**
- Make sure the key is set in your current terminal session
- If using .env, ensure it's in the directory where you run Claude Code
- Try: `echo $HELIUS_API_KEY` to verify it's set

**API rate limits:**
- Helius free tier has generous limits for personal use
- If you hit limits, wait a few minutes or upgrade your plan
