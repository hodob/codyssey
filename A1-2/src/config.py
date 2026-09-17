"""dotenv + YAML + 표준 string.Template로 설정을 읽는다."""

from __future__ import annotations

import math
import os
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

import yaml
from dotenv import load_dotenv

from .models import AppConfig, ConfigError, LLMConfig, PlacesConfig


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ConfigError('config.yml에 중복된 설정 항목이 있습니다.')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _mapping(value, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ConfigError(f'{label}의 필수 항목 또는 알 수 없는 항목을 확인하세요.')
    return value


def _string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f'{label}은 비어 있지 않은 문자열이어야 합니다.')
    return value.strip()


def _positive(value, label: str, integer: bool = False):
    allowed = (int,) if integer else (int, float)
    if type(value) not in allowed or not math.isfinite(value) or value <= 0:
        raise ConfigError(f'{label}은 양수' + (' 정수' if integer else '') + '여야 합니다.')
    return value


def _base_url(value, label: str) -> str:
    value = _string(value, label)
    try:
        url = urlsplit(value)
        valid = (url.scheme == 'https' and url.hostname and not url.username and not url.password
                 and not url.query and not url.fragment and not any(c.isspace() for c in value))
        url.port
    except ValueError:
        valid = False
    if not valid:
        raise ConfigError(f'{label}에 올바른 HTTPS API 주소를 설정하세요.')
    return value.rstrip('/')


def _key_reference(value, label: str) -> str:
    source = _string(value, label)
    parts = list(Template.pattern.finditer(source))
    if len(parts) != 1 or parts[0].span() != (0, len(source)) or not parts[0].group('braced'):
        raise ConfigError(f'{label}에는 ${{환경변수명}} 참조를 사용하세요.')
    name = parts[0].group('braced')
    try:
        value = Template(source).substitute(os.environ)
    except (KeyError, ValueError) as exc:
        raise ConfigError(f'{name} 환경변수를 .env 또는 현재 터미널에 설정하세요.') from exc
    if not value.strip():
        raise ConfigError(f'{name} 환경변수가 비어 있습니다. .env 또는 현재 환경변수를 확인하세요.')
    if any(c.isspace() for c in value) or not value.isascii():
        raise ConfigError(f'{name}에 공백 없는 API 키를 설정하세요.')
    return value


def load_config(project_root: Path) -> AppConfig:
    project_root = project_root.resolve()
    try:
        load_dotenv(project_root / '.env', override=False, encoding='utf-8')
        with (project_root / 'config.yml').open(encoding='utf-8') as handle:
            raw = yaml.load(handle, Loader=UniqueKeyLoader)
        raw = _mapping(raw, {'llm', 'places'}, 'config.yml')
        llm = _mapping(raw['llm'], {'base_url', 'api_key', 'model', 'max_tokens', 'timeout_seconds'}, 'llm')
        places = _mapping(raw['places'], {'provider', 'base_url', 'api_key', 'category_group_code', 'limit', 'timeout_seconds'}, 'places')
        limit = _positive(places['limit'], 'places.limit', integer=True)
        if limit > 15:
            raise ConfigError('places.limit은 1~15여야 합니다.')
        if places['provider'] != 'kakao' or places['category_group_code'] != 'FD6':
            raise ConfigError('현재 장소 검색은 provider: kakao, category_group_code: FD6를 사용합니다.')
        return AppConfig(
            project_root=project_root,
            llm=LLMConfig(
                base_url=_base_url(llm['base_url'], 'llm.base_url'),
                api_key=_key_reference(llm['api_key'], 'llm.api_key'),
                model=_string(llm['model'], 'llm.model'),
                max_tokens=_positive(llm['max_tokens'], 'llm.max_tokens', integer=True),
                timeout_seconds=_positive(llm['timeout_seconds'], 'llm.timeout_seconds'),
            ),
            places=PlacesConfig(
                base_url=_base_url(places['base_url'], 'places.base_url'),
                api_key=_key_reference(places['api_key'], 'places.api_key'),
                limit=limit,
                timeout_seconds=_positive(places['timeout_seconds'], 'places.timeout_seconds'),
            ),
        )
    except ConfigError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError, TypeError, ValueError) as exc:
        raise ConfigError('config.yml과 .env의 파일 접근 권한, UTF-8 인코딩, YAML 문법을 확인하세요.') from exc
