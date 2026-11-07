"""Tiny in-memory TTL cache so page reloads don't hammer the APIs."""
from __future__ import annotations

import functools
import time

_store: dict = {}


def cached(ttl: float):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args):
            key = (fn.__qualname__, args)
            hit = _store.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
            value = fn(*args)
            _store[key] = (time.time(), value)
            return value

        return wrapper

    return deco


def clear() -> None:
    _store.clear()
