import secrets
import string

BASE62_CHARS = string.ascii_letters + string.digits
SHORT_CODE_LENGTH = 7


def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """Random Base62 string. 62^7 ≈ 3.5T combinations."""
    return "".join(secrets.choice(BASE62_CHARS) for _ in range(length))
