"""
Redis-based leader election so exactly one backend process/instance ever
holds the live Alpaca WebSocket connection, regardless of how many
backend processes or containers actually exist. Safe by construction
for the "I genuinely don't know the deployment topology" case: a
single process behaves identically to N processes racing, since the
lock decides leadership either way.

The renewal check (via a Lua script, executed atomically) is the part
that's easy to get subtly wrong: a naive "if I think I'm leader, just
call EXPIRE" has a race window where the lock could have already
expired and been claimed by someone else between the check and the
EXPIRE call. Using GET+compare+EXPIRE atomically in one server-side
script closes that window.
"""
import time
import uuid

LOCK_KEY = "alpaca_stream_leader_lock"
LOCK_TTL_SECONDS = 15
RENEW_INTERVAL_SECONDS = 5  # comfortable margin under the TTL

# Atomic: only renew if the lock's current value is still ours.
_RENEW_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
"""

# Atomic: only release if the lock's current value is still ours
# (never delete a lock some other instance has since acquired).
_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class LeaderLock:
    def __init__(self, redis_client, instance_id=None,
                 lock_key=LOCK_KEY, ttl_seconds=LOCK_TTL_SECONDS):
        self.redis = redis_client
        self.instance_id = instance_id or str(uuid.uuid4())
        self.lock_key = lock_key
        self.ttl_seconds = ttl_seconds
        self._is_leader = False
        self._renew_script = self.redis.register_script(_RENEW_SCRIPT)
        self._release_script = self.redis.register_script(_RELEASE_SCRIPT)

    def try_acquire_or_renew(self) -> bool:
        """
        Returns True if this instance is (now, or still) the leader.
        Safe to call repeatedly from a loop -- acquires if unclaimed,
        renews if we already hold it, does nothing (returns False) if
        someone else holds it.
        """
        # NX+EX: only succeeds if the key doesn't exist yet.
        acquired = self.redis.set(self.lock_key, self.instance_id,
                                   nx=True, ex=self.ttl_seconds)
        if acquired:
            self._is_leader = True
            return True

        # Someone (possibly us) already holds it -- try to renew,
        # atomically checking it's still genuinely our own lock first.
        renewed = self._renew_script(keys=[self.lock_key],
                                      args=[self.instance_id, self.ttl_seconds])
        self._is_leader = bool(renewed)
        return self._is_leader

    def release(self):
        """Only releases if we still genuinely hold it -- never deletes
        a lock some other instance has since legitimately acquired."""
        self._release_script(keys=[self.lock_key], args=[self.instance_id])
        self._is_leader = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader
