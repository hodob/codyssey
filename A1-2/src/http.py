"""재시도 없는 HTTP 경계. 오류 응답 본문과 인증 헤더는 노출하지 않는다."""

import requests

from .models import AppError, ErrorType


def request_json(session, method, url, *, service_label='API', **kwargs):
    try:
        response = session.request(method, url, allow_redirects=False, **kwargs)
    except requests.Timeout as exc:
        raise AppError(ErrorType.TIMEOUT, f'{service_label} 응답 대기 시간이 초과되었습니다.') from exc
    except requests.RequestException as exc:
        raise AppError(ErrorType.NETWORK_ERROR, f'{service_label} 연결에 실패했습니다. 네트워크와 주소를 확인하세요.') from exc
    try:
        status = response.status_code
        if not 200 <= status < 300:
            if status in (401, 403):
                kind, message = ErrorType.AUTH_ERROR, f'{service_label} 인증에 실패했습니다. 키 종류·인증 방식·사용 권한을 확인하세요.'
            elif status == 429:
                kind, message = ErrorType.QUOTA_ERROR, f'{service_label} 사용량 또는 요청 횟수 제한에 도달했습니다.'
            elif status == 413:
                kind, message = ErrorType.INPUT_TOO_LARGE, f'{service_label} 입력 크기 또는 입력 토큰 한도를 초과했습니다.'
            elif 300 <= status < 400:
                kind, message = ErrorType.REDIRECT_ERROR, f'{service_label}가 다른 주소로 이동을 요청했습니다. 기본 주소를 확인하세요.'
            elif status in (400, 404):
                kind, message = ErrorType.REQUEST_ERROR, f'{service_label} 주소·요청 형식을 확인하세요.'
            else:
                kind, message = ErrorType.HTTP_ERROR, f'{service_label}가 요청을 처리하지 못했습니다.'
            # 호출자가 비밀값을 제거한 뒤 감사 기록에 저장한다. 인증 헤더는 수집하지 않는다.
            details = {'headers': {k: v for k, v in response.headers.items()
                                  if k.lower().startswith('x-ratelimit-') or k.lower() == 'retry-after'}}
            try:
                body = response.json()
                error = body.get('error') if isinstance(body, dict) else None
                if isinstance(error, dict):
                    details['provider_error'] = {k: error[k] for k in ('message', 'type', 'code') if k in error}
            except ValueError:
                pass
            raise AppError(kind, f'{message} (HTTP {status})', status, details)
        try:
            result = response.json()
        except ValueError as exc:
            raise AppError(ErrorType.RESPONSE_ERROR, f'{service_label} 응답 본문을 JSON으로 읽을 수 없습니다.') from exc
        if not isinstance(result, dict):
            raise AppError(ErrorType.RESPONSE_ERROR, f'{service_label} 응답 형식이 올바르지 않습니다.')
        return result
    finally:
        response.close()
