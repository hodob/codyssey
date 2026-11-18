"""나만의 프롬프트 관리 프로그램.

외부 라이브러리 없이 실행되는 Python 콘솔 프로그램이다.
"""

import json
import shutil
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "prompts.json"
EXPORT_DIR = BASE_DIR / "exports"
MIN_PAGE_WIDTH = 50

MAIN_MENU_OPTIONS = [
    "[1] 추가",
    "[2] 목록",
    "[3] 카테고리",
    "[4] 검색",
    "[5] 상세",
    "[6] 즐겨찾기",
    "[7] 즐겨찾기 목록",
    "[8] 내보내기",
    "[0] 종료",
]

CATEGORIES = [
    "텍스트 생성",
    "이미지 생성",
    "영상 생성",
    "페르소나",
    "자동화",
    "기타",
]

DEFAULT_PROMPTS = [
    {
        "title": "JAPAN MATE 메인 홈페이지 UI",
        "content": (
            "Create a high-fidelity desktop website UI for 'JAPAN MATE', "
            "a Japanese package travel guide service targeting Korean users "
            "in their 20s and 30s. Use a clean, modern travel platform style. "
            "Create the main homepage screen with a hero banner, search area, "
            "featured package tours, popular destinations and a footer."
        ),
        "category": "이미지 생성",
        "favorite": False,
    },
    {
        "title": "JAPAN MATE 패키지 검색 결과 UI",
        "content": (
            "Create a high-fidelity package travel listing screen for "
            "'JAPAN MATE'. Include filter controls, sorting options, multiple "
            "package cards, prices, duration, destination labels, ratings and "
            "pagination. Make the products easy to search and compare."
        ),
        "category": "이미지 생성",
        "favorite": False,
    },
    {
        "title": "봄의 오사카성 여행 사진",
        "content": (
            "Create a geographically plausible commercial travel photograph "
            "of Osaka Castle in spring. Frame the castle with mature cherry "
            "blossoms under natural blue sky and soft morning daylight. Use a "
            "wide 16:9 landscape crop with no text, logo or watermark."
        ),
        "category": "이미지 생성",
        "favorite": True,
    },
]


def create_default_prompts():
    """기본 데이터를 안전한 복사본으로 반환한다."""
    return deepcopy(DEFAULT_PROMPTS)


def save_prompts(prompts):
    """현재 프롬프트 목록을 UTF-8 JSON 파일에 저장한다."""
    try:
        DATA_FILE.write_text(
            json.dumps(prompts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"데이터를 저장하지 못했습니다: {error}")
        return False
    return True


def is_valid_prompt(prompt):
    """JSON에서 읽은 항목이 필요한 데이터 구조인지 확인한다."""
    required_keys = {"title", "content", "category", "favorite"}
    return (
        isinstance(prompt, dict)
        and required_keys.issubset(prompt)
        and isinstance(prompt["title"], str)
        and isinstance(prompt["content"], str)
        and isinstance(prompt["category"], str)
        and isinstance(prompt["favorite"], bool)
    )


def load_prompts():
    """JSON 데이터를 불러오며, 없거나 손상됐으면 기본값을 사용한다."""
    if not DATA_FILE.exists():
        prompts = create_default_prompts()
        save_prompts(prompts)
        return prompts

    try:
        prompts = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(prompts, list) or not all(
            is_valid_prompt(prompt) for prompt in prompts
        ):
            raise ValueError("필요한 프롬프트 데이터 구조가 아닙니다.")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"데이터 파일을 불러오지 못해 기본 데이터를 사용합니다: {error}")
        return create_default_prompts()
    return prompts


def get_page_dimensions():
    """현재 터미널 크기를 읽고 페이지에 사용할 폭과 높이를 반환한다."""
    terminal_size = shutil.get_terminal_size(fallback=(80, 24))
    width = max(MIN_PAGE_WIDTH, terminal_size.columns)
    return width, terminal_size.lines


def character_display_width(character):
    """터미널에서 문자 하나가 차지하는 칸 수를 반환한다."""
    if unicodedata.combining(character):
        return 0
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 2
    return 1


def display_width(text):
    """한글과 전각 문자를 고려한 문자열 표시 폭을 계산한다."""
    return sum(character_display_width(character) for character in str(text))


def pad_display(text, target_width):
    """표시 폭을 기준으로 문자열 오른쪽에 공백을 채운다."""
    text = str(text)
    return text + " " * max(0, target_width - display_width(text))


def split_display_token(token, available_width):
    """공백 없는 긴 단어를 표시 폭에 맞는 조각으로 나눈다."""
    if available_width <= 0:
        return [token]

    pieces = []
    current = ""
    current_width = 0
    for character in token:
        character_width = character_display_width(character)
        if current and current_width + character_width > available_width:
            pieces.append(current)
            current = character
            current_width = character_width
        else:
            current += character
            current_width += character_width
    if current or not pieces:
        pieces.append(current)
    return pieces


def wrap_display_text(text, width, initial_indent="", subsequent_indent=""):
    """한글 표시 폭을 고려해 문자열을 여러 줄로 나눈다."""
    width = max(1, width)
    result = []
    paragraphs = str(text).splitlines() or [""]

    for paragraph_number, paragraph in enumerate(paragraphs):
        words = paragraph.split()
        indent = initial_indent
        current = indent
        current_width = display_width(indent)

        if not words:
            result.append(indent.rstrip())
            continue

        for word in words:
            separator = "" if current_width == display_width(indent) else " "
            required_width = display_width(separator) + display_width(word)
            if current_width + required_width <= width:
                current += separator + word
                current_width += required_width
                continue

            if current_width > display_width(indent):
                result.append(current.rstrip())
                indent = subsequent_indent
                current = indent
                current_width = display_width(indent)

            remaining_width = max(1, width - current_width)
            pieces = split_display_token(word, remaining_width)
            for piece in pieces[:-1]:
                result.append((current + piece).rstrip())
                indent = subsequent_indent
                current = indent
                current_width = display_width(indent)
            last_piece = pieces[-1]
            current += last_piece
            current_width += display_width(last_piece)

        result.append(current.rstrip())
        if paragraph_number < len(paragraphs) - 1 and paragraph == "":
            result.append("")

    return result


def layout_options(options, width, gap="  "):
    """현재 폭에 들어가는 만큼 선택 항목을 한 줄에 배치한다."""
    rows = []
    current = ""
    usable_width = max(1, width - 2)
    gap_width = display_width(gap)

    for option in options:
        option_width = display_width(option)
        if not current:
            current = option
            continue
        if display_width(current) + gap_width + option_width <= usable_width:
            current += gap + option
        else:
            rows.append(current)
            current = option
    if current:
        rows.append(current)
    return rows


def calculate_items_per_page(terminal_height, footer_line_count=1):
    """터미널 높이에서 머리말과 하단 메뉴를 제외한 항목 수를 계산한다."""
    reserved_lines = 10 + footer_line_count
    return max(2, terminal_height - reserved_lines)


def calculate_footer_start_row(
    terminal_height,
    footer_line_count,
    reserve_input_line=True,
):
    """하단 메뉴와 입력란이 마지막 행에 오도록 시작 행을 계산한다."""
    footer_height = footer_line_count + 2
    if reserve_input_line:
        footer_height += 1
    return max(1, terminal_height - footer_height + 1)


def clear_screen():
    """실제 터미널에서 이전 페이지를 지우고 화면 맨 위로 이동한다."""
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def show_page_header(title, description=""):
    """현재 터미널 크기에 맞춘 페이지 상단을 출력한다."""
    width, height = get_page_dimensions()
    clear_screen()
    print("=" * width)
    for line in wrap_display_text(f"PROMPT MANAGER  >  {title}", width - 2, " ", " "):
        print(line)
    if description:
        for line in wrap_display_text(description, width - 2, " ", " "):
            print(line)
    print("-" * width)
    return width, height


def show_page_footer(lines, width=None, height=None, reserve_input_line=True):
    """선택 영역을 현재 페이지 폭과 터미널 하단에 맞춰 출력한다."""
    if width is None or height is None:
        current_width, current_height = get_page_dimensions()
        width = width or current_width
        height = height or current_height

    rendered_lines = []
    for line in lines:
        rendered_lines.extend(wrap_display_text(line, width - 2, " ", " "))

    if sys.stdout.isatty():
        start_row = calculate_footer_start_row(
            height,
            len(rendered_lines),
            reserve_input_line,
        )
        print(f"\033[{start_row};1H", end="")

    print("-" * width)
    for rendered_line in rendered_lines:
        print(rendered_line)
    print("=" * width)


def pause_to_menu():
    """결과 페이지를 확인한 뒤 메인 페이지로 돌아간다."""
    width, height = get_page_dimensions()
    print()
    show_page_footer(
        ["[Enter] 메인 페이지로 돌아가기"],
        width,
        height,
    )
    input("선택 > ")


def print_prompt_rows(prompts, start_number=1, width=None):
    """현재 페이지 폭에 맞춰 프롬프트 목록을 출력한다."""
    if not prompts:
        print("등록된 프롬프트가 없습니다.")
        return

    if width is None:
        width, _ = get_page_dimensions()
    for number, prompt in enumerate(prompts, start=start_number):
        for line in wrap_display_text(
            prompt_line(number, prompt),
            width,
            subsequent_indent="   ",
        ):
            print(line)


def show_menu(prompts=None, message=""):
    """현황과 번호 메뉴가 구분된 메인 페이지를 출력한다."""
    prompts = prompts or []
    favorite_count = sum(prompt["favorite"] for prompt in prompts)

    width, height = show_page_header(
        "홈",
        "프롬프트를 한곳에서 등록하고 찾아보세요.",
    )
    print(f"{pad_display('전체 프롬프트', 18)}{len(prompts)}개")
    print(f"{pad_display('즐겨찾기', 18)}{favorite_count}개")

    if prompts:
        print("\n최근 프롬프트")
        for number, prompt in enumerate(prompts[-3:], start=1):
            for line in wrap_display_text(
                prompt_line(number, prompt),
                width,
                subsequent_indent="   ",
            ):
                print(line)
    else:
        print("\n아직 등록된 프롬프트가 없습니다.")

    if message:
        for line in wrap_display_text(f"안내: {message}", width):
            print(f"\n{line}")

    show_page_footer(
        layout_options(MAIN_MENU_OPTIONS, width),
        width,
        height,
    )


def input_nonempty(message):
    """빈 문자열이 아닌 값을 입력받는다."""
    while True:
        value = input(message).strip()
        if value:
            return value
        print("입력값은 비워둘 수 없습니다. 다시 입력해주세요.")


def print_page_fields(fields, width):
    """입력 단계에서 이미 작성한 필드를 내용 영역에 표시한다."""
    for label, value in fields:
        for line in wrap_display_text(f"{label}: {value}", width):
            print(line)


def input_page_value(title, description, field_label, fields=None):
    """페이지 하단 입력란에서 비어 있지 않은 값을 입력받는다."""
    message = ""
    while True:
        width, height = show_page_header(title, description)
        if fields:
            print_page_fields(fields, width)
        if message:
            print(f"\n안내: {message}")
            message = ""

        show_page_footer([f"[입력] {field_label}"], width, height)
        value = input(f"{field_label} > ").strip()
        if value:
            return value
        message = "입력값은 비워둘 수 없습니다. 다시 입력해주세요."


def select_category(title=""):
    """하단 선택 메뉴에서 기본 또는 직접 입력 카테고리를 선택한다."""
    category_options = [
        f"[{index}] {category}"
        for index, category in enumerate(CATEGORIES, start=1)
    ]
    category_options.append(f"[{len(CATEGORIES) + 1}] 직접 입력")
    category_options.append("[0] 취소")
    message = ""

    while True:
        width, height = show_page_header(
            "프롬프트 추가 · 3/3",
            "카테고리를 선택하세요.",
        )
        if title:
            print_page_fields([("제목", title)], width)
        if message:
            print(f"\n안내: {message}")
            message = ""

        show_page_footer(
            layout_options(category_options, width),
            width,
            height,
        )
        choice = input("선택 > ").strip()
        if choice == "0":
            return None
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(CATEGORIES):
                return CATEGORIES[number - 1]
            if number == len(CATEGORIES) + 1:
                return input_page_value(
                    "프롬프트 추가 · 직접 카테고리",
                    "새 카테고리 이름을 입력하세요.",
                    "새 카테고리",
                    [("제목", title)],
                )
        message = "올바른 카테고리 번호를 입력해주세요."


def add_prompt(prompts):
    """새 프롬프트를 입력받아 목록에 추가한다."""
    title = input_page_value(
        "프롬프트 추가 · 1/3",
        "프롬프트 제목을 입력하세요.",
        "제목",
    )
    content = input_page_value(
        "프롬프트 추가 · 2/3",
        "프롬프트 전체 내용을 입력하세요.",
        "내용",
        [("제목", title)],
    )
    category = select_category(title)
    if category is None:
        return False

    prompts.append(
        {
            "title": title,
            "content": content,
            "category": category,
            "favorite": False,
        }
    )
    save_prompts(prompts)
    width, _ = show_page_header(
        "프롬프트 추가 완료",
        "새 프롬프트를 저장했습니다.",
    )
    print_page_fields(
        [
            ("제목", title),
            ("카테고리", category),
            ("즐겨찾기", "아니요"),
        ],
        width,
    )
    return True


def prompt_line(number, prompt):
    """목록에서 사용할 한 줄 문자열을 만든다."""
    star = " ⭐" if prompt["favorite"] else ""
    return f"{number}. [{prompt['category']}] {prompt['title']}{star}"


def show_prompt_list(prompts, heading="프롬프트 목록", interactive=False):
    """터미널 높이에 맞춰 프롬프트 목록을 페이지 단위로 출력한다."""
    page_index = 0
    message = ""
    navigation_options = ["[P] 이전", "[N] 다음", "[0] 메인 페이지"]

    while True:
        width, height = show_page_header(
            heading,
            "번호, 카테고리, 제목과 즐겨찾기를 확인하세요.",
        )
        footer_rows = layout_options(navigation_options, width)
        items_per_page = calculate_items_per_page(height, len(footer_rows))
        total_pages = max(1, (len(prompts) + items_per_page - 1) // items_per_page)
        page_index = min(page_index, total_pages - 1)
        start = page_index * items_per_page
        end = min(start + items_per_page, len(prompts))

        print_prompt_rows(prompts[start:end], start + 1, width)
        print(
            f"\n전체 {len(prompts)}개  |  "
            f"페이지 {page_index + 1}/{total_pages}"
        )
        if message:
            print(f"안내: {message}")
            message = ""

        if not interactive:
            return

        show_page_footer(footer_rows, width, height)
        choice = input("선택 > ").strip().casefold()
        if choice in {"", "0"}:
            return
        if choice == "p" and page_index > 0:
            page_index -= 1
        elif choice == "n" and page_index < total_pages - 1:
            page_index += 1
        else:
            message = "이동할 수 없는 페이지이거나 잘못된 선택입니다."


def available_categories(prompts):
    """기본 카테고리와 데이터에 존재하는 카테고리를 합쳐 반환한다."""
    categories = list(CATEGORIES)
    for prompt in prompts:
        category = prompt["category"]
        if category not in categories:
            categories.append(category)
    return categories


def show_by_category(prompts, interactive=False):
    """사용자가 선택한 카테고리의 프롬프트만 출력한다."""
    categories = available_categories(prompts)
    options = [
        f"[{index}] {category}"
        for index, category in enumerate(categories, start=1)
    ]
    options.append("[0] 메인 페이지")
    message = ""

    while True:
        width, height = show_page_header(
            "카테고리별 조회",
            "조회할 카테고리를 선택하세요.",
        )
        if message:
            print(f"안내: {message}")
            message = ""
        show_page_footer(layout_options(options, width), width, height)
        choice = input("선택 > ").strip()
        if choice == "0":
            return False
        if choice.isdigit() and 1 <= int(choice) <= len(categories):
            selected = categories[int(choice) - 1]
            break
        message = "올바른 카테고리 번호를 입력해주세요."

    matches = [prompt for prompt in prompts if prompt["category"] == selected]
    show_prompt_list(matches, f"{selected} 카테고리", interactive)
    return True


def search_prompts(prompts, interactive=False):
    """제목 또는 내용에서 대소문자 구분 없이 키워드를 찾는다."""
    keyword = input_page_value(
        "프롬프트 검색",
        "제목 또는 내용에 포함된 단어를 찾습니다.",
        "검색어",
    )
    normalized_keyword = keyword.casefold()
    matches = [
        prompt
        for prompt in prompts
        if normalized_keyword in prompt["title"].casefold()
        or normalized_keyword in prompt["content"].casefold()
    ]
    show_prompt_list(matches, f"'{keyword}' 검색 결과", interactive)


def input_prompt_index(prompts, message="프롬프트 번호: "):
    """유효한 프롬프트 번호를 입력받아 리스트 인덱스로 반환한다."""
    if not prompts:
        print("등록된 프롬프트가 없습니다.")
        return None

    value = input(message).strip()
    if not value.isdigit():
        print("번호는 숫자로 입력해주세요.")
        return None

    index = int(value) - 1
    if not 0 <= index < len(prompts):
        print("존재하지 않는 프롬프트 번호입니다.")
        return None
    return index


def select_prompt_from_pages(prompts, title, description):
    """높이에 맞춘 목록에서 번호로 프롬프트를 선택한다."""
    if not prompts:
        width, height = show_page_header(title, description)
        print("등록된 프롬프트가 없습니다.")
        show_page_footer(["[0] 메인 페이지"], width, height)
        input("선택 > ")
        return None

    page_index = 0
    message = ""
    navigation_options = [
        "[번호] 선택",
        "[P] 이전",
        "[N] 다음",
        "[0] 메인 페이지",
    ]

    while True:
        width, height = show_page_header(title, description)
        footer_rows = layout_options(navigation_options, width)
        items_per_page = calculate_items_per_page(height, len(footer_rows))
        total_pages = max(1, (len(prompts) + items_per_page - 1) // items_per_page)
        page_index = min(page_index, total_pages - 1)
        start = page_index * items_per_page
        end = min(start + items_per_page, len(prompts))

        print_prompt_rows(prompts[start:end], start + 1, width)
        print(
            f"\n전체 {len(prompts)}개  |  "
            f"페이지 {page_index + 1}/{total_pages}"
        )
        if message:
            print(f"안내: {message}")
            message = ""

        show_page_footer(footer_rows, width, height)
        choice = input("선택 > ").strip().casefold()
        if choice in {"", "0"}:
            return None
        if choice == "p" and page_index > 0:
            page_index -= 1
            continue
        if choice == "n" and page_index < total_pages - 1:
            page_index += 1
            continue
        if choice.isdigit():
            index = int(choice) - 1
            if start <= index < end:
                return index
            message = "현재 페이지에 표시된 프롬프트 번호를 입력해주세요."
            continue
        message = "P, N, 0 또는 표시된 프롬프트 번호를 입력해주세요."


def show_prompt_detail(prompts):
    """선택한 프롬프트의 전체 내용을 출력한다."""
    index = select_prompt_from_pages(
        prompts,
        "프롬프트 상세 보기",
        "상세히 볼 프롬프트 번호를 선택하세요.",
    )
    if index is None:
        return False

    prompt = prompts[index]
    favorite = "⭐" if prompt["favorite"] else "아니요"
    width, _ = show_page_header("프롬프트 상세", f"선택한 번호: {index + 1}")
    for label, value in [
        ("제목", prompt["title"]),
        ("카테고리", prompt["category"]),
        ("즐겨찾기", favorite),
    ]:
        for line in wrap_display_text(f"{label}: {value}", width):
            print(line)
    print("-" * width)
    print("내용:")
    for line in wrap_display_text(prompt["content"], width):
        print(line)
    return True


def toggle_favorite(prompts):
    """선택한 프롬프트의 즐겨찾기 상태를 반전한다."""
    index = select_prompt_from_pages(
        prompts,
        "즐겨찾기 관리",
        "상태를 변경할 프롬프트 번호를 선택하세요.",
    )
    if index is None:
        return False

    prompt = prompts[index]
    prompt["favorite"] = not prompt["favorite"]
    save_prompts(prompts)
    width, _ = show_page_header("즐겨찾기 변경 완료")
    if prompt["favorite"]:
        message = f"'{prompt['title']}' 프롬프트를 즐겨찾기에 추가했습니다!"
    else:
        message = f"'{prompt['title']}' 프롬프트를 즐겨찾기에서 해제했습니다!"
    for line in wrap_display_text(message, width):
        print(line)
    return True


def show_favorites(prompts, interactive=False):
    """즐겨찾기한 프롬프트만 모아 출력한다."""
    favorites = [prompt for prompt in prompts if prompt["favorite"]]
    show_prompt_list(favorites, "즐겨찾기 목록", interactive)


def safe_file_name(category):
    """카테고리 이름을 Windows에서도 안전한 파일명으로 바꾼다."""
    invalid_characters = '<>:"/\\|?*'
    name = category.strip().replace(" ", "_")
    for character in invalid_characters:
        name = name.replace(character, "_")
    return name.strip("._") or "기타"


def export_markdown(prompts):
    """프롬프트를 카테고리별 Markdown 파일로 내보낸다."""
    show_page_header(
        "Markdown 내보내기",
        "프롬프트를 카테고리별 파일로 저장합니다.",
    )
    if not prompts:
        print("내보낼 프롬프트가 없습니다.")
        return

    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        created_files = []
        for category in available_categories(prompts):
            category_prompts = [
                prompt for prompt in prompts if prompt["category"] == category
            ]
            if not category_prompts:
                continue

            lines = [f"# {category} 프롬프트", ""]
            for number, prompt in enumerate(category_prompts, start=1):
                favorite = "예 ⭐" if prompt["favorite"] else "아니요"
                lines.extend(
                    [
                        f"## {number}. {prompt['title']}",
                        "",
                        f"- 카테고리: {prompt['category']}",
                        f"- 즐겨찾기: {favorite}",
                        "",
                        "### 내용",
                        "",
                        prompt["content"],
                        "",
                        "---",
                        "",
                    ]
                )

            export_file = EXPORT_DIR / f"{safe_file_name(category)}.md"
            export_file.write_text("\n".join(lines), encoding="utf-8")
            created_files.append(export_file.name)
    except OSError as error:
        print(f"Markdown 파일을 내보내지 못했습니다: {error}")
        return

    print(f"{len(created_files)}개 파일을 exports 폴더에 저장했습니다.")
    for file_name in created_files:
        print(f"- {file_name}")


def main():
    """메뉴 입력을 반복해서 처리한다."""
    prompts = load_prompts()
    message = ""

    while True:
        show_menu(prompts, message)
        message = ""
        choice = input("선택 > ").strip()

        if choice == "0":
            save_prompts(prompts)
            width, _ = show_page_header("종료")
            for line in wrap_display_text(
                "프롬프트를 저장하고 프로그램을 종료합니다.",
                width,
            ):
                print(line)
            break
        needs_pause = True
        if choice == "1":
            needs_pause = add_prompt(prompts)
        elif choice == "2":
            show_prompt_list(prompts, interactive=True)
            needs_pause = False
        elif choice == "3":
            show_by_category(prompts, interactive=True)
            needs_pause = False
        elif choice == "4":
            search_prompts(prompts, interactive=True)
            needs_pause = False
        elif choice == "5":
            needs_pause = show_prompt_detail(prompts)
        elif choice == "6":
            needs_pause = toggle_favorite(prompts)
        elif choice == "7":
            show_favorites(prompts, interactive=True)
            needs_pause = False
        elif choice == "8":
            export_markdown(prompts)
        else:
            message = "잘못된 번호입니다. 하단 메뉴의 번호를 입력해주세요."
            continue

        if needs_pause:
            pause_to_menu()


if __name__ == "__main__":
    main()
