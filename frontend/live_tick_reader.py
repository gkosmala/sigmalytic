"""
Reads the coherent per-symbol tick hash (live_tick:{symbol}) that
tools/render_alpaca_stream_worker.py's trade/quote/bar handlers write
into. Deliberately all-or-nothing: returns a full, internally-coherent
tick only if trade, quote, AND bar data are all present and each
individually fresh enough -- never a partial mix (e.g. a fresh
streamed price paired with a stale bar's volume), since that would be
a real, silent inconsistency, not an improvement over the plain REST
poll it's meant to enhance.
"""
import time
import math
from datetime import datetime, timezone

TRADE_QUOTE_MAX_AGE_SECONDS = 15
BAR_MAX_AGE_SECONDS = 90  # bars arrive ~once/minute; this must be looser than the trade/quote threshold


def read_coherent_tick(redis_client, symbol: str, now: float = None):
    """
    Returns {"price", "bid_price", "bid_size", "ask_price", "ask_size",
    "volume", "timestamp"} if the stream has a full, fresh tick for this
    symbol, else None -- meaning the caller should fall back to its
    existing REST-polled snapshot entirely, not blend the two.

    "volume" here is the latest bar's volume, matching what the old
    REST endpoint's "volume" field already meant (Alpaca's latest-bar
    endpoint is itself bar-based) -- not a single trade's size, which
    is a different, smaller number that would silently change the
    meaning of that field if used instead.

    UPDATED (2026-09-14): added bid_size/ask_size to the returned dict.
    Confirmed directly in tools/render_alpaca_stream_worker.py's
    write_quote_to_hash() that these fields were already being written
    to the Redis hash on every quote update -- this function just
    wasn't reading them out. No change to the streaming worker itself
    was needed.
    """
    now = now if now is not None else time.time()

    try:
        raw = redis_client.hgetall(f"live_tick:{symbol}")
    except Exception:
        return None

    if not raw:
        return None

    # FIX (2026-09-23): frontend Redis returns byte keys. The stream
    # worker writes string field names, but hgetall() on this client
    # returns bytes, so required.issubset(raw.keys()) was always false.
    raw = {key.decode("utf-8") if isinstance(key, bytes) else key: value
           for key, value in raw.items()}

    required = {"last_price", "last_ts", "bid_price", "bid_size", "ask_price", "ask_size", "quote_ts", "bar_volume", "bar_ts"}
    if not required.issubset(raw.keys()):
        return None  # not all three event types have reported for this symbol yet

    try:
        last_ts = float(raw["last_ts"])
        quote_ts = float(raw["quote_ts"])
        bar_ts = float(raw["bar_ts"])
    except (KeyError, ValueError, TypeError):
        return None

    if (now - last_ts) > TRADE_QUOTE_MAX_AGE_SECONDS:
        return None
    if (now - quote_ts) > TRADE_QUOTE_MAX_AGE_SECONDS:
        return None
    if (now - bar_ts) > BAR_MAX_AGE_SECONDS:
        return None

    try:
        return {
            "price": float(raw["last_price"]),
            "bid_price": float(raw["bid_price"]),
            "bid_size": int(float(raw["bid_size"])),
            "ask_price": float(raw["ask_price"]),
            "ask_size": int(float(raw["ask_size"])),
            "volume": int(float(raw["bar_volume"])),
            "timestamp": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat(),
        }
    except (KeyError, ValueError, TypeError):
        return None


def read_fresh_quote(redis_client, symbol: str, now: float = None):
    """Read a fresh bid/ask independently of the trade and one-minute bar.

    A quote is useful even when there has been no recent trade or bar. Last
    price and bar volume are returned only when *their own* timestamps are
    fresh, so the UI can label missing fields without hiding the quote.
    """
    now = time.time() if now is None else now
    try:
        raw = redis_client.hgetall(f"live_tick:{symbol.upper()}")
        raw = {k.decode("utf-8") if isinstance(k, bytes) else k: v
               for k, v in raw.items()}
        quote_ts = float(raw["quote_ts"])
        bid = float(raw["bid_price"])
        ask = float(raw["ask_price"])
        # Alpaca SIP equity quote sizes are round lots (100 shares).
        bid_size = int(float(raw["bid_size"])) * 100
        ask_size = int(float(raw["ask_size"])) * 100
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    except Exception:  # Redis may be unavailable temporarily.
        return None

    if (not all(math.isfinite(x) for x in (quote_ts, bid, ask))
            or not -2 <= now - quote_ts <= TRADE_QUOTE_MAX_AGE_SECONDS
            or bid <= 0 or ask <= 0
            or bid_size < 0 or ask_size < 0):
        return None

    result = {
        "symbol": symbol.upper(),
        "source": "alpaca_stream",
        "bid_price": bid, "bid_size": bid_size,
        "ask_price": ask, "ask_size": ask_size,
        "quote_timestamp": datetime.fromtimestamp(quote_ts, tz=timezone.utc).isoformat(),
    }
    try:
        last_ts = float(raw["last_ts"])
        last_price = float(raw["last_price"])
        if (math.isfinite(last_ts) and math.isfinite(last_price)
                and 0 <= now - last_ts <= TRADE_QUOTE_MAX_AGE_SECONDS
                and last_price > 0):
            result["price"] = last_price
            result["last_timestamp"] = datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat()
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    try:
        bar_ts = float(raw["bar_ts"])
        volume = int(float(raw["bar_volume"]))
        if math.isfinite(bar_ts) and 0 <= now - bar_ts <= BAR_MAX_AGE_SECONDS and volume >= 0:
            result["volume"] = volume
            result["bar_timestamp"] = datetime.fromtimestamp(bar_ts, tz=timezone.utc).isoformat()
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return result
