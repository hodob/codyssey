"""터미널 폭에 맞춰 출력한다. API나 파일 저장은 수행하지 않는다."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from .models import Recommendation, RunResult
from .report import NOTICE, itinerary, sections
from .safety import SecretFilter


# TUI와 비대화형 출력이 공유하는 고정 여행 팔레트
TEAL = '#147D8C'
AMBER = '#E59F3A'
CORAL = '#C94C4C'


class TravelConsole:
    def __init__(self, console: Console | None = None, secrets: SecretFilter | None = None):
        self.console = console or Console(highlight=False)
        self.secrets = secrets or SecretFilter()

    @property
    def visual(self):
        return self.console.is_terminal and not self.console.is_dumb_terminal and 'NO_COLOR' not in os.environ

    @property
    def width(self):
        return min(self.console.width, 104)

    def text(self, value, style=None):
        return Text(self.secrets.text(str(value)), style=style or '')

    def print(self, value=''):
        self.console.print(self.text(value), soft_wrap=not self.visual)

    def header(self, date: str, model: str):
        self.console.print(self.text(f'국내 여행 플래너  ·  {date}', f'bold {TEAL}'))
        self.print(f'모델  {model}')
        self.print()

    @contextmanager
    def stage(self, index: int, label: str):
        started = time.monotonic()
        if not self.visual:
            self.print(f'[{index}/3] {label} 중...')
        progress = Progress(SpinnerColumn(), TextColumn('{task.description}'), TimeElapsedColumn(),
                            console=self.console, transient=True, disable=not self.visual)
        try:
            with progress:
                progress.add_task(f'[{index}/3] {label}', total=None)
                yield
        except BaseException:
            self.print(f'[{index}/3] {label} 중단 · {time.monotonic() - started:.1f}초')
            raise
        else:
            self.print(f'[{index}/3] {label} 완료 · {time.monotonic() - started:.1f}초')

    def warning(self, message: str):
        self.console.print(self.text(f'주의  {message}', AMBER), soft_wrap=not self.visual)

    def error(self, message: str):
        self.console.print(self.text(f'오류  {message}', CORAL), soft_wrap=not self.visual)

    def recommendation(self, value: Recommendation):
        elements = [self.text(value.recommended_city, f'bold {TEAL}'), self.text(''),
                    self.text('추천 이유  ' + value.reason), self.text('날씨  ' + value.weather),
                    self.text('행사 후보\n' + '\n'.join(f'  · {event}' for event in value.events))]
        if self.visual and self.width >= 45:
            self.console.print(Panel(Group(*elements), title='이번 여행은', border_style=TEAL,
                                     width=self.width, padding=(1, 2) if self.width >= 104 else (0, 1)))
        else:
            for element in elements:
                self.console.print(element, soft_wrap=not self.visual)
        self.print()

    def places(self, result: RunResult):
        self.print(f'맛집 후보 · {len(result.restaurants)}곳')
        if not result.restaurants:
            failed = result.place_search and result.place_search['status'] == 'failed'
            self.warning('데이터 없음 · ' + ('장소 검색 실패' if failed else '검색 결과 0건'))
            return
        if not self.visual or self.width < 80:
            for index, place in enumerate(result.restaurants, 1):
                self.print(f'{index:02}  {place.name}')
                self.print(f'    분류  {place.category or "정보 없음"}')
                self.print(f'    주소  {place.address}')
                self.print(f'    지도  {place.url or "정보 없음"}')
                self.print()
        else:
            wide = self.width >= 104
            table = Table(box=box.SIMPLE_HEAD, width=self.width, padding=(0, 1), show_edge=False)
            table.add_column('번호', width=4, no_wrap=True)
            table.add_column('식당', ratio=3, overflow='fold')
            table.add_column('주소', ratio=4, overflow='fold')
            if wide:
                table.add_column('분류', ratio=2, overflow='fold')
            for index, place in enumerate(result.restaurants, 1):
                name = place.name if wide else f'{place.name}\n{place.category or "정보 없음"}'
                cells = [str(index), name, place.address]
                if wide:
                    cells.append(place.category or '정보 없음')
                table.add_row(*(self.text(cell) for cell in cells))
            self.console.print(table)
            for index, place in enumerate(result.restaurants, 1):
                self.print(f'장소 링크 {index}. {place.url or "정보 없음"}')

    def report(self, markdown: str, result: RunResult):
        schedule = itinerary(sections(markdown)['1일 일정 제안'])
        self.print('\n하루 일정')
        for period, content in schedule.items():
            self.print(f'  {period}\n{content}')
        self.print('\n안내  ' + NOTICE)
        if result.errors:
            self.print('오류 요약')
            for error in result.errors:
                self.warning(f'[{error.type}] {error.message}')
        else:
            self.print('오류  없음')

    def saved(self, json_path, report_path, warnings=False):
        self.print('\n' + ('주의 사항과 함께 저장 완료' if warnings else '저장 완료'))
        self.print(f'  리포트  {report_path.resolve()}')
        self.print(f'  데이터  {json_path.resolve()}')
