import io
import json

import pytest
import requests
from rich.console import Console

from src.console import TravelConsole
from src.models import AppConfig, Completion, LLMConfig, PlacesConfig
from src.safety import SecretFilter


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('자동 테스트에서는 실제 네트워크를 사용하지 않습니다.')
    monkeypatch.setattr(requests.Session, 'request', blocked)


@pytest.fixture
def config(tmp_path):
    return AppConfig(
        tmp_path,
        LLMConfig('https://llm.example/v1', 'test-only-llm-secret'),
        PlacesConfig('https://places.example/v2/local', 'test-only-place-secret', limit=5),
    )


@pytest.fixture
def recommendation():
    return {
        'recommended_city': '경상북도 경주시',
        'weather': '선선한 가을 날씨입니다.',
        'events': ['가을 문화행사 후보: 일정 확인 필요'],
        'reason': '산책하기 좋은 계절입니다. 유적지를 함께 둘러볼 수 있습니다.',
    }


@pytest.fixture
def markdown():
    return '''# 2026-10-15 국내 여행 추천 리포트
## 추천 지역
경상북도 경주시
## 추천 이유
산책하기 좋습니다.
## 날씨 요약
선선합니다.
## 행사/축제
가을 문화행사 후보: 일정 확인 필요
## 맛집 추천
실제 식당
## 1일 일정 제안
### 오전
유적지 산책
### 오후
명소 관람
### 저녁
현지 식사
## 오류 요약(errors)
없음
'''


@pytest.fixture
def console(config):
    stream = io.StringIO()
    view = TravelConsole(
        Console(file=stream, width=104, force_terminal=False, color_system=None),
        SecretFilter((config.llm.api_key, config.places.api_key)),
    )
    return view, stream


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, response_format=None):
        self.calls.append((messages, response_format))
        if not self.replies:
            raise AssertionError('예상하지 않은 LLM 호출입니다.')
        value = self.replies.pop(0)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, Completion):
            return value
        content = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        return Completion(content, 'stop', usage={'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30})


class FakeSession:
    def __init__(self, status=200, data=None, error=None, raw=None):
        self.status, self.data, self.error, self.raw = status, data, error, raw
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response.encoding = 'utf-8'
        response._content = self.raw if self.raw is not None else json.dumps(self.data).encode('utf-8')
        response._content_consumed = True
        return response


@pytest.fixture
def project(tmp_path, monkeypatch):
    sample_config = '''llm:
  base_url: "https://llm.example/v1"
  api_key: "${LLM_API_KEY}"
  model: "test-model"
  max_tokens: 2048
  timeout_seconds: 60
places:
  provider: "kakao"
  base_url: "https://dapi.kakao.com/v2/local"
  api_key: "${KAKAO_REST_API_KEY}"
  category_group_code: "FD6"
  limit: 5
  timeout_seconds: 30
'''
    (tmp_path / 'config.yml').write_text(sample_config, encoding='utf-8')
    (tmp_path / '.env').write_text(
        'LLM_API_KEY=dotenv-llm-value\nKAKAO_REST_API_KEY=dotenv-kakao-value\n',
        encoding='utf-8',
    )
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('KAKAO_REST_API_KEY', raising=False)
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED', raising=False)
    return tmp_path
