"""OpenAI-compatible Chat Completions 클라이언트."""

from .http import request_json
from .models import AppError, Completion, ErrorType, LLMConfig
from .safety import SecretFilter


class LLMClient:
    def __init__(self, config: LLMConfig, session, secrets: SecretFilter):
        self.config = config
        self.session = session
        self.secrets = secrets

    def complete(self, messages, response_format=None) -> Completion:
        payload = {
            'model': self.config.model,
            'messages': messages,
            'max_tokens': self.config.max_tokens,
            'stream': False,
        }
        if response_format is not None:
            payload['response_format'] = response_format
        data = request_json(
            self.session, 'POST', self.config.base_url + '/chat/completions',
            headers={'Authorization': f'Bearer {self.config.api_key}'},
            json=payload, timeout=self.config.timeout_seconds,
        )
        try:
            choice = data['choices'][0]
            message = choice['message']
            content = message.get('content') or ''
            finish_reason = choice.get('finish_reason') or ''
            if not isinstance(content, str):
                raise TypeError
            return Completion(
                content=self.secrets.text(content),
                finish_reason=finish_reason,
                refusal=bool(message.get('refusal')),
                usage=data.get('usage'),
            )
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AppError(ErrorType.RESPONSE_ERROR, 'API 응답에서 모델의 답변을 찾을 수 없습니다.') from exc
