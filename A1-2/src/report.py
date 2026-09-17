"""최종 LLM이 생성한 Markdown의 구조와 필수 값을 검증한다."""

from __future__ import annotations

import re

from .models import AppError, ErrorType, RunResult


SECTIONS = ('추천 지역', '추천 이유', '날씨 요약', '행사/축제', '맛집 추천', '1일 일정 제안', '오류 요약(errors)')
NOTICE = '날씨는 계절적 참고 정보이며, 행사 일정은 방문 전 확인이 필요합니다.'


def sections(text: str) -> dict[str, str]:
    headings = list(re.finditer(r'^## (.+?)\s*$', text, re.M))
    names = [match.group(1).strip() for match in headings]
    if names != list(SECTIONS) or '```' in text:
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트의 필수 제목·순서 또는 중복 여부를 확인할 수 없습니다.')
    result = {}
    for index, heading in enumerate(headings):
        stop = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        content = text[heading.end():stop].strip()
        if not content:
            raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트에 비어 있는 필수 섹션이 있습니다.')
        result[names[index]] = content
    return result


def itinerary(text: str) -> dict[str, str]:
    headings = list(re.finditer(r'^### (오전|오후|저녁)\s*$', text, re.M))
    if [match.group(1) for match in headings] != ['오전', '오후', '저녁']:
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '일정에 오전·오후·저녁 구역이 모두 필요합니다.')
    result = {}
    for index, heading in enumerate(headings):
        stop = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():stop].strip()
        if not body:
            raise AppError(ErrorType.REPORT_FORMAT_ERROR, '오전·오후·저녁 일정 내용이 비어 있습니다.')
        result[heading.group(1)] = body
    return result


def finalize_report(text: str, result: RunResult) -> str:
    parts = sections(text)
    itinerary(parts['1일 일정 제안'])
    if text.splitlines()[0].strip() != f'# {result.requested_date} 국내 여행 추천 리포트':
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트 제목의 날짜 또는 형식이 올바르지 않습니다.')
    if result.recommendation.recommended_city not in parts['추천 지역']:
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트의 추천 지역이 원본 추천과 다릅니다.')
    if any(event not in parts['행사/축제'] for event in result.recommendation.events):
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트에 원본 행사/축제 후보가 누락되었습니다.')
    if result.restaurants:
        if any(place.name not in parts['맛집 추천'] for place in result.restaurants):
            raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트에 검색된 음식점이 누락되었습니다.')
    elif '데이터 없음' not in parts['맛집 추천']:
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '음식점 결과가 없을 때는 데이터 없음으로 표시해야 합니다.')
    if result.errors:
        if any(error.type not in parts['오류 요약(errors)'] for error in result.errors):
            raise AppError(ErrorType.REPORT_FORMAT_ERROR, '리포트에 실행 오류 유형이 누락되었습니다.')
    elif '없음' not in parts['오류 요약(errors)']:
        raise AppError(ErrorType.REPORT_FORMAT_ERROR, '오류가 없을 때는 오류 요약에 없음을 표시해야 합니다.')
    return text
