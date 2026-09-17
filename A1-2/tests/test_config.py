from pathlib import Path

import pytest
import yaml

from src.config import load_config
from src.models import ConfigError


def test_submission_config_matches_existing_provider():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / 'config.yml').read_text(encoding='utf-8'))
    assert data['llm']['base_url'] == 'https://api.groq.com/openai/v1'
    assert data['llm']['model'] == 'openai/gpt-oss-120b'
    assert data['places']['api_key'] == '${KAKAO_API_KEY}'


def test_env_precedence_and_hidden_repr(project, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'existing-process-value')
    result = load_config(project)
    assert result.llm.api_key == 'existing-process-value'
    assert result.places.api_key == 'dotenv-kakao-value'
    assert 'existing-process-value' not in repr(result)
    assert 'dotenv-kakao-value' not in repr(result)


def test_env_file_optional(project, monkeypatch):
    (project / '.env').unlink()
    monkeypatch.setenv('LLM_API_KEY', 'process-llm')
    monkeypatch.setenv('KAKAO_REST_API_KEY', 'process-kakao')
    assert load_config(project).llm.api_key == 'process-llm'


def test_missing_env(project):
    (project / '.env').unlink()
    with pytest.raises(ConfigError, match='LLM_API_KEY'):
        load_config(project)


@pytest.mark.parametrize('before,after', [
    ('${LLM_API_KEY}', '${LLM_API_KEY'),
    ('${LLM_API_KEY}', 'direct-secret-must-not-appear'),
    ('max_tokens: 2048', 'max_tokens: true'),
    ('max_tokens: 2048', 'max_tokens: 0'),
    ('limit: 5', 'limit: 16'),
    ('provider: "kakao"', 'provider: "naver"'),
    ('timeout_seconds: 60', 'timeout_seconds: .nan'),
    ('https://llm.example/v1', 'http://llm.example/v1'),
])
def test_invalid_settings_are_safe(project, before, after):
    path = project / 'config.yml'
    path.write_text(path.read_text(encoding='utf-8').replace(before, after), encoding='utf-8')
    with pytest.raises(ConfigError) as caught:
        load_config(project)
    assert 'direct-secret-must-not-appear' not in str(caught.value)
