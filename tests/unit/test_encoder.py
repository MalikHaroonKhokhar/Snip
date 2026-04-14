import pytest

from app.utils.encoder import BASE62_CHARS, SHORT_CODE_LENGTH, generate_short_code


pytestmark = pytest.mark.unit


def test_default_length_is_seven():
    assert len(generate_short_code()) == SHORT_CODE_LENGTH == 7


def test_custom_length():
    assert len(generate_short_code(length=10)) == 10


def test_only_base62_charset():
    allowed = set(BASE62_CHARS)
    for _ in range(50):
        code = generate_short_code()
        assert set(code).issubset(allowed)


def test_generates_distinct_values():
    codes = {generate_short_code() for _ in range(100)}
    # 62^7 space — collisions in 100 draws are effectively impossible
    assert len(codes) == 100
