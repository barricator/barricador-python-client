"""MurmurHash3 (x86 32-bit).

Bit-for-bit compatible with the Java/backend implementation so a user buckets into the same
variation across every SDK. Bucketing hashes ``"<flag_key>.<salt>.<bucket_by_value>"``.
"""

_C1 = 0xCC9E2D51
_C2 = 0x1B873593
_MASK = 0xFFFFFFFF


def _rotl32(x: int, r: int) -> int:
    x &= _MASK
    return ((x << r) | (x >> (32 - r))) & _MASK


def _fmix(h: int) -> int:
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK
    h ^= h >> 16
    return h & _MASK


def hash32(data: bytes, seed: int = 0) -> int:
    """Return the signed 32-bit MurmurHash3 (matching Java's ``int`` result)."""
    h1 = seed & _MASK
    length = len(data)
    rounded_end = length & 0xFFFFFFFC

    for i in range(0, rounded_end, 4):
        k1 = (data[i] & 0xFF) \
            | ((data[i + 1] & 0xFF) << 8) \
            | ((data[i + 2] & 0xFF) << 16) \
            | ((data[i + 3] & 0xFF) << 24)
        k1 = (k1 * _C1) & _MASK
        k1 = _rotl32(k1, 15)
        k1 = (k1 * _C2) & _MASK
        h1 ^= k1
        h1 = _rotl32(h1, 13)
        h1 = (h1 * 5 + 0xE6546B64) & _MASK

    k1 = 0
    tail = length & 0x03
    if tail == 3:
        k1 = (data[rounded_end + 2] & 0xFF) << 16
    if tail >= 2:
        k1 |= (data[rounded_end + 1] & 0xFF) << 8
    if tail >= 1:
        k1 |= (data[rounded_end] & 0xFF)
        k1 = (k1 * _C1) & _MASK
        k1 = _rotl32(k1, 15)
        k1 = (k1 * _C2) & _MASK
        h1 ^= k1

    h1 ^= length
    h1 = _fmix(h1)

    # Convert to signed 32-bit so that ``% n`` matches Java's Math.floorMod(signedInt, n).
    if h1 >= 0x80000000:
        h1 -= 0x100000000
    return h1


def _unsigned_hash(flag_key: str, salt: str, bucket_by: str) -> int:
    composite = f"{flag_key}.{salt or ''}.{bucket_by}"
    return hash32(composite.encode("utf-8"), 0)


def bucket_0_to_99(flag_key: str, salt: str, bucket_by: str) -> int:
    """Deterministic bucket in ``[0, 100)``."""
    return _unsigned_hash(flag_key, salt, bucket_by) % 100


def bucket_100k(flag_key: str, salt: str, bucket_by: str) -> int:
    """Deterministic bucket in ``[0, 100000)`` for sub-percent rollouts."""
    return _unsigned_hash(flag_key, salt, bucket_by) % 100_000
