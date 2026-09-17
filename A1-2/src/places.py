"""장소 공급자 인터페이스와 Kakao 검색 응답 정규화."""

from __future__ import annotations

import math
import re
from typing import Protocol

from .http import request_json
from .models import AppError, ErrorRecord, ErrorType, Place, PlacesConfig, PlaceSearch
from .safety import SecretFilter, safe_url


class PlaceProvider(Protocol):
    def search(self, city: str, limit: int) -> PlaceSearch: ...


_ADMIN_PATTERN = re.compile(
    r'[가-힣]+?(?:특별자치도|특별자치시|특별시|광역시|도|시|군|구)'
)


def normalize_region(city: str) -> str:
    """LLM 지역명을 도·시·군·구 단위로 정리해 장소 검색용 지역명으로 만든다."""
    cleaned = ' '.join(city.split())
    if not cleaned or len(cleaned) > 60:
        raise AppError(ErrorType.CITY_ERROR, '추천 지역명이 비어 있거나 지나치게 깁니다.')

    matches = _ADMIN_PATTERN.findall(cleaned)
    if not matches:
        return cleaned

    ordered = []
    seen = set()
    for value in matches:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ' '.join(ordered)


# 기존 호출부와 외부 테스트 호환을 위해 이름을 유지한다.
def normalize_city(city: str) -> str:
    return normalize_region(city)


def restaurant_query(city: str) -> str:
    return f'{normalize_region(city)} 음식점'


class KakaoPlaces:
    def __init__(self, config: PlacesConfig, session, secrets: SecretFilter):
        self.config = config
        self.session = session
        self.secrets = secrets

    def search(self, city: str, limit: int) -> PlaceSearch:
        query = restaurant_query(city)
        result = PlaceSearch('kakao', query, 'ok')
        params = {
            'query': query,
            'category_group_code': self.config.category_group_code,
            'size': min(limit, 15),
        }
        data = request_json(
            self.session,
            'GET',
            self.config.base_url + '/search/keyword.json',
            service_label='Kakao Local API',
            headers={'Authorization': f'KakaoAK {self.config.api_key}'},
            params=params,
            timeout=self.config.timeout_seconds,
        )
        documents = data.get('documents')
        if not isinstance(documents, list):
            raise AppError(ErrorType.RESPONSE_ERROR, '장소 검색 응답에 음식점 목록이 없습니다.')

        seen = set()
        for index, raw in enumerate(documents, start=1):
            if not isinstance(raw, dict):
                self._warning(result, index, '이름과 주소를 읽을 수 없어 제외했습니다.')
                continue
            raw = self.secrets.data(raw)
            name = self._text(raw.get('place_name'))
            address = self._text(raw.get('road_address_name')) or self._text(raw.get('address_name'))
            if not name or not address:
                self._warning(result, index, '이름 또는 주소가 없어 제외했습니다.')
                continue
            identity = str(raw.get('id') or (name, address))
            if identity in seen:
                continue
            seen.add(identity)

            place = Place(name=name, address=address, category=self._text(raw.get('category_name')))
            raw_url = self._text(raw.get('place_url'))
            place.url = safe_url(raw_url)
            if raw_url and not place.url:
                self._warning(result, index, '유효하지 않은 장소 링크를 제외했습니다.')

            for source, target, maximum in [('x', 'lng', 180), ('y', 'lat', 90)]:
                try:
                    if isinstance(raw.get(source), bool):
                        raise ValueError
                    value = float(raw[source])
                    if not math.isfinite(value) or abs(value) > maximum:
                        raise ValueError
                    setattr(place, target, value)
                except (ValueError, TypeError, KeyError, OverflowError):
                    self._warning(result, index, f'{target} 좌표를 사용할 수 없습니다.')
            result.restaurants.append(place)

        if not result.restaurants:
            result.status = 'empty'
            result.errors.append(
                ErrorRecord('place_search', ErrorType.EMPTY_RESULT.value, '사용 가능한 음식점 검색 결과가 없습니다.')
            )
        return result

    @staticmethod
    def _text(value) -> str | None:
        return ' '.join(value.split()) if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _warning(result: PlaceSearch, index: int, message: str):
        result.errors.append(
            ErrorRecord('place_search', ErrorType.PLACE_DATA_WARNING.value, f'검색 항목 {index}: {message}')
        )
