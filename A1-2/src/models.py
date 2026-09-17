"""API와 화면 사이에서 사용하는 공통 데이터 계약."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ErrorType(str, Enum):
    CONFIG_ERROR = 'CONFIG_ERROR'
    AUTH_ERROR = 'AUTH_ERROR'
    QUOTA_ERROR = 'QUOTA_ERROR'
    TIMEOUT = 'TIMEOUT'
    NETWORK_ERROR = 'NETWORK_ERROR'
    REQUEST_ERROR = 'REQUEST_ERROR'
    INPUT_TOO_LARGE = 'INPUT_TOO_LARGE'
    REDIRECT_ERROR = 'REDIRECT_ERROR'
    HTTP_ERROR = 'HTTP_ERROR'
    RESPONSE_ERROR = 'RESPONSE_ERROR'
    REFUSAL = 'REFUSAL'
    TRUNCATED = 'TRUNCATED'
    INCOMPLETE = 'INCOMPLETE'
    EMPTY_RESPONSE = 'EMPTY_RESPONSE'
    EMPTY_REQUIRED_VALUE = 'EMPTY_REQUIRED_VALUE'
    INVALID_FIELD_VALUE = 'INVALID_FIELD_VALUE'
    CITY_ERROR = 'CITY_ERROR'
    EMPTY_RESULT = 'EMPTY_RESULT'
    PLACE_DATA_WARNING = 'PLACE_DATA_WARNING'
    REPORT_FORMAT_ERROR = 'REPORT_FORMAT_ERROR'
    CACHE_ERROR = 'CACHE_ERROR'
    SAVE_ERROR = 'SAVE_ERROR'
    INTERRUPTED = 'INTERRUPTED'


class AppError(Exception):
    """외부 응답 원문 대신 안전하게 작성한 사용자용 오류."""

    def __init__(self, kind: ErrorType | str, message: str, http_status: int | None = None, details=None):
        super().__init__(message)
        self.kind = kind.value if isinstance(kind, ErrorType) else str(kind)
        self.http_status = http_status
        self.details = details


class ConfigError(AppError):
    def __init__(self, message: str):
        super().__init__(ErrorType.CONFIG_ERROR, message)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str = 'openai/gpt-oss-120b'
    max_tokens: int = 4096
    timeout_seconds: float = 120


@dataclass(frozen=True)
class PlacesConfig:
    base_url: str
    api_key: str = field(repr=False)
    provider: str = 'kakao'
    category_group_code: str = 'FD6'
    limit: int = 5
    timeout_seconds: float = 30


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    llm: LLMConfig
    places: PlacesConfig


RECOMMENDATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'recommended_city': {'type': 'string'},
        'weather': {'type': 'string'},
        'events': {'type': 'array', 'items': {'type': 'string'}},
        'reason': {'type': 'string'},
    },
    'required': ['recommended_city', 'weather', 'events', 'reason'],
    'additionalProperties': False,
}
RECOMMENDATION_FORMAT = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'travel_recommendation',
        'strict': True,
        'schema': RECOMMENDATION_SCHEMA,
    },
}


@dataclass
class Recommendation:
    recommended_city: str
    weather: str
    events: list[str]
    reason: str


def parse_recommendation(text: str) -> Recommendation:
    """Provider가 구조를 보장한 JSON을 파싱하고 실제 사용 가능한 값인지 검증한다."""
    try:
        data = json.loads(text)
        result = Recommendation(
            recommended_city=data['recommended_city'].strip(),
            weather=data['weather'].strip(),
            events=[event.strip() for event in data['events']],
            reason=data['reason'].strip(),
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise AppError(ErrorType.RESPONSE_ERROR, '구조화 응답을 추천 데이터로 읽을 수 없습니다.') from exc

    if not result.recommended_city or not result.weather or not result.reason:
        raise AppError(ErrorType.EMPTY_REQUIRED_VALUE, '추천 도시·날씨·추천 이유는 비어 있을 수 없습니다.')
    if not 1 <= len(result.events) <= 3:
        raise AppError(ErrorType.INVALID_FIELD_VALUE, '행사 후보는 1~3개여야 합니다.')
    if not all(result.events):
        raise AppError(ErrorType.EMPTY_REQUIRED_VALUE, '행사 후보에는 빈 문자열을 사용할 수 없습니다.')
    return result


@dataclass
class ErrorRecord:
    step: str
    type: str
    message: str
    attempt: int = 1
    http_status: int | None = None


@dataclass
class Place:
    name: str
    address: str
    category: str | None = None
    url: str | None = None
    lng: float | None = None
    lat: float | None = None


@dataclass
class PlaceSearch:
    provider: str
    query: str
    status: str
    restaurants: list[Place] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)


@dataclass
class Completion:
    content: str
    finish_reason: str
    refusal: bool = False
    usage: dict[str, int] | None = None


def completed_text(completion: Completion) -> str:
    if completion.refusal or completion.finish_reason == 'content_filter':
        raise AppError(ErrorType.REFUSAL, '모델이 요청에 대한 응답을 거부했습니다.')
    if completion.finish_reason == 'length':
        raise AppError(ErrorType.TRUNCATED, '토큰 한도로 응답이 중단되었습니다.')
    if completion.finish_reason != 'stop':
        raise AppError(ErrorType.INCOMPLETE, '모델 응답이 정상적으로 완료되지 않았습니다.')
    if not completion.content.strip():
        raise AppError(ErrorType.EMPTY_RESPONSE, '모델 응답 내용이 비어 있습니다.')
    return completion.content


@dataclass
class RunResult:
    requested_date: str
    model: str
    status: str = 'in_progress'
    recommendation: Recommendation | None = None
    place_search: dict[str, str] | None = None
    restaurants: list[Place] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    report_file: str | None = None

    @classmethod
    def start(cls, requested_date: str, model: str) -> 'RunResult':
        return cls(requested_date=requested_date, model=model)

    def to_raw_dict(self) -> dict[str, Any]:
        if self.recommendation is None:
            raise AppError(ErrorType.SAVE_ERROR, '추천 결과가 없어 원본 JSON을 저장할 수 없습니다.')
        return {
            'date': self.requested_date,
            'recommendation': asdict(self.recommendation),
            'places': [asdict(place) for place in self.restaurants],
            'errors': [asdict(error) for error in self.errors],
        }
