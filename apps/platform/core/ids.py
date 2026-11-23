"""Unique IDs for every table.

We use UUID version 7. The first part of the ID is the time it was made, so new
rows sort after old ones and database indexes stay compact. The rest is random,
so an ID cannot be guessed or counted.
"""

import os
import threading
import time
import uuid
from collections.abc import Callable

_COUNTER_MAX = (1 << 42) - 1

_lock = threading.Lock()
_last_timestamp_ms = 0
_last_counter = 0


def _now_ms() -> int:
    """The current time in whole milliseconds since 1 January 1970 (UTC)."""
    return time.time_ns() // 1_000_000


def _random_counter_start() -> int:
    """A random 41-bit number. The 42nd bit starts at 0, which leaves room to count up."""
    return int.from_bytes(os.urandom(6), "big") & ((1 << 41) - 1)


def _fallback_uuid7() -> uuid.UUID:
    """Build a UUID version 7 (RFC 9562) on Python versions that lack ``uuid.uuid7``.

    The 128 bits, left to right:
    48 bits of time in milliseconds, 4 bits for the version, 12 bits of counter,
    2 bits for the variant, 30 more bits of counter, 32 random bits.

    The counter makes IDs from the same millisecond come out in order. If the
    computer's clock jumps backwards, we keep the last time and count up.
    """
    global _last_timestamp_ms, _last_counter

    with _lock:
        timestamp_ms = _now_ms()
        if timestamp_ms > _last_timestamp_ms:
            counter = _random_counter_start()
        else:
            timestamp_ms = _last_timestamp_ms
            counter = _last_counter + 1
            if counter > _COUNTER_MAX:
                timestamp_ms += 1
                counter = _random_counter_start()
        _last_timestamp_ms = timestamp_ms
        _last_counter = counter

    value = (timestamp_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= (counter >> 30) << 64
    value |= 0b10 << 62
    value |= (counter & 0x3FFF_FFFF) << 32
    value |= int.from_bytes(os.urandom(4), "big")
    return uuid.UUID(int=value)


# Python 3.14 and newer ship uuid.uuid7. Older versions use our own builder.
_stdlib_uuid7: Callable[[], uuid.UUID] | None = getattr(uuid, "uuid7", None)


def new_uuid() -> uuid.UUID:
    """Return a new UUID version 7. Every model uses this for its ``id``."""
    if _stdlib_uuid7 is not None:
        return _stdlib_uuid7()
    return _fallback_uuid7()
