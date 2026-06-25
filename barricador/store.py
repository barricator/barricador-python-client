"""Thread-safe in-memory flag store and metrics buffer."""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple


class FlagStore:
    """Holds the environment ruleset. Reads are guarded by an ``RLock`` for consistency under
    concurrent SSE updates; lookups are O(1) dict access."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._flags: Dict[str, Dict[str, Any]] = {}
        self._rules_version = 0
        self._initialized = False

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._flags.get(key)

    @property
    def initialized(self) -> bool:
        with self._lock:
            return self._initialized

    @property
    def rules_version(self) -> int:
        with self._lock:
            return self._rules_version

    def replace_all(self, flags: Dict[str, Dict[str, Any]], version: int) -> None:
        with self._lock:
            self._flags = dict(flags)
            self._rules_version = version
            self._initialized = True

    def upsert(self, flag: Dict[str, Any]) -> None:
        if not flag or not flag.get("key"):
            return
        with self._lock:
            self._flags[flag["key"]] = flag
            self._rules_version = max(self._rules_version, int(flag.get("version", 0)))
            self._initialized = True

    def remove(self, key: Optional[str]) -> None:
        if not key:
            return
        with self._lock:
            self._flags.pop(key, None)


class MetricsBuffer:
    """Lock-guarded aggregation of evaluation counts keyed by (flag, variation, defaulted)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: Dict[Tuple[str, Optional[str], bool], int] = {}

    def record(self, flag_key: str, variation_id: Optional[str], defaulted: bool) -> None:
        key = (flag_key, variation_id, defaulted)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def drain(self) -> List[Dict[str, Any]]:
        with self._lock:
            snapshot = self._counts
            self._counts = {}
        return [
            {
                "flagKey": flag_key,
                "variationId": variation_id,
                "count": count,
                "defaulted": defaulted,
            }
            for (flag_key, variation_id, defaulted), count in snapshot.items()
            if count > 0
        ]
