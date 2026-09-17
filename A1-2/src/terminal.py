"""TUI가 입력을 소유하기 전에 터미널 기능을 확인한다."""
import os
import sys


def interactive_terminal():
    return bool(sys.stdin.isatty() and sys.stdout.isatty()
                and os.environ.get('TERM', '').lower() != 'dumb'
                and 'NO_COLOR' not in os.environ)
