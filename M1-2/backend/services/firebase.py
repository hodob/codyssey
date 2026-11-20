"""Firestore 클라이언트. 서비스 계정 키는 환경변수(JSON 문자열 또는 파일 경로)로 받는다."""
import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

import config

DATA = "data"
CONVERSATIONS = "conversations"
_client = None


def _credential():
    raw = config.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON 환경변수가 설정되지 않았습니다.")
    if raw.startswith("{"):
        return credentials.Certificate(json.loads(raw))
    if os.path.exists(raw):
        return credentials.Certificate(raw)
    raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON 이 JSON 도, 존재하는 파일 경로도 아닙니다.")


def get_db():
    """FastAPI 의존성. 테스트에서는 dependency_overrides 로 교체한다."""
    global _client
    if _client is None:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(_credential())
        _client = firestore.client()
    return _client
