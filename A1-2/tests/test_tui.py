import asyncio

import pytest
pytest.importorskip('textual')
from textual.widgets import ContentSwitcher, OptionList, Static

from conftest import FakeLLM
from test_pipeline import FakePlaces
from src.models import AppError
from src.pipeline import run_pipeline
from src.terminal import interactive_terminal
from src.tui import Records, TravelApp


async def wait_done(app, pilot):
    for _ in range(120):
        if app.finished:
            return
        await pilot.pause(.02)
    pytest.fail('pipeline did not finish')


def test_keyboard_pages_details_and_logs(config, recommendation, markdown):
    llm, places = FakeLLM(recommendation, markdown), FakePlaces()

    def runner(view):
        return run_pipeline('2026-10-15', config, llm, places, view)

    async def scenario():
        app = TravelApp('2026-10-15', config, runner=runner)
        async with app.run_test(size=(100, 35)) as pilot:
            await wait_done(app, pilot)
            assert app.result.status == 'completed'
            await pilot.press('3', 'enter')
            assert app.active == 'detail'
            assert '실제 식당' in str(app.query_one('#detail-body', Static).render())
            await pilot.press('escape')
            assert app.query_one(OptionList).highlighted == 0
            await pilot.press('2')
            await pilot.pause()
            assert app.active == 'schedule'
            await pilot.press('1', 'l')
            assert isinstance(app.screen, Records)
            assert '리포트:' in '\n'.join(app.records)
            await pilot.press('escape')
            assert app.query_one('#pages', ContentSwitcher).region.width <= 100
            await pilot.press('q')
        app.thread.join(timeout=1)
        assert not app.thread.is_alive()
        assert len(llm.calls) == 2 and len(places.calls) == 1

    asyncio.run(scenario())


def test_tui_place_failure_still_generates_report(config, recommendation, markdown):
    places = FakePlaces(fail=AppError('TIMEOUT', '검색 실패'))
    markdown = markdown.replace('실제 식당', '데이터 없음').replace(
        '## 오류 요약(errors)\n없음', '## 오류 요약(errors)\n- **TIMEOUT**'
    )

    def runner(view):
        return run_pipeline('2026-10-15', config, FakeLLM(recommendation, markdown), places, view)

    async def scenario():
        app = TravelApp('2026-10-15', config, runner=runner)
        async with app.run_test(size=(100, 35)) as pilot:
            await wait_done(app, pilot)
            assert app.result.status == 'completed_with_warnings'
            assert '데이터 없음' in str(app.query_one('#places-state', Static).render())
            await pilot.press('2')
            await pilot.pause()
            assert app.active == 'schedule'
            await pilot.press('q')
        app.thread.join(timeout=1)

    asyncio.run(scenario())


def test_noninteractive_terminal_is_not_tui(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    assert not interactive_terminal()
