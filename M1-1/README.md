# 마우나로아 CO₂ 시계열 분석

Scripps 마우나로아 월별 CO₂ 기록(1958–2026)으로 장기 증가 속도, 계절 진폭, 2024년 증가량을 분석.

**전체 분석: [REPORT.md](REPORT.md)** / 발표 자료: `presentation.html`을 브라우저에서 열기

## 실행

Python 3.10 이상 (검증: 3.13)

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python run_analysis.py
```

- `run_analysis.py`: 보관된 원본으로 분석 → `REPORT.md`·`presentation.html` 생성 → 테스트 순서로 실행
- 다른 Python 버전: `requirements.txt` 사용
- 원본 새로 받기: `python src/collect_data.py --download`

## 데이터

- 원본: `data/raw/monthly_in_situ_co2_mlo.csv` ([출처·컬럼·결측 처리](data/SOURCE.md))
- 라이선스: Scripps CO₂ Program, UC San Diego, CC BY 4.0 (코드에는 미적용)

## 구성

```text
REPORT.md          # 제출 보고서
src/               # 수집·분석·보고서·발표 생성 코드
data/              # 원본과 중간 산출물
images/            # 그래프
results/           # 정량 지표(JSON)·검증 기록
tests/             # 자동 테스트
```
