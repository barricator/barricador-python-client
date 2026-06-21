# barricator-python-client

[![PyPI](https://img.shields.io/pypi/v/barricator-client?label=PyPI)](https://pypi.org/project/barricator-client/)

Production-grade **Python Server SDK** for Barricator. Standard library only (no third-party runtime
deps), Python 3.9+.

## Install

```bash
pip install barricator-client
```

## Guarantees

- **Zero-latency evaluation.** `is_enabled(...)` is a synchronous in-memory dict lookup — no I/O.
- **Local evaluation** that mirrors the backend engine exactly (incl. MurmurHash3 bucketing —
  verified byte-identical with the Java SDK).
- **Real-time sync** over SSE on a daemon thread, with exponential backoff + jitter on disconnect and
  graceful fallback to cached state.
- **Async telemetry** flushed every 30s; never blocks the host application.
- **Two tracks:** synchronous `BarricatorClient` and asyncio-native `AsyncBarricatorClient`.

## Sync usage

```python
from barricator import BarricatorClient, UserContext

with BarricatorClient("sdk-srv-...", base_url="https://app.barricator.io") as client:
    user = UserContext("user-123", email="user@enterprise.com", custom={"plan": "pro"})
    if client.is_enabled("premium-pricing", user):
        ...
    theme = client.string_variation("homepage-theme", user, "control")
```

## Async usage

```python
from barricator import AsyncBarricatorClient, UserContext

async with await AsyncBarricatorClient.create("sdk-srv-...") as client:
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
| `barricator.client` / `barricator.aio` | Sync / async clients |
| `barricator.evaluation` | Local targeting engine |
| `barricator.store` | Thread-safe `FlagStore` + `MetricsBuffer` |
| `barricator.transport` | urllib bootstrap/flush + SSE parsing |
| `barricator.murmur` | MurmurHash3 (cross-SDK consistent) |
| `barricator.context` | `UserContext` |
