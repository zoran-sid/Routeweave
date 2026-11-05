"""Small version-keyed LRU cache for read-only query results.

The cache is deliberately local and synchronous: it demonstrates the
invalidation rule (a new release invalidates every entry) without pretending to
be a distributed cache. A production deployment would key by the same five
version strings in Redis or a shared store.
"""
from collections import OrderedDict
import copy
import json


def version_key(versions):
    return json.dumps(versions, sort_keys=True, separators=(",", ":"))


def query_key(kind, payload):
    return kind + ":" + json.dumps(payload, sort_keys=True, separators=(",", ":"))


class QueryCache:
    def __init__(self, capacity=256):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._data = OrderedDict()
        self._version = None
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0

    def bind(self, versions):
        """Clear the cache when the release version changes."""
        marker = version_key(versions)
        if self._version is not None and marker != self._version:
            self.clear()
            self.invalidations += 1
        self._version = marker

    def get(self, key):
        if key not in self._data:
            self.misses += 1
            return None
        value = self._data.pop(key)
        self._data[key] = value
        self.hits += 1
        return copy.deepcopy(value)

    def put(self, key, value):
        if key in self._data:
            self._data.pop(key)
        self._data[key] = copy.deepcopy(value)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)
            self.evictions += 1

    def get_or_compute(self, key, versions, compute):
        self.bind(versions)
        hit = self.get(key)
        if hit is not None:
            return hit
        value = compute()
        self.put(key, value)
        return value

    def clear(self):
        self._data.clear()

    def reset_stats(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0

    def stats(self):
        total = self.hits + self.misses
        return {
            "capacity": self.capacity,
            "entries": len(self._data),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "invalidations": self.invalidations,
            "hit_rate": (self.hits / total) if total else 0.0,
        }
