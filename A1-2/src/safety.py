"""출력 경계에서 비밀값과 터미널 제어문자를 제거한다."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit


_ANSI = re.compile(r'\x1b\][\s\S]*?(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')


def clean_text(value: str) -> str:
    text = _ANSI.sub('', value)
    return ''.join(c for c in text if c in '\n\t' or unicodedata.category(c) not in ('Cc', 'Cf'))


def safe_url(value: str | None) -> str | None:
    if not value or any(c.isspace() or unicodedata.category(c) in ('Cc', 'Cf') for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


@dataclass(frozen=True)
class SecretFilter:
    secrets: tuple[str, ...] = field(default=(), repr=False)

    def text(self, value: str) -> str:
        for secret in sorted((s for s in self.secrets if s), key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        return clean_text(value)

    def data(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.data(item) for item in value]
        if isinstance(value, dict):
            return {key: self.data(item) for key, item in value.items()}
        return value
