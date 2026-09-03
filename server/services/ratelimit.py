import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-memory sliding-window rate limiter.

    Thread-safe enough for a single process. Swap for a Redis-backed limiter if the
    API is scaled to multiple processes/workers (see PLAN.md).
    """

    def __init__(self):
        self._buckets = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        """Return True if a request under `key` is within `limit` per `window`."""
        now = time.monotonic()
        q = self._buckets[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def reset(self, key: str = None):
        if key is None:
            self._buckets.clear()
        else:
            self._buckets.pop(key, None)


# Default limits
MSG_PER_VISITOR = 5
MSG_VISITOR_WINDOW = 60.0
MSG_PER_IP = 20
MSG_IP_WINDOW = 10.0
MSG_PER_SITE = 120
MSG_SITE_WINDOW = 3600.0
