"""Small in-memory limiter for failed logins (per phone number and per client IP).

Good for a single app instance. With several instances, move this to Redis.
"""
import time
from collections import defaultdict, deque
from threading import Lock

# Per phone number: stops password guessing on one account.
# Per IP: much looser, since many users can share one IP behind a proxy or mobile carrier NAT.
LIMITS = {"phone": 5, "ip": 30}
WINDOW_SECONDS = 15 * 60

_failures: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def _prune(q: deque, now: float) -> None:
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()


def retry_after(*keys: str) -> int:
    """Seconds until the caller may try again (0 = allowed)."""
    now = time.monotonic()
    wait = 0
    with _lock:
        for key in keys:
            q = _failures.get(key)
            if not q:
                continue
            _prune(q, now)
            if len(q) >= LIMITS.get(key.split(":", 1)[0], 5):
                wait = max(wait, int(WINDOW_SECONDS - (now - q[0])) + 1)
    return wait


def record_failure(*keys: str) -> None:
    now = time.monotonic()
    with _lock:
        for key in keys:
            _failures[key].append(now)


def reset(*keys: str) -> None:
    with _lock:
        for key in keys or list(_failures):
            _failures.pop(key, None)
