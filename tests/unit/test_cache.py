from __future__ import annotations

import pytest

from app.core.cache import cache_key


def test_cache_key_rounding_stable():
    k1 = cache_key(1.234567, 2.345678, 3.456789, 4.567891)
    k2 = cache_key(1.23456, 2.34568, 3.45679, 4.56789)
    assert k1 == k2


def test_cache_key_changes_when_route_changes():
    k1 = cache_key(1.0, 2.0, 3.0, 4.0)
    k2 = cache_key(1.0, 2.0, 3.0, 4.0002)
    assert k1 != k2

