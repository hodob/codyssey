"""대화형 TUI. API 파이프라인은 작업 스레드에서 실행하고 화면은 이벤트로 갱신한다."""

from __future__ import annotations

import copy
import threading
import time
import webbrowser
from contextlib import contextmanager

import requests
from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, ContentSwitcher, Footer, OptionList, Static
from textual.widgets.option_list import Option

from .llm import LLMClient
from .models import AppError, ErrorType
from .pipeline import run_pipeline
from .places import KakaoPlaces
from .report import itinerary, sections
from .safety import SecretFilter, safe_url
from .storage import result_paths


# 화면 전반에서 공유하는 고정 팔레트. 여행지에 따라 색을 바꾸지 않는다.
INK = '#1F2937'
TEAL = '#147D8C'
MUTED = '#667085'
AMBER = '#E59F3A'


class ReadingPane(VerticalScroll):
    can_focus = True


class Records(ModalScreen):
    BINDINGS = [('escape', 'dismiss', '닫기'), ('l', 'dismiss', '닫기')]

    def compose(self):
        with Container(id='dialog'):
            yield Static('실행 기록 · 저장 위치', classes='dialog-title')
            with ReadingPane():
                yield Static('', id='record-body', markup=False)
            yield Button('닫기 [Esc]', id='close-records')

    def on_mount(self):
        self.refresh_records()
        self.set_interval(.5, self.refresh_records)
        self.query_one(ReadingPane).focus()

    def refresh_records(self):
        text = '\n'.join(self.app.records)
        if text != getattr(self, '_last_text', None):
            self.query_one('#record-body', Static).update(text)
            self._last_text = text

    def on_button_pressed(self, event):
        self.dismiss()


class ConfirmQuit(ModalScreen):
    BINDINGS = [('escape', 'dismiss(False)', '계속 보기'), ('n', 'dismiss(False)', '계속 보기'),
                ('y', 'dismiss(True)', '중단')]

    def compose(self):
        with Container(id='quit-dialog'):
            yield Static('진행 중인 작업을 중단할까요?', classes='dialog-title')
            yield Static('새 요청은 보내지 않고, 현재 요청이 끝나거나 시간 초과되면\n확보한 데이터를 저장한 뒤 종료합니다.', markup=False)
            yield Button('계속 보기 [N / Esc]', id='continue')
            yield Button('중단하고 종료 [Y]', id='confirm')

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == 'confirm')


class CancellableSession(requests.Session):
    def __init__(self, stop):
        super().__init__()
        self.stop = stop

    def request(self, *args, **kwargs):
        if self.stop.is_set():
            raise AppError(ErrorType.INTERRUPTED, '사용자가 실행을 중단했습니다.')
        timeout = kwargs.get('timeout', 45)
        if isinstance(timeout, (int, float)):
            kwargs['timeout'] = (min(10, timeout), min(45, timeout))
        try:
            response = super().request(*args, **kwargs)
        except requests.RequestException:
            if self.stop.is_set():
                raise AppError(ErrorType.INTERRUPTED, '사용자가 실행을 중단했습니다.')
            raise
        if self.stop.is_set():
            response.close()
            raise AppError(ErrorType.INTERRUPTED, '사용자가 실행을 중단했습니다.')
        return response


class PipelineView:
    """일반 콘솔 출력 계약을 UI 이벤트로 변환한다."""

    def __init__(self, app):
        self.app = app

    def send(self, kind, *values):
        self.app.call_from_thread(self.app.receive, kind, *copy.deepcopy(values))

    @contextmanager
    def stage(self, index, label):
        if self.app.stop.is_set():
            raise AppError(ErrorType.INTERRUPTED, '사용자가 실행을 중단했습니다.')
        started = time.monotonic()
        self.send('stage', index, label)
        try:
            yield
        except BaseException:
            self.send('log', f'[{index}/3] {label} 중단 · {time.monotonic()-started:.1f}초')
            raise
        else:
            self.send('log', f'[{index}/3] {label} 완료 · {time.monotonic()-started:.1f}초')

    def print(self, text): self.send('log', text)
    def warning(self, text): self.send('log', '주의: ' + text)
    def error(self, text): self.send('error', text)
    def recommendation(self, value): self.send('recommendation', value)
    def places(self, result): self.send('places', result)
    def report(self, markdown, result): self.send('report', markdown, result)
    def saved(self, json_path, report_path, warnings=False):
        self.send('log', f'JSON: {json_path.resolve()}\n리포트: {report_path.resolve()}')


class TravelApp(App):
    CSS_PATH = 'tui.tcss'
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding('1', "page('recommend')", '추천'),
        Binding('2', "page('schedule')", '일정'),
        Binding('3', "page('places')", '맛집'),
        Binding('escape', 'back', '뒤로'),
        Binding('l', 'records', '기록'),
        Binding('r', 'report', '문서'),
        Binding('q,ctrl+c', 'quit', '종료', priority=True, key_display='Q'),
    ]

    def __init__(self, date, config, *, runner=None):
        super().__init__()
        self.date, self.config = date, config
        self.runner = runner
        self.stop = threading.Event()
        self.result = None
        self.finished = False
        self.active = 'recommend'
        self.records = [f'모델: {config.llm.model}']
        self.places_data = []
        self.stage_started = time.monotonic()
        self.stage_label = '시작 준비'
        self.phase = 0
        self.selected = 0
        self.secrets = SecretFilter((config.llm.api_key, config.places.api_key))
        self.thread = None

    def compose(self) -> ComposeResult:
        yield Static(f'여행 안내서  ·  {self.date}', id='heading', markup=False)
        with Horizontal(id='tabs'):
            yield Button('추천', id='tab-recommend')
            yield Button('일정', id='tab-schedule')
            yield Button('맛집', id='tab-places')
        with ContentSwitcher(initial='recommend', id='pages'):
            with ReadingPane(id='recommend'):
                with Container(id='recommend-layout'):
                    with Container(id='recommend-copy'):
                        with Container(id='recommend-hero'):
                            yield Static('오늘의 목적지', id='recommend-kicker', markup=False)
                            yield Static('여행지 추천', id='recommend-city-name', markup=False)
                            yield Static('──────────────', id='recommend-city-divider', markup=False)
                            yield Static('여행지 추천을 준비하고 있습니다.', id='recommend-subtitle', markup=False)
                        with Container(id='recommend-reason', classes='recommend-section'):
                            yield Static('떠나기 전, 이곳을 고른 이유', classes='recommend-section-title')
                            yield Static('', id='recommend-reason-body', markup=False)
                        with Container(id='recommend-facts', classes='recommend-section'):
                            yield Static('오늘의 공기', classes='recommend-section-title')
                            yield Static('', id='recommend-weather-body', markup=False)
                        with Container(id='recommend-events', classes='recommend-section'):
                            yield Static('여행 중 만나는 장면', id='recommend-events-title', classes='recommend-section-title')
                            yield Static('', id='recommend-events-body', markup=False)
                        yield Static('', id='recommend-notice', markup=False)
            with ReadingPane(id='schedule'):
                yield Static('일정 생성 대기 중\n추천과 음식점 검색 후 자동으로 생성됩니다.', id='schedule-body', markup=False)
            with Container(id='places'):
                yield Static('음식점 검색 대기 중', id='places-state', markup=False)
                yield OptionList(id='place-list')
            with ReadingPane(id='detail'):
                yield Static('', id='detail-body', markup=False)
                yield Button('카카오 지도 열기', id='map-button')
                yield Button('맛집 목록으로 [Esc]', id='back-button')
        yield Static('', id='status', markup=False)
        yield Static('', id='context', markup=False)
        yield Footer()

    def on_mount(self):
        # 밝은 자체 팔레트에 맞춰 기본 위젯도 밝은 테마의 대비 규칙을 따른다.
        self.theme = 'textual-light'
        self.action_page('recommend')
        self.set_interval(.2, self.tick)
        self.thread = threading.Thread(target=self.execute, name='travel-pipeline', daemon=False)
        self.thread.start()

    def execute(self):
        view = PipelineView(self)
        try:
            if self.runner:
                result = self.runner(view)
            else:
                with CancellableSession(self.stop) as llm_session, CancellableSession(self.stop) as places_session:
                    result = run_pipeline(
                        self.date, self.config,
                        LLMClient(self.config.llm, llm_session, self.secrets),
                        KakaoPlaces(self.config.places, places_session, self.secrets),
                        view,
                    )
            self.call_from_thread(self.receive, 'done', result)
        except Exception as error:
            self.call_from_thread(self.receive, 'fatal', type(error).__name__)

    def receive(self, kind, *values):
        if kind == 'stage':
            self.phase, self.stage_label = values
            self.stage_started = time.monotonic()
            self.records.append(f'[{self.phase}/3] {self.stage_label} 시작')
            if self.phase == 2:
                self.query_one('#places-state', Static).update('음식점 검색 중…')
            elif self.phase == 3:
                self.query_one('#schedule-body', Static).update('최종 여행 리포트를 작성하고 있습니다…\n\n추천 결과와 음식점 데이터를 바탕으로\n오전·오후·저녁 일정을 생성합니다.')
        elif kind in ('log', 'error'):
            self.records.append(self.secrets.text(str(values[0])))
        elif kind == 'recommendation':
            value = values[0]
            self.query_one('#heading', Static).update(
                f'여행 안내서  ·  {self.date}  ·  {value.recommended_city}'
            )
            self.query_one('#recommend-kicker', Static).update('오늘의 목적지')
            self.query_one('#recommend-city-name', Static).update(
                Text('  '.join(value.recommended_city), style=f'bold {AMBER}')
            )
            self.query_one('#recommend-subtitle', Static).update(f'{value.recommended_city}에서 천천히 머무는 하루')
            self.query_one('#recommend-reason-body', Static).update(value.reason)
            self.query_one('#recommend-weather-body', Static).update('계절 날씨  ' + value.weather)
            self.query_one('#recommend-events-body', Static).update('\n'.join('· ' + event for event in value.events))
            self.query_one('#recommend-events-title', Static).update('여행 아이디어')
            self.query_one('#recommend-notice', Static).update('날씨는 계절 참고 정보입니다. 공식 행사 일정은 방문 전 확인하세요.')
            for selector in ('#recommend-reason', '#recommend-facts', '#recommend-events'):
                self.query_one(selector).display = True
        elif kind == 'places':
            result = values[0]
            self.places_data = result.restaurants
            state = f'맛집 후보 {len(self.places_data)}곳 · Kakao Local'
            if not self.places_data:
                state = '데이터 없음 · ' + ('음식점 검색 실패' if result.place_search['status']=='failed' else '검색 결과 0건')
                state += '\n음식점 정보 없이 리포트를 생성합니다. [L] 오류 확인'
            self.query_one('#places-state', Static).update(state)
            listing = self.query_one('#place-list', OptionList)
            listing.clear_options()
            listing.add_options([Option(Text(f'{i:02}  {p.name}\n    {p.address}\n    {p.category or "분류 정보 없음"}\n'), id=str(i-1)) for i,p in enumerate(self.places_data,1)])
            if self.places_data:
                listing.highlighted = 0
        elif kind == 'report':
            markdown = values[0]
            schedule = itinerary(sections(markdown)['1일 일정 제안'])
            text = Group(
                Text('오늘의 여정\n', style=f'bold {TEAL}'),
                *(Group(Text(period, style=f'bold {TEAL}'), Markdown(body), Text(''))
                  for period, body in schedule.items()),
            )
            self.query_one('#schedule-body', Static).update(text)
        elif kind in ('done', 'fatal'):
            self.finished = True
            if kind == 'done':
                self.result = values[0]
                self.records.extend(f'[{e.type}] {e.message}' for e in self.result.errors)
                if self.result.status == 'failed':
                    message = self.result.errors[-1].message
                    if not self.result.recommendation:
                        self.show_recommendation_error(message)
                        self.query_one('#places-state', Static).update('검색하지 않음 · 여행지 추천 실패')
                    self.query_one('#schedule-body', Static).update('일정을 생성하지 못했습니다.\n'+message+'\n[L] 실행 기록과 확보한 결과 확인')
            else:
                self.records.append('예기치 않은 오류: '+values[0])
                if self.phase <= 1:
                    self.show_recommendation_error('예기치 않은 오류가 발생했습니다. [L] 실행 기록 확인')
                if self.phase <= 2:
                    self.query_one('#places-state', Static).update('작업 중단 · 음식점 검색을 완료하지 못했습니다.')
                self.query_one('#schedule-body', Static).update('작업이 중단되었습니다. [L] 실행 기록 확인')
            if self.stop.is_set():
                self.exit(self.result)
        self.tick()
        self.refresh_bindings()

    def show_recommendation_error(self, message):
        self.query_one('#recommend-kicker', Static).update('추천 결과')
        self.query_one('#recommend-city-name', Static).update('추천을 완료하지 못했습니다.')
        self.query_one('#recommend-subtitle', Static).update(message + '\n[L] 실행 기록 확인')
        self.query_one('#recommend-notice', Static).update('')
        for selector in ('#recommend-reason', '#recommend-facts', '#recommend-events'):
            self.query_one(selector).display = False

    def tick(self):
        if not self.is_mounted:
            return

        if self.stop.is_set() and not self.finished:
            status = '중단 처리 중 · 현재 요청의 응답/시간 초과 후 저장합니다'
        elif self.finished:
            if self.result is None or self.result.status == 'failed':
                status = '작업 중단 · [L] 오류·저장 위치 확인'
            else:
                status = ('일부 오류 있음' if self.result.errors else '완료 · 오류 없음') + ' · JSON·리포트 저장됨'
        else:
            frames = ('·  ', '·· ', '···')
            status = f'{frames[int(time.monotonic()*3)%3]} [{self.phase}/3] {self.stage_label} · {time.monotonic()-self.stage_started:.1f}초'
        # 앱 종료 직후 마지막 interval이 실행되면 기본 화면의 위젯이 이미 해제될 수 있다.
        try:
            self.query_one('#status', Static).update(status)
        except NoMatches:
            return

    def action_page(self, page):
        if len(self.screen_stack) > 1:
            return
        self.active = page
        self.query_one('#pages', ContentSwitcher).current = page
        selected_page = 'places' if page == 'detail' else page
        for name, label in [('recommend', '추천'), ('schedule', '일정'), ('places', '맛집')]:
            button = self.query_one('#tab-' + name, Button)
            button.label = ('● ' if name == selected_page else '') + label
            button.set_class(name == selected_page, 'tab-selected')
        hint = ('↑↓ 식당 선택 · Enter 상세' if page=='places' else
                '↑↓ 스크롤 · Tab 버튼 이동 · Esc 목록' if page=='detail' else
                '↑↓ / PgUp·PgDn 스크롤')
        self.query_one('#context', Static).update(hint)
        target = self.query_one('#place-list') if page=='places' else self.query_one('#'+page)
        target.focus()
        self.refresh_bindings()

    def on_option_list_option_selected(self, event):
        if event.option_list.id != 'place-list': return
        self.selected = int(event.option.id)
        p = self.places_data[self.selected]
        text = Text()
        text.append(f'맛집 {self.selected+1:02} / {len(self.places_data):02}\n\n', style='dim')
        text.append(p.name+'\n\n', style=f'bold {TEAL}')
        for label,value in [('분류',p.category),('주소',p.address),('지도',p.url)]:
            text.append(label+'\n',style=TEAL)
            text.append(str(value if value is not None else '정보 없음')+'\n\n')
        coords = f'{p.lat:.6f}, {p.lng:.6f}' if p.lat is not None and p.lng is not None else '정보 없음'
        text.append('좌표: '+coords+'\n출처: Kakao Local\n\n', style='dim')
        text.append('영업시간과 메뉴는 방문 전 확인하세요.',style='dim')
        self.query_one('#detail-body', Static).update(text)
        self.query_one('#map-button', Button).disabled = not bool(safe_url(p.url))
        self.action_page('detail')

    def on_button_pressed(self, event):
        if event.button.id.startswith('tab-'):
            self.action_page(event.button.id[4:])
        elif event.button.id == 'back-button': self.action_back()
        elif event.button.id == 'map-button':
            url = safe_url(self.places_data[self.selected].url)
            if url: self.open_external(url)

    def open_external(self, url):
        try:
            if not webbrowser.open(url):
                self.notify('브라우저를 열지 못했습니다. 표시된 주소를 확인하세요.', severity='warning')
        except Exception:
            self.notify('외부 프로그램을 열지 못했습니다.', severity='warning')

    def action_report(self):
        if self.result and self.result.report_file:
            self.open_external((self.config.project_root/'results'/self.result.report_file).resolve().as_uri())

    def action_back(self):
        if self.active == 'detail': self.action_page('places')

    def action_records(self):
        if len(self.screen_stack)==1: self.push_screen(Records())

    def check_action(self, action, parameters):
        if len(self.screen_stack)>1 and action in ('page','back','report','records'):
            return False
        if action == 'back': return self.active=='detail'
        if action == 'report': return bool(self.finished and self.result and self.result.report_file)
        return True

    def action_quit(self):
        if self.finished:
            self.exit(self.result)
        elif not self.stop.is_set() and not isinstance(self.screen, ConfirmQuit):
            self.push_screen(ConfirmQuit(), self.confirm_stop)

    def confirm_stop(self, confirmed):
        if confirmed:
            self.stop.set()
            if self.finished: self.exit(self.result)
            else: self.tick()

def run_tui(date, config):
    app = TravelApp(date, config)
    result = app.run(mouse=True)
    if app.thread:
        app.thread.join()
    print('\n국내 여행 플래너 종료')
    if result:
        for error in result.errors:
            print(app.secrets.text(f'[{error.type}] {error.message}'))
        for path in result_paths(config.project_root/'results', date):
            if path.exists(): print(f'결과: {path.resolve()}')
    if app.stop.is_set(): return 130
    return 0 if result and result.status in ('completed', 'completed_with_warnings') else 1
