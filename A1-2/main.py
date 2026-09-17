"""실행: python main.py -date "2026-10-15"."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def parse_date(value: str) -> str:
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise argparse.ArgumentTypeError('날짜는 YYYY-MM-DD 형식이어야 합니다.')
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError('실제 달력에 존재하는 날짜를 입력하세요.') from exc


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description='여행 날짜로 국내 여행지와 음식점을 추천합니다.')
    parser.add_argument('-date', '--date', required=True, type=parse_date, help='여행 날짜 (YYYY-MM-DD)')
    parser.add_argument('--no-tui', action='store_true', help='TUI 없이 일반 CLI 모드로 실행')
    args = parser.parse_args(argv)

    try:
        import requests
        from src.config import load_config
        from src.console import TravelConsole
        from src.llm import LLMClient
        from src.models import ConfigError
        from src.pipeline import run_pipeline
        from src.places import KakaoPlaces
        from src.safety import SecretFilter
        from src.terminal import interactive_terminal
    except ImportError:
        print('필요한 패키지가 없습니다. python -m pip install -r requirements.txt 를 실행하세요.', file=sys.stderr)
        return 2

    console = TravelConsole()
    try:
        config = load_config(Path(__file__).resolve().parent)
    except ConfigError as error:
        console.error(f'설정 오류: {error}')
        console.print('실행 중단 · API 호출 없음 · 종료 코드 2')
        return 2

    secrets = SecretFilter((config.llm.api_key, config.places.api_key))

    # 기본은 TUI이며, --no-tui 또는 비대화형 터미널에서는 일반 CLI로 실행한다.
    if not args.no_tui and interactive_terminal():
        try:
            from src.tui import run_tui
        except ImportError:
            console.error('TUI 패키지가 없습니다. python -m pip install -r requirements.txt 를 실행하세요.')
            return 2
        return run_tui(args.date, config)

    console.secrets = secrets
    console.header(args.date, config.llm.model)
    try:
        with requests.Session() as llm_session, requests.Session() as place_session:
            result = run_pipeline(
                args.date,
                config,
                LLMClient(config.llm, llm_session, secrets),
                KakaoPlaces(config.places, place_session, secrets),
                console,
            )
    except KeyboardInterrupt:
        console.error('실행을 중단했습니다.')
        return 130

    if any(error.type == 'INTERRUPTED' for error in result.errors):
        return 130
    return 0 if result.status in ('completed', 'completed_with_warnings') else 1


if __name__ == '__main__':
    raise SystemExit(main())
