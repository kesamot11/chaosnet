"""Retry budget for one link, kept by the caller (#138, design by Tomáš 2026-11-01).

A token bucket shared by every call on the link: each first attempt adds `ratio` of a
token (0.1), each retry takes a whole one, so retries stay around a tenth of the
traffic. In calm times the bucket fills up to `cap` and a rare failure is retried as
before; in a storm it empties at once and the retries stop. It starts full, so a
failure right after a start is retried; the cost, at most `cap` extra retries.
"""


class RetryBudget:
    def __init__(self, ratio: float = 0.1, cap: float = 10.0) -> None:
        self.ratio = ratio
        self.cap = cap
        self.tokens = cap  # starts full

    def first_attempt(self) -> None:
        """A first attempt on the link earns `ratio` of a token, up to `cap`."""
        self.tokens = min(self.cap, self.tokens + self.ratio)

    def try_retry(self) -> bool:
        """True and one token less if a retry is affordable; False if not."""
        # 1e-9: ten times 0.1 is 0.9999999999999999 in floats, which must still pay
        if self.tokens < 1.0 - 1e-9:
            return False
        self.tokens = self.tokens - 1.0
        return True
