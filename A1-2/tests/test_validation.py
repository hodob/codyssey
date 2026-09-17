import json

import pytest

from src.models import AppError, Completion, completed_text, parse_recommendation
from src.places import normalize_region, restaurant_query


@pytest.mark.parametrize('field,value,kind', [
    ('weather', ' ', 'EMPTY_REQUIRED_VALUE'),
    ('reason', '', 'EMPTY_REQUIRED_VALUE'),
    ('recommended_city', '', 'EMPTY_REQUIRED_VALUE'),
    ('events', [], 'INVALID_FIELD_VALUE'),
    ('events', ['a'] * 4, 'INVALID_FIELD_VALUE'),
    ('events', [' '], 'EMPTY_REQUIRED_VALUE'),
])
def test_unusable_values(recommendation, field, value, kind):
    recommendation[field] = value
    with pytest.raises(AppError) as caught:
        parse_recommendation(json.dumps(recommendation))
    assert caught.value.kind == kind


@pytest.mark.parametrize('reply,kind', [
    (Completion('', 'length'), 'TRUNCATED'),
    (Completion('{}', 'stop', refusal=True), 'REFUSAL'),
    (Completion('text', 'content_filter'), 'REFUSAL'),
    (Completion('text', ''), 'INCOMPLETE'),
    (Completion('  ', 'stop'), 'EMPTY_RESPONSE'),
])
def test_completion_status(reply, kind):
    with pytest.raises(AppError) as caught:
        completed_text(reply)
    assert caught.value.kind == kind


@pytest.mark.parametrize('source,expected', [
    ('  경상북도   경주시  ', '경상북도 경주시'),
    ('부산광역시 해운대구', '부산광역시 해운대구'),
    ('경상북도 경주시 경주시', '경상북도 경주시'),
    ('경주', '경주'),
])
def test_region_regex_normalization(source, expected):
    assert normalize_region(source) == expected


def test_restaurant_query_uses_food_keyword():
    assert restaurant_query('경상북도 경주시') == '경상북도 경주시 음식점'
