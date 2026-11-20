"""환경변수 로딩. 키는 코드에 두지 않고 모두 환경변수로 받는다."""
import os

from dotenv import load_dotenv

load_dotenv()


def _origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")  # 비우면 OpenAI 공식 주소, OpenAI 호환 프록시 사용 시 지정
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1500"))
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
ALLOWED_ORIGINS = _origins()
CHAT_HISTORY_LIMIT = 10  # GPT 에 다시 보내는 최근 메시지 수 (토큰 절약)
