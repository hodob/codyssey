"""추천 → 음식점 검색 → 최종 Markdown 리포트의 세 단계를 조합한다."""

from __future__ import annotations

from dataclasses import asdict

from . import prompts
from .models import (
    AppConfig, AppError, ErrorRecord, ErrorType, Place,
    RECOMMENDATION_FORMAT, Recommendation, RunResult,
    completed_text, parse_recommendation,
)
from .places import PlaceProvider, normalize_region
from .report import finalize_report
from .safety import SecretFilter
from .storage import load_raw, result_paths, save_raw, save_report


def run_pipeline(date: str, config: AppConfig, llm, places: PlaceProvider, console) -> RunResult:
    root = config.project_root / 'results'
    secrets = SecretFilter((config.llm.api_key, config.places.api_key))
    json_path, report_path = result_paths(root, date)
    step = 'cache'

    def record(result: RunResult, error: AppError, stage: str, attempt: int = 1):
        result.errors.append(
            ErrorRecord(stage, error.kind, secrets.text(str(error)), attempt, error.http_status)
        )

    # 같은 날짜의 원본 JSON이 있으면 추천 LLM과 Kakao 호출을 생략한다.
    if json_path.exists():
        try:
            result = load_raw(root, date, config.llm.model)
        except AppError as error:
            result = RunResult.start(date, config.llm.model)
            record(result, error, 'cache')
            result.status = 'failed'
            console.error(str(error))
            return result

        console.print(f'캐시 사용 · {json_path.resolve()}')
        console.recommendation(result.recommendation)
        console.places(result)

        if report_path.exists():
            try:
                markdown = report_path.read_text(encoding='utf-8')
            except (OSError, UnicodeError) as exc:
                error = AppError(ErrorType.CACHE_ERROR, '저장된 Markdown 결과를 읽을 수 없습니다.')
                record(result, error, 'cache')
            else:
                result.report_file = report_path.name
                result.status = 'completed_with_warnings' if result.errors else 'completed'
                console.report(markdown, result)
                console.saved(json_path, report_path, bool(result.errors))
                return result
    else:
        result = RunResult.start(date, config.llm.model)

        step = 'recommendation'
        try:
            with console.stage(1, '여행지 추천'):
                correction = None
                previous_response = None
                for attempt in (1, 2):
                    response_text = None
                    try:
                        reply = llm.complete(
                            prompts.recommendation_messages(
                                date, correction, previous_response
                            ),
                            response_format=RECOMMENDATION_FORMAT,
                        )
                        response_text = secrets.text(completed_text(reply))
                        recommendation = parse_recommendation(response_text)
                        # 다음 단계에서 사용할 수 있는 지역명인지 값 수준에서 확인한다.
                        normalize_region(recommendation.recommended_city)
                        result.recommendation = Recommendation(
                            **secrets.data(asdict(recommendation))
                        )
                        break
                    except AppError as error:
                        record(result, error, step, attempt)
                        retryable = error.kind in {
                            ErrorType.EMPTY_REQUIRED_VALUE.value,
                            ErrorType.INVALID_FIELD_VALUE.value,
                            ErrorType.CITY_ERROR.value,
                            ErrorType.RESPONSE_ERROR.value,
                            ErrorType.TRUNCATED.value,
                        }
                        if not retryable or attempt == 2:
                            raise
                        correction = error
                        # 파싱·값 검증까지 도달한 응답만 보정 문맥으로 전달한다.
                        # 응답 자체가 없거나 토큰 한도로 중단된 내용은 포함하지 않는다.
                        previous_response = response_text
                        console.warning(
                            f'[{error.kind}] {error} · 보정 요청 1/1을 진행합니다.'
                        )
            console.recommendation(result.recommendation)
        except AppError as error:
            if not result.errors or result.errors[-1].type != error.kind:
                record(result, error, step)
            result.status = 'failed'
            console.error(str(error))
            return result

        step = 'place_search'
        try:
            with console.stage(2, '음식점 검색'):
                search = places.search(result.recommendation.recommended_city, config.places.limit)
            result.place_search = {
                'provider': search.provider,
                'query': search.query,
                'status': search.status,
            }
            result.restaurants = [
                Place(**secrets.data(asdict(place))) for place in search.restaurants
            ]
            result.errors.extend(
                ErrorRecord(**secrets.data(asdict(error))) for error in search.errors
            )
        except AppError as error:
            record(result, error, step)
            if error.kind == ErrorType.INTERRUPTED.value:
                result.status = 'failed'
                console.error(str(error))
                return result
            result.place_search = {
                'provider': config.places.provider,
                'query': '',
                'status': 'failed',
            }
            console.warning(f'{error} 음식점 정보 없이 리포트를 계속 생성합니다.')
        console.places(result)

        try:
            save_raw(root, result, secrets)
        except OSError:
            error = AppError(
                ErrorType.SAVE_ERROR,
                '원본 JSON을 저장할 수 없습니다. 폴더 권한과 디스크 공간을 확인하세요.',
            )
            record(result, error, 'save')
            result.status = 'failed'
            console.error(str(error))
            return result

    # raw만 존재하는 캐시 경로도 이 지점에서 최종 LLM만 실행한다.
    step = 'report'
    try:
        with console.stage(3, '최종 리포트 생성'):
            reply = llm.complete(prompts.report_messages(result))
            markdown = finalize_report(
                secrets.text(completed_text(reply)), result
            )
    except AppError as error:
        # raw 캐시는 추천·장소 단계의 재사용 데이터다. 일시적인 리포트 오류는
        # 다음 재실행까지 고착시키지 않고 현재 실행 결과에만 기록한다.
        record(result, error, step)
        result.status = 'failed'
        console.error(str(error))
        return result

    try:
        # 최종 errors 상태도 raw에 반영한 뒤 Markdown을 저장한다.
        save_raw(root, result, secrets)
        report_path = save_report(root, result, markdown, secrets)
    except OSError:
        error = AppError(
            ErrorType.SAVE_ERROR,
            '결과 파일을 저장할 수 없습니다. 폴더 권한과 디스크 공간을 확인하세요.',
        )
        record(result, error, 'save')
        result.status = 'failed'
        console.error(str(error))
        return result

    result.status = 'completed_with_warnings' if result.errors else 'completed'
    console.report(markdown, result)
    console.saved(json_path, report_path, bool(result.errors))
    return result
