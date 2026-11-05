"""Estimated cost per model, in US dollars per million tokens.

Defaults are Anthropic's first-party API list prices as published in its model documentation (cached 2026-10-06).
Cache reads use the published rate where one is given, otherwise 10% of input; cache writes use 125% of input (the
five-minute cache write rate). Prices change and differ by platform and plan: override any of them with a JSON
file (the `pricing` setting) shaped like DEFAULT_PRICES. A model with no matching entry is reported as unpriced,
never guessed.
Matching is by prefix after lower-casing, so "claude-opus-5-5-20260101" matches "claude-opus-5-5".
"""

from __future__ import annotations

import hashlib
import json
import os

# model prefix: [input, output, cache_read, cache_write]
DEFAULT_PRICES: dict[str, list[float]] = {
    "claude-fable-5-1": [10.00, 50.00, 0.25, 12.50],
    "claude-mythos-5-1": [10.00, 50.00, 1.00, 12.50],
    "claude-fable-5": [10.00, 50.00, 1.00, 12.50],
    "claude-opus-5-5": [4.00, 20.00, 0.20, 5.00],
    "claude-opus-5": [5.00, 25.00, 0.50, 6.25],
    "claude-opus-4-8": [5.00, 25.00, 0.50, 6.25],
    "claude-opus-4-7": [5.00, 25.00, 0.50, 6.25],
    "claude-opus-4-6": [5.00, 25.00, 0.50, 6.25],
    "claude-sonnet-5-5": [2.00, 10.00, 0.20, 2.50],
    "claude-sonnet-5": [2.00, 10.00, 0.20, 2.50],
    "claude-sonnet-4-6": [3.00, 15.00, 0.30, 3.75],
    "claude-haiku-5-5": [0.10, 0.50, 0.01, 0.125],
    "claude-haiku-4-5": [1.00, 5.00, 0.10, 1.25],
}


class Pricing:
    def __init__(self, path: str | None = None):
        self.prices = dict(DEFAULT_PRICES)
        if path:
            with open(os.path.expanduser(path), encoding="utf-8") as fh:
                self.prices.update({k.lower(): v for k, v in json.load(fh).items()})
        # longest prefix first, so "claude-opus-5-5" wins over "claude-opus-5"
        self._keys = sorted(self.prices, key=len, reverse=True)
        # changes when any price changes, so the syncer re-prices files it has already read
        self.fingerprint = hashlib.md5(json.dumps(self.prices, sort_keys=True).encode()).hexdigest()[:12]

    def rates(self, model: str) -> list[float] | None:
        m = (model or "").lower()
        for k in self._keys:
            if m.startswith(k):
                return self.prices[k]
        return None

    def cost(self, model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float | None:
        r = self.rates(model)
        if r is None:
            return None
        return (inp * r[0] + out * r[1] + cache_read * r[2] + cache_write * r[3]) / 1_000_000

    def cache_savings(self, model: str, cache_read: int) -> float:
        """What the cached input would have cost at the full input price, minus what it did cost."""
        r = self.rates(model)
        return 0.0 if r is None else cache_read * (r[0] - r[2]) / 1_000_000
