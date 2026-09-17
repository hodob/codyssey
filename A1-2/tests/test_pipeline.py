import json

import pytest

from conftest import FakeLLM
from src.models import AppError, Completion, ErrorRecord, Place, PlaceSearch
from src.pipeline import run_pipeline
from src.storage import result_paths


class FakePlaces:
    def __init__(self, fail=None, empty=False):
        self.calls = []
        self.fail, self.empty = fail, empty

    def search(self, city, limit):
        self.calls.append((city, limit))
        if self.fail:
            raise self.fail
        items = [] if self.empty else [
            Place('실제 식당', '경주시 실제 주소', '한식', 'https://place.map.kakao.com/1', 129.2, 35.8)
        ]
        errors = [ErrorRecord('place_search', 'EMPTY_RESULT', '검색 결과 0건')] if self.empty else []
        return PlaceSearch('kakao', f'{city} 음식점', 'empty' if self.empty else 'ok', items, errors)


def read_raw(config, date='2026-10-15'):
    path, _ = result_paths(config.project_root / 'results', date)
    return json.loads(path.read_text(encoding='utf-8'))


def markdown_with_errors(markdown, *types):
    summary = '\n'.join(f'- **{kind}**' for kind in types) or '없음'
    return markdown.replace('## 오류 요약(errors)\n없음', f'## 오류 요약(errors)\n{summary}')


def test_success_flow(config, recommendation, markdown, console):
    llm, places = FakeLLM(recommendation, markdown), FakePlaces()
    result = run_pipeline('2026-10-15', config, llm, places, console[0])

    assert result.status == 'completed'
    assert places.calls == [('경상북도 경주시', 5)]
    assert len(llm.calls) == 2
    assert llm.calls[0][1]['json_schema']['strict'] is True
    assert llm.calls[1][1] is None

    payload = json.loads(llm.calls[1][0][1]['content'])
    assert payload['restaurants'][0]['name'] == '실제 식당'
    assert payload['errors'] == []

    raw_path, report_path = result_paths(config.project_root / 'results', '2026-10-15')
    assert raw_path.exists() and report_path.exists()
    stored = read_raw(config)
    assert set(stored) == {'date', 'recommendation', 'places', 'errors'}
    report = report_path.read_text(encoding='utf-8')
    assert report == markdown


def test_single_value_correction_includes_previous_response(config, recommendation, markdown, console):
    bad = {**recommendation, 'events': []}
    llm = FakeLLM(bad, recommendation, markdown_with_errors(markdown, 'INVALID_FIELD_VALUE'))
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    assert result.status == 'completed_with_warnings'
    assert len(llm.calls) == 3
    previous = llm.calls[1][0][-2]
    correction = llm.calls[1][0][-1]['content']
    assert previous == {
        'role': 'assistant',
        'content': json.dumps(bad, ensure_ascii=False),
    }
    assert 'error_type: INVALID_FIELD_VALUE' in correction
    assert 'error_detail:' in correction
    assert result.errors[0].type == 'INVALID_FIELD_VALUE'


def test_unexpected_json_parse_failure_gets_one_correction(config, recommendation, markdown, console):
    llm = FakeLLM(Completion('{broken', 'stop'), recommendation, markdown_with_errors(markdown, 'RESPONSE_ERROR'))
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    assert result.status == 'completed_with_warnings'
    assert len(llm.calls) == 3
    assert llm.calls[1][0][-2] == {'role': 'assistant', 'content': '{broken'}
    correction = llm.calls[1][0][-1]['content']
    assert 'error_type: RESPONSE_ERROR' in correction
    assert result.errors[0].type == 'RESPONSE_ERROR'


def test_correction_without_response_omits_assistant_message(config, recommendation, markdown, console):
    llm = FakeLLM(
        AppError('RESPONSE_ERROR', '모델 답변 없음'),
        recommendation,
        markdown_with_errors(markdown, 'RESPONSE_ERROR'),
    )
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    assert result.status == 'completed_with_warnings'
    assert [message['role'] for message in llm.calls[1][0]] == ['system', 'user', 'user']


def test_truncated_correction_omits_partial_response(config, recommendation, markdown, console):
    llm = FakeLLM(
        Completion('{"recommended_city": "경주"', 'length'),
        recommendation,
        markdown_with_errors(markdown, 'TRUNCATED'),
    )
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    assert result.status == 'completed_with_warnings'
    assert [message['role'] for message in llm.calls[1][0]] == ['system', 'user', 'user']


def test_previous_response_is_secret_filtered(config, recommendation, markdown, console):
    bad = {
        **recommendation,
        'events': [],
        'reason': f'노출되면 안 되는 값: {config.llm.api_key}',
    }
    llm = FakeLLM(
        bad,
        recommendation,
        markdown_with_errors(markdown, 'INVALID_FIELD_VALUE'),
    )
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    previous = llm.calls[1][0][-2]['content']
    assert result.status == 'completed_with_warnings'
    assert config.llm.api_key not in previous
    assert '[REDACTED]' in previous


def test_value_correction_stops_after_one_failed_retry(config, recommendation, console):
    bad = {**recommendation, 'recommended_city': ''}
    llm, places = FakeLLM(bad, bad), FakePlaces()
    result = run_pipeline('2026-10-15', config, llm, places, console[0])

    assert result.status == 'failed'
    assert len(llm.calls) == 2
    assert places.calls == []
    assert [error.attempt for error in result.errors] == [1, 2]


@pytest.mark.parametrize('kind', ['AUTH_ERROR', 'QUOTA_ERROR', 'TIMEOUT', 'NETWORK_ERROR', 'empty'])
def test_place_failure_continues(config, recommendation, markdown, console, kind):
    places = FakePlaces(
        empty=kind == 'empty',
        fail=AppError(kind, '장소 검색 실패') if kind != 'empty' else None,
    )
    error_type = 'EMPTY_RESULT' if kind == 'empty' else kind
    report_markdown = markdown.replace('실제 식당', '데이터 없음')
    llm = FakeLLM(recommendation, markdown_with_errors(report_markdown, error_type))
    result = run_pipeline('2026-10-15', config, llm, places, console[0])

    assert result.status == 'completed_with_warnings'
    assert len(llm.calls) == 2
    report_path = result_paths(config.project_root / 'results', '2026-10-15')[1]
    report = report_path.read_text(encoding='utf-8')
    assert '데이터 없음' in report
    assert result.errors[0].type in report


def test_report_failure_preserves_raw_without_markdown(config, recommendation, console):
    llm = FakeLLM(recommendation, AppError('QUOTA_ERROR', '사용량 제한', 429))
    result = run_pipeline('2026-10-15', config, llm, FakePlaces(), console[0])

    raw_path, report_path = result_paths(config.project_root / 'results', '2026-10-15')
    assert result.status == 'failed'
    assert raw_path.exists() and not report_path.exists()
    assert read_raw(config)['recommendation']['recommended_city'] == '경상북도 경주시'


def test_full_cache_skips_all_external_calls(config, recommendation, markdown, console):
    run_pipeline('2026-10-15', config, FakeLLM(recommendation, markdown), FakePlaces(), console[0])

    llm, places = FakeLLM(), FakePlaces()
    result = run_pipeline('2026-10-15', config, llm, places, console[0])
    assert result.status == 'completed'
    assert llm.calls == [] and places.calls == []


def test_raw_only_cache_calls_report_once(config, recommendation, markdown, console):
    first = FakeLLM(recommendation, AppError('QUOTA_ERROR', '사용량 제한', 429))
    run_pipeline('2026-10-15', config, first, FakePlaces(), console[0])

    llm, places = FakeLLM(markdown), FakePlaces()
    result = run_pipeline('2026-10-15', config, llm, places, console[0])
    assert result.status == 'completed'
    assert len(llm.calls) == 1 and places.calls == []
    assert result_paths(config.project_root / 'results', '2026-10-15')[1].exists()


def test_same_date_uses_fixed_result_files(config, recommendation, markdown, console):
    run_pipeline('2026-10-15', config, FakeLLM(recommendation, markdown), FakePlaces(), console[0])
    run_pipeline('2026-10-15', config, FakeLLM(), FakePlaces(), console[0])
    files = sorted(path.name for path in (config.project_root / 'results').iterdir())
    assert files == ['2026-10-15_raw.json', '2026-10-15_travel_plan.md']
