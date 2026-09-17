"""날짜별 원본 JSON과 Markdown 결과를 UTF-8로 원자적으로 저장한다."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import AppError, ErrorRecord, ErrorType, Place, Recommendation, RunResult
from .safety import SecretFilter


def result_paths(root: Path, date: str) -> tuple[Path, Path]:
    return root / f'{date}_raw.json', root / f'{date}_travel_plan.md'


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', newline='\n', dir=path.parent,
            prefix='.travel-', suffix='.tmp', delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def save_raw(root: Path, result: RunResult, secrets: SecretFilter) -> Path:
    json_path, _ = result_paths(root, result.requested_date)
    data = secrets.data(result.to_raw_dict())
    atomic_write(json_path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return json_path


def save_report(root: Path, result: RunResult, report: str, secrets: SecretFilter) -> Path:
    _, report_path = result_paths(root, result.requested_date)
    atomic_write(report_path, secrets.text(report))
    result.report_file = report_path.name
    return report_path


def load_raw(root: Path, date: str, model: str) -> RunResult:
    json_path, _ = result_paths(root, date)
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
        if data.get('date') != date:
            raise ValueError
        recommendation = Recommendation(**data['recommendation'])
        places = [Place(**item) for item in data.get('places', [])]
        errors = [ErrorRecord(**item) for item in data.get('errors', [])]
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise AppError(ErrorType.CACHE_ERROR, '저장된 원본 JSON 캐시를 읽을 수 없습니다.') from exc

    result = RunResult.start(date, model)
    result.recommendation = recommendation
    result.restaurants = places
    result.errors = errors
    place_failed = any(
        error.step == 'place_search'
        and error.type not in (ErrorType.EMPTY_RESULT.value, ErrorType.PLACE_DATA_WARNING.value)
        for error in errors
    )
    result.place_search = {
        'provider': 'kakao',
        'query': '',
        'status': 'failed' if place_failed else ('empty' if not places else 'ok'),
    }
    return result
