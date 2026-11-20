"""환경변수 로딩. 키는 코드에 두지 않고 모두 환경변수로 받는다."""
import os

from dotenv import load_dotenv

load_dotenv()


def _origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")  # 비우면 OpenAI 공식 주소, OpenAI 호환 프록시 사용 시 지정
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1500"))
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
ALLOWED_ORIGINS = _origins()
BRIEFING_MODEL = os.getenv("BRIEFING_MODEL", "") or OPENAI_MODEL
BRIEFING_MAX_TOKENS = int(os.getenv("BRIEFING_MAX_TOKENS", "1200"))
# 컨텍스트 예산: 이전 대화는 최근 N개, 총 글자수 한도, 오래된 긴 답변은 잘라서 다시 보낸다
CHAT_HISTORY_LIMIT = 10
HISTORY_MAX_CHARS = int(os.getenv("HISTORY_MAX_CHARS", "4000"))
HISTORY_PER_MESSAGE_CHARS = 800
MAX_TOOL_ROUNDS = 3  # 도구 호출 왕복 상한 (무한 루프·비용 방지)
