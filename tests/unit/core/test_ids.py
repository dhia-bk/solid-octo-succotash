from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.core.ids import (
    build_direct_pair_key,
    build_membership_key,
    build_public_slug,
    normalize_nullable_string_id,
    normalize_string_id,
    slugify,
    stable_hash_key,
)


def test_normalize_string_id_trims_and_collapses_whitespace() -> None:
    assert normalize_string_id("  abc   123  ") == "abc 123"


def test_normalize_string_id_supports_primitives() -> None:
    assert normalize_string_id(123) == "123"
    assert normalize_string_id(True) == "true"
    assert normalize_string_id(Decimal("10.0")) == "10"


def test_normalize_string_id_rejects_none() -> None:
    with pytest.raises(ValidationError):
        normalize_string_id(None)


def test_normalize_nullable_string_id_returns_none_for_blank() -> None:
    assert normalize_nullable_string_id(None) is None
    assert normalize_nullable_string_id("   ") is None


def test_slugify_is_deterministic() -> None:
    assert slugify(" Hello, World! ") == "hello-world"


def test_stable_hash_key_is_deterministic() -> None:
    left = stable_hash_key("user", 123, length=12)
    right = stable_hash_key("user", 123, length=12)

    assert left == right
    assert len(left) == 12


def test_build_membership_key_is_stable() -> None:
    assert build_membership_key(" 42 ", " 7 ") == "membership::42::7"


def test_build_direct_pair_key_is_order_independent() -> None:
    left = build_direct_pair_key("2", "1")
    right = build_direct_pair_key("1", "2")

    assert left == right
    assert left == "direct_pair::1::2"


def test_build_public_slug_prefixes_slugified_value() -> None:
    assert build_public_slug("User", "John Doe") == "user-john-doe"
