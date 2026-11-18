"""실제 콘솔 실행 결과를 제출용 터미널 이미지 원본 HTML로 만든다."""

import html
import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import prompt_manager  # noqa: E402


OUTPUT_DIR = PROJECT_DIR.parents[1] / ".evidence_html"


def terminal_html(title, command, output):
    """실행 출력을 읽기 쉬운 터미널 화면 HTML로 변환한다."""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0d1117; color: #e6edf3;
         font-family: 'Cascadia Mono', Consolas, 'Malgun Gothic', monospace; }}
  .wrap {{ width: 1360px; margin: 28px auto; }}
  h1 {{ font: 700 25px 'Malgun Gothic', sans-serif; margin: 0 0 14px; }}
  .terminal {{ border: 1px solid #30363d; border-radius: 12px; overflow: hidden;
               background: #010409; box-shadow: 0 16px 40px #0008; }}
  .bar {{ height: 46px; background: #161b22; border-bottom: 1px solid #30363d;
          display: flex; align-items: center; padding: 0 17px; gap: 9px; }}
  .dot {{ width: 13px; height: 13px; border-radius: 50%; }}
  .red {{ background: #ff5f56; }} .yellow {{ background: #ffbd2e; }}
  .green {{ background: #27c93f; }}
  .command {{ color: #8b949e; margin-left: 13px; font-size: 15px; }}
  pre {{ margin: 0; padding: 22px 26px 30px; white-space: pre-wrap;
         overflow-wrap: anywhere; font-size: 17px; line-height: 1.48; }}
  .note {{ margin-top: 12px; color: #8b949e; font: 14px 'Malgun Gothic', sans-serif; }}
</style>
</head>
<body><div class="wrap">
<h1>{html.escape(title)}</h1>
<div class="terminal"><div class="bar">
  <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
  <span class="command">{html.escape(command)}</span>
</div><pre>{html.escape(output)}</pre></div>
<div class="note">프로젝트에서 실제 실행한 명령과 출력 · 입력값은 프롬프트 뒤에 함께 표시</div>
</div></body></html>"""


def run_program(inputs, data_file, export_dir):
    """지정된 입력으로 실제 main 함수를 실행하고 출력 전체를 돌려준다."""
    prompt_manager.DATA_FILE = data_file
    prompt_manager.EXPORT_DIR = export_dir
    values = iter(inputs)

    def visible_input(message=""):
        value = next(values)
        print(f"{message}{value}")
        return value

    output = io.StringIO()
    with patch("builtins.input", side_effect=visible_input):
        with redirect_stdout(output):
            prompt_manager.main()
    return output.getvalue()


def write_page(
    file_name,
    title,
    output,
    command="python -X utf8 prompt_manager.py",
):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page = OUTPUT_DIR / file_name
    page.write_text(
        terminal_html(title, command, output),
        encoding="utf-8",
    )


def main():
    with tempfile.TemporaryDirectory() as temporary_directory:
        temp = Path(temporary_directory)

        menu_data = temp / "menu.json"
        write_page(
            "06_메인메뉴.html",
            "프로그램 실행 및 메인 메뉴",
            run_program(["0"], menu_data, temp / "menu_exports"),
        )

        add_data = temp / "add.json"
        write_page(
            "07_추가_전체목록.html",
            "프롬프트 추가 및 전체 목록 반영",
            run_program(
                [
                    "1",
                    "여행 일정 요약",
                    "3박 4일 여행 일정을 표로 정리해주세요.",
                    "1",
                    "",
                    "2",
                    "0",
                    "0",
                ],
                add_data,
                temp / "add_exports",
            ),
        )

        search_data = temp / "search.json"
        write_page(
            "08_카테고리_검색.html",
            "카테고리별 조회 및 키워드 검색",
            run_program(
                ["3", "2", "0", "4", "오사카", "0", "0"],
                search_data,
                temp / "search_exports",
            ),
        )

        detail_data = temp / "detail.json"
        write_page(
            "09_상세_즐겨찾기.html",
            "상세 보기 및 즐겨찾기 관리",
            run_program(
                ["5", "3", "", "6", "1", "", "7", "0", "0"],
                detail_data,
                temp / "detail_exports",
            ),
        )

        bonus_data = temp / "bonus.json"
        bonus_exports = temp / "bonus_exports"
        first_run = run_program(
            [
                "1",
                "여행 일정 요약",
                "3박 4일 여행 일정을 표로 정리해주세요.",
                "1",
                "",
                "8",
                "",
                "0",
            ],
            bonus_data,
            bonus_exports,
        )
        second_run = run_program(["2", "0", "0"], bonus_data, bonus_exports)
        bonus_files = "\n".join(
            f"- {path.name}" for path in sorted(bonus_exports.glob("*.md"))
        )
        write_page(
            "10_JSON_Markdown_보너스.html",
            "보너스 1: JSON 영구 저장 및 Markdown 내보내기",
            first_run
            + "\n=== 프로그램 재실행 후 JSON 불러오기 확인 ===\n"
            + second_run
            + "\n=== 생성된 Markdown 파일 ===\n"
            + bonus_files,
        )

    test_result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "-v"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    write_page(
        "11_자동테스트.html",
        "핵심 기능 자동 테스트",
        test_result.stdout + test_result.stderr,
    )

    git_user_name = subprocess.run(
        ["git", "config", "--get", "user.name"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    git_user_email = subprocess.run(
        ["git", "config", "--get", "user.email"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    git_config_output = (
        "PS prompt-manager> git config --get user.name\n"
        f"{git_user_name}\n\n"
        "PS prompt-manager> git config --get user.email\n"
        f"{git_user_email}\n"
    )
    write_page(
        "12_Git_사용자정보_확인.html",
        "Git 사용자 정보 설정 확인",
        git_config_output,
        "git config --get user.name / user.email",
    )
    print(f"증빙 HTML 생성 완료: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
