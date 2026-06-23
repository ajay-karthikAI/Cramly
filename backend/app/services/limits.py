from __future__ import annotations

from datetime import datetime, timezone
import time


class LimitViolation(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FixedWindowRateLimiter:
    def __init__(self):
        self._windows: dict[str, tuple[int, int]] = {}

    def check(self, key: str, limit: int, window_seconds: int, detail: str) -> None:
        if limit <= 0:
            return

        window_seconds = max(1, window_seconds)
        window_id = int(time.monotonic() // window_seconds)
        current_window, count = self._windows.get(key, (window_id, 0))
        if current_window != window_id:
            current_window = window_id
            count = 0

        if count >= limit:
            raise LimitViolation(429, detail)

        self._windows[key] = (current_window, count + 1)
        self._prune(window_id)

    def reset(self) -> None:
        self._windows.clear()

    def _prune(self, current_window: int) -> None:
        stale = [key for key, (window_id, _) in self._windows.items() if window_id < current_window - 1]
        for key in stale:
            self._windows.pop(key, None)


class DailyQuota:
    def consume(self, repo, user_id: str, category: str, limit: int, detail: str, amount: int = 1) -> None:
        if limit <= 0:
            return

        usage_date = datetime.now(timezone.utc).date().isoformat()
        current = repo.get_daily_usage(user_id, category, usage_date)
        if current + amount > limit:
            raise LimitViolation(429, detail)
        repo.increment_daily_usage(user_id, category, usage_date, amount)


def ensure_max_bytes(size: int, max_bytes: int, detail: str) -> None:
    if max_bytes > 0 and size > max_bytes:
        raise LimitViolation(413, detail)


def ensure_max_chars(text: str, max_chars: int, detail: str) -> None:
    if max_chars > 0 and len(text) > max_chars:
        raise LimitViolation(413, detail)


def ensure_max_count(count: int, max_count: int, detail: str) -> None:
    if max_count > 0 and count > max_count:
        raise LimitViolation(413, detail)
