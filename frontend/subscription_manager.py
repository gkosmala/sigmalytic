"""
Decouples "who requests a live symbol subscription" (any Dash worker,
calling this from load_symbol() or the Weis Analysis fetch trigger)
from "who actually holds the Alpaca WebSocket connection" (only
whichever backend instance won the leader lock). Callers just declare
what their slot currently wants; only the leader reads this and
reconciles its real subscriptions against it.

Using a single Redis hash (slot -> symbol) rather than explicit
reference counting gets both confirmed behaviors for free:
  - Unsubscribe-on-switch: overwriting a slot's value naturally drops
    the old symbol from the hash's values (unless another slot still
    holds it).
  - Reference-counted sharing: a symbol stays "desired" as long as ANY
    slot's value still points to it, even if a different slot moves
    off it -- no manual counting needed, it falls out of using distinct
    slots as hash keys.
"""
HASH_KEY = "alpaca_stream_desired_subscriptions"


class SubscriptionManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    def request(self, slot: str, symbol: str):
        """Declares that `slot` now wants `symbol` streamed live.
        Passing symbol=None clears that slot's request entirely."""
        if symbol:
            self.redis.hset(HASH_KEY, slot, symbol.upper())
        else:
            self.redis.hdel(HASH_KEY, slot)

    def get_desired_symbols(self) -> set:
        """The current, deduplicated set of symbols any slot wants
        streamed right now -- what the leader should be subscribed to."""
        values = self.redis.hvals(HASH_KEY)
        return set(values)

    def get_slots(self) -> dict:
        """For diagnostics: slot -> symbol, as currently requested."""
        return self.redis.hgetall(HASH_KEY)
