"""Synchronous Barricator server SDK client."""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Optional

from . import evaluation
from .context import UserContext
from .store import FlagStore, MetricsBuffer
from .transport import Transport

logger = logging.getLogger("barricator")


class BarricatorClient:
    """Server SDK client.

    Evaluation methods are synchronous, in-memory, and never perform I/O or raise. A daemon thread
    keeps the cache fresh via SSE (with exponential backoff on disconnect), and another daemon thread
    flushes aggregated telemetry every ``metrics_flush_interval`` seconds. Use as a context manager
    or call :meth:`close`.
    """

    def __init__(
        self,
        sdk_key: str,
        base_url: str = "https://app.barricator.com",
        *,
        streaming_enabled: bool = True,
        metrics_enabled: bool = True,
        metrics_flush_interval: float = 30.0,
        bootstrap_timeout: float = 5.0,
        initial_reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
    ) -> None:
        if not sdk_key:
            raise ValueError("sdk_key is required")
        self._transport = Transport(base_url, sdk_key)
        self._store = FlagStore()
        self._metrics = MetricsBuffer()
        self._metrics_enabled = metrics_enabled
        self._metrics_flush_interval = metrics_flush_interval
        self._bootstrap_timeout = bootstrap_timeout
        self._initial_reconnect_delay = initial_reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay

        self._closed = threading.Event()
        self._sse_conn = None  # type: Optional[Any]

        self._safe_bootstrap()
        if streaming_enabled:
            self._sse_thread = threading.Thread(target=self._stream_loop, name="barricator-sse", daemon=True)
            self._sse_thread.start()
        if metrics_enabled:
            self._flush_thread = threading.Thread(target=self._flush_loop, name="barricator-metrics", daemon=True)
            self._flush_thread.start()

    # --- public evaluation API ---

    def is_enabled(self, flag_key: str, user: UserContext, default: bool = False) -> bool:
        value = self._evaluate(flag_key, user, default).value
        return value if isinstance(value, bool) else default

    def bool_variation(self, flag_key: str, user: UserContext, default: bool) -> bool:
        return self.is_enabled(flag_key, user, default)

    def string_variation(self, flag_key: str, user: UserContext, default: str) -> str:
        value = self._evaluate(flag_key, user, default).value
        return default if value is None else str(value)

    def number_variation(self, flag_key: str, user: UserContext, default: float) -> float:
        value = self._evaluate(flag_key, user, default).value
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def json_variation(self, flag_key: str, user: UserContext, default: Any) -> Any:
        return self._evaluate(flag_key, user, default).value

    @property
    def initialized(self) -> bool:
        return self._store.initialized

    def _evaluate(self, flag_key: str, user: UserContext, fallback: Any) -> evaluation.EvaluationResult:
        flag = self._store.get(flag_key)
        result = evaluation.evaluate(flag, user, fallback)
        if self._metrics_enabled:
            self._metrics.record(flag_key, result.variation_id, result.is_defaulted)
        return result

    # --- lifecycle ---

    def _safe_bootstrap(self) -> None:
        try:
            resp = self._transport.bootstrap(timeout=self._bootstrap_timeout)
            flags = {f["key"]: f for f in (resp.get("flags") or [])}
            self._store.replace_all(flags, int(resp.get("rulesVersion", 0)))
            logger.debug("Barricator bootstrap: %d flags (v%s)", len(flags), resp.get("rulesVersion"))
        except Exception as exc:  # noqa: BLE001 - never fatal
            logger.warning("Barricator bootstrap failed (%s); serving cached/defaults", exc)

    def _stream_loop(self) -> None:
        delay = self._initial_reconnect_delay
        while not self._closed.is_set():
            try:
                conn = self._transport.open_stream()
                self._sse_conn = conn
                # Reconnected: re-bootstrap to recover any deltas missed while offline.
                self._safe_bootstrap()
                delay = self._initial_reconnect_delay
                for evt in conn.events():
                    if self._closed.is_set():
                        break
                    self._apply_event(evt)
            except Exception as exc:  # noqa: BLE001
                if self._closed.is_set():
                    break
                logger.debug("SSE disconnected (%s); reconnecting in %.1fs", exc, delay)
                self._sleep_with_jitter(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

    def _apply_event(self, evt: dict) -> None:
        if evt.get("event") != "flag-change":
            return
        try:
            import json

            payload = json.loads(evt["data"])
            if payload.get("type") == "DELETE":
                self._store.remove(payload.get("flagKey"))
            else:
                flag = payload.get("flag")
                if flag:
                    self._store.upsert(flag)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to apply SSE delta: %s", exc)

    def _flush_loop(self) -> None:
        while not self._closed.wait(self._metrics_flush_interval):
            self.flush()

    def flush(self) -> None:
        try:
            events = self._metrics.drain()
            if events:
                self._transport.flush_metrics(events)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Metrics flush failed: %s", exc)

    def _sleep_with_jitter(self, base: float) -> None:
        self._closed.wait(base + random.uniform(0, base / 2))

    def close(self) -> None:
        self._closed.set()
        if self._sse_conn is not None:
            self._sse_conn.close()
        self.flush()

    def __enter__(self) -> "BarricatorClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
