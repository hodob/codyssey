import pytest
import requests

from conftest import FakeSession
from src.llm import LLMClient
from src.models import AppError, RECOMMENDATION_FORMAT
from src.places import KakaoPlaces
from src.safety import SecretFilter


def test_llm_uses_post_and_strict_json_schema(config):
    session = FakeSession(data={'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]})
    LLMClient(config.llm, session, SecretFilter()).complete([], RECOMMENDATION_FORMAT)
    method, url, request = session.calls[0]
    assert method == 'POST' and url.endswith('/chat/completions')
    assert request['json']['response_format']['json_schema']['strict'] is True
    assert request['headers']['Authorization'] == 'Bearer ' + config.llm.api_key


@pytest.mark.parametrize('status,kind', [
    (401, 'AUTH_ERROR'), (403, 'AUTH_ERROR'), (429, 'QUOTA_ERROR'),
    (400, 'REQUEST_ERROR'), (404, 'REQUEST_ERROR'), (502, 'HTTP_ERROR'),
])
def test_http_errors(config, status, kind):
    session = FakeSession(status=status, data={'message': config.llm.api_key})
    with pytest.raises(AppError) as caught:
        LLMClient(config.llm, session, SecretFilter()).complete([])
    assert caught.value.kind == kind
    assert config.llm.api_key not in str(caught.value)


@pytest.mark.parametrize('error,kind', [
    (requests.Timeout('secret-body'), 'TIMEOUT'),
    (requests.ConnectionError('secret-body'), 'NETWORK_ERROR'),
])
def test_network_errors(config, error, kind):
    with pytest.raises(AppError) as caught:
        KakaoPlaces(config.places, FakeSession(error=error), SecretFilter()).search('경주', 5)
    assert caught.value.kind == kind


def test_kakao_uses_get_and_normalized_query(config):
    place = {
        'id': '1', 'place_name': '식당', 'road_address_name': '', 'address_name': '경주시 주소',
        'category_name': '한식', 'x': '129.21', 'y': '35.84',
        'place_url': 'https://place.map.kakao.com/1',
    }
    session = FakeSession(data={'documents': [place]})
    result = KakaoPlaces(config.places, session, SecretFilter()).search('경상북도 경주시', 5)
    assert result.restaurants[0].name == '식당'
    method, _, request = session.calls[0]
    assert method == 'GET'
    assert request['params'] == {
        'query': '경상북도 경주시 음식점',
        'category_group_code': 'FD6',
        'size': 5,
    }


def test_kakao_empty(config):
    result = KakaoPlaces(config.places, FakeSession(data={'documents': []}), SecretFilter()).search('경주', 5)
    assert result.status == 'empty'
    assert result.errors[0].type == 'EMPTY_RESULT'


@pytest.mark.parametrize('status', [401, 403])
def test_kakao_auth_failure(config, status):
    client = KakaoPlaces(config.places, FakeSession(status=status, data={}), SecretFilter())
    with pytest.raises(AppError) as caught:
        client.search('경주', 5)
    assert caught.value.kind == 'AUTH_ERROR'
