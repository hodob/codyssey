import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from main import main, parse_date
from src.models import RunResult


def test_valid_date_is_normalized():
    assert parse_date('2026-10-15') == '2026-10-15'


@pytest.mark.parametrize('value', ['2026-2-03', '2026-02-30', '2026-13-01', 'bad-date'])
def test_calendar_validation(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_date(value)


@pytest.mark.parametrize('args', [[], ['-date', '2026-02-30'], ['--date', '2026-2-1']])
def test_invalid_cli_before_network(args):
    script = Path(__file__).resolve().parents[1] / 'main.py'
    result = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, encoding='utf-8'
    )
    assert result.returncode == 2 and 'usage:' in result.stderr


def test_no_tui_option_is_documented_by_parser():
    script = Path(__file__).resolve().parents[1] / 'main.py'
    result = subprocess.run(
        [sys.executable, str(script), '--help'], capture_output=True, text=True, encoding='utf-8'
    )
    assert result.returncode == 0
    assert '--no-tui' in result.stdout and '-date' in result.stdout


def test_no_tui_calls_shared_pipeline(config, monkeypatch):
    called = []

    def fake_pipeline(date, loaded_config, llm, places, console):
        called.append((date, loaded_config))
        result = RunResult.start(date, loaded_config.llm.model)
        result.status = 'completed'
        return result

    monkeypatch.setattr('src.config.load_config', lambda root: config)
    monkeypatch.setattr('src.pipeline.run_pipeline', fake_pipeline)
    assert main(['-date', '2026-10-15', '--no-tui']) == 0
    assert called == [('2026-10-15', config)]
