# barricador-python-client

[![PyPI](https://img.shields.io/pypi/v/barricador-client?label=PyPI)](https://pypi.org/project/barricador-client/)

Production-grade **Python Server SDK** for Barricador. Standard library only (no third-party runtime
deps), Python 3.9+.

## Install

```bash
pip install barricador-client
```

## Guarantees

- **Zero-latency evaluation.** `is_enabled(...)` is a synchronous in-memory dict lookup — no I/O.
- **Local evaluation** that mirrors the backend engine exactly (incl. MurmurHash3 bucketing —
  verified byte-identical with the Java SDK).
- **Real-time sync** over SSE on a daemon thread, with exponential backoff + jitter on disconnect and
  graceful fallback to cached state.
- **Async telemetry** flushed every 30s; never blocks the host application.
- **Two tracks:** synchronous `BarricadorClient` and asyncio-native `AsyncBarricadorClient`.

## Sync usage

```python
from barricador import BarricadorClient, UserContext

with BarricadorClient("sdk-srv-...", base_url="https://app.barricador.com") as client:
    user = UserContext("user-123", email="user@enterprise.com", custom={"plan": "pro"})
    if client.is_enabled("premium-pricing", user):
        ...
    theme = client.string_variation("homepage-theme", user, "control")
```

## Async usage

```python
from barricador import AsyncBarricadorClient, UserContext

async with await AsyncBarricadorClient.create("sdk-srv-...") as client:
    user = UserContext("user-123", country="US")
    enabled = client.is_enabled("beta-feature", user)   # evaluation is sync (in-memory)
```

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Layout

| Module | Responsibility |
|--------|----------------|
| `barricador.client` / `barricador.aio` | Sync / async clients |
| `barricador.evaluation` | Local targeting engine |
| `barricador.store` | Thread-safe `FlagStore` + `MetricsBuffer` |
| `barricador.transport` | urllib bootstrap/flush + SSE parsing |
| `barricador.murmur` | MurmurHash3 (cross-SDK consistent) |
| `barricador.context` | `UserContext` |
