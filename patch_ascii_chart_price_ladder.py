from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_ASCII_CHART_PRICE_LADDER_FIX
# Removes corrupted emoji/arrows/middle-dot symbols from Price Ladder and chart header/footer.

# 1. Remove arrow markers from all price ladder rows.
text = re.sub(
    r'(level_row\("Breakout",\s*kl\.breakout,\s*TEAL_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)
text = re.sub(
    r'(level_row\("Liquidity",\s*kl\.prior_high,\s*TEAL_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)
text = re.sub(
    r'(level_row\("Expansion",\s*kl\.expansion,\s*TEAL_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)
text = re.sub(
    r'(level_row\("Trigger",\s*kl\.trigger,\s*YELLOW_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)
text = re.sub(
    r'(level_row\("Trap Door",\s*kl\.trap,\s*RED_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)
text = re.sub(
    r'(level_row\("Fail Gate",\s*kl\.fail,\s*RED_DIM,\s*)arrow=.*?\)',
    r'\1arrow="")',
    text
)

# 2. Replace chart title line with ASCII-safe text.
text = re.sub(
    r'html\.Span\(f".*?\{symbol\}.*?Smart Chart",\s*style=',
    'html.Span(f"{symbol} - Smart Chart", style=',
    text,
    count=1,
    flags=re.DOTALL
)

# 3. Replace chart subtitle separators with ASCII-safe hyphens.
text = re.sub(
    r'html\.Span\(f"\s*\{live_age\}.*?\{tf\}.*?\{regime\.replace\([^)]*\)\.title\(\)\}",\s*style=',
    'html.Span(f"{live_age} - {tf} - {regime.replace(\'_\',\' \').title()}", style=',
    text,
    count=1,
    flags=re.DOTALL
)

# 4. Replace chart footer candle count separator with ASCII-safe hyphen.
text = re.sub(
    r'html\.Span\(f"\{tf\}.*?\{len\(candles\)\} candles",\s*style=',
    'html.Span(f"{tf} - {len(candles)} candles", style=',
    text,
    count=1,
    flags=re.DOTALL
)

# 5. Remove common corrupted mojibake sequences still visible in this area if present.
for bad in [
    "ðŸ“Š", "ðŸ“ˆ", "ðŸš€", "ðŸŒ±", "â–²", "â–¼", "â†‘", "â†“",
    "Â·", "Â", "â€¢", "â€”"
]:
    text = text.replace(bad, "")

# Verification: these exact visible corruptions should not remain.
bad_remaining = [bad for bad in ["ðŸ“Š", "â–²", "â–¼", "Â·"] if bad in text]
if bad_remaining:
    raise SystemExit("FAILED: corrupted chart/price ladder symbols remain: " + ", ".join(bad_remaining))

path.write_text(text, encoding="utf-8")
print("V2 ASCII CHART PRICE LADDER FIX OK")
