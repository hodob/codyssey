import json

import pytest

from src.llm_input import compact_address
from src.models import ErrorRecord, Place, Recommendation, RunResult
from src.prompts import report_messages


@pytest.mark.parametrize('address,city,expected', [
    ('제주시 무는대로 123', '제주', '무는대로 123'),
    ('제주특별자치도 제주시 무는대로 123', '제주시', '무는대로 123'),
    ('전북특별자치도 전주시 완산구 전주천동로 12', '전주', '완산구 전주천동로 12'),
    ('서울특별시 종로구 종로 1', '서울', '종로구 종로 1'),
])
def test_address_prefix_only(address, city, expected):
    assert compact_address(address, city) == expected


def test_report_input_contains_only_needed_data():
    result = RunResult.start('2026-10-15', 'test')
    result.recommendation = Recommendation('제주', '가을', ['후보'], '산책')
    result.restaurants = [Place('식당', '제주시 중앙로 123', '한식', 'https://example.com', 126.5, 33.5)]
    result.errors = [ErrorRecord('place_search', 'EMPTY_RESULT', '예시 오류')]

    payload = json.loads(report_messages(result)[1]['content'])
    restaurant = payload['restaurants'][0]
    assert restaurant['address'] == '중앙로 123'
    assert not {'url', 'lng', 'lat'} & restaurant.keys()
    assert payload['errors'][0]['type'] == 'EMPTY_RESULT'
