import io

import pytest
from rich.console import Console

from src.console import TravelConsole
from src.models import Place, RunResult


@pytest.mark.parametrize('width', [60, 79, 80, 103, 104, 120])
def test_responsive_output_preserves_text(width, monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'xterm-256color')
    stream = io.StringIO()
    rich_console = Console(file=stream, width=width, force_terminal=True, color_system=None, record=True)
    console = TravelConsole(rich_console)
    result = RunResult.start('2026-10-15', 'model')
    result.restaurants = [Place('[red]긴식당이름', '경북 경주시 내남면 포석로 112', '음식점 > 한식 > 회',
                                'https://place.map.kakao.com/13718224')]
    console.places(result)
    plain = rich_console.export_text()
    compact = ''.join(plain.split())
    assert '[red]긴식당이름' in compact
    assert '경북경주시내남면포석로112' in compact
    assert 'https://place.map.kakao.com/13718224' in compact
    assert ('번호' in plain) == (width >= 80)


def test_plain_output_has_no_control_sequences(console):
    console[0].print('\x1b[31m악성 제어문자\x1b[0m')
    assert '\x1b' not in console[1].getvalue()
