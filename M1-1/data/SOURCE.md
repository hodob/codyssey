# Scripps 월별 CO₂ 원본과 데이터 확인

## 출처와 이용 조건

- 기관: Scripps CO₂ Program, Scripps Institution of Oceanography, UC San Diego
- 관측자료: 마우나로아 현장(in situ) 월별 대기 CO₂ 농도. 일부 기간은 인근 마우나케아 대체 관측 포함
- 공식 설명: https://scrippsco2.ucsd.edu/data/atmospheric-co2-data/sampling-station-records/mauna-loa-observatory-hawaii/
- 다운로드: https://keelinglabsites.ucsd.edu/websitedataco2/monthly_in_situ_co2_mlo.csv
- 원본: `raw/monthly_in_situ_co2_mlo.csv` (응답 바이트 그대로 보관)
- 취득 정보·SHA-256: `raw/download_metadata.json`
- 기계 판독 점검 결과: `data_audit.json`

공식 자료 페이지가 데이터와 그래픽에 **Creative Commons Attribution 4.0 International (CC BY 4.0)**을 적용하고 Scripps Institution of Oceanography at UC San Diego 표시를 안내하는 것을 확인

라이선스: https://creativecommons.org/licenses/by/4.0/

원본 헤더가 제시한 인용:

> C. D. Keeling, S. C. Piper, R. B. Bacastow, M. Wahlen, T. P. Whorf, M. Heimann, and H. A. Meijer (2001), *Exchanges of atmospheric CO₂ and ¹³CO₂ with the terrestrial biosphere and oceans from 1978 to 2000. I. Global aspects*, SIO Reference Series, No. 01-06, Scripps Institution of Oceanography, San Diego, 88 pages.

학술지 동료심사 문헌이 필요한 경우 헤더가 안내하는 문헌: 같은 저자들의 2005년 *A History of Atmospheric CO₂ and its effects on Plants, Animals, and Ecosystems* 수록 장(pp. 83–113)

## 수집과 재실행

프로젝트 루트에서 Python 3.10 이상으로 실행 (표준 라이브러리만 사용)

```bash
# 원본이 없으면 다운로드. 원본이 있으면 네트워크 없이 동일 자료 점검.
python3 src/collect_data.py

# 원본 버전을 의도적으로 갱신할 때만 사용.
python3 src/collect_data.py --download
```

수집 코드: 다운로드 응답을 파싱·검증한 뒤 원본 저장. 기존 원본의 SHA-256이 수집 기록과 다르면 중단. 최신 원본은 개정될 수 있으므로 보고서 수치는 다운로드 기록과 함께 보관한 버전을 기준으로 함

## 열 정의

원본 설명에는 처음에 '10 columns'라고 적혀 있으나 이어서 11번째 관측소 열을 설명하며, 실제 데이터도 **11열**. 다중 행 헤더를 건너뛰고 연도로 시작하는 데이터 행만 파싱

| 순서 | 코드상의 이름 | 의미 |
|---|---|---|
| 1 | year | 연도 |
| 2 | month | 월 |
| 3 | excel_date | 원본이 제공하는 Excel 날짜 |
| 4 | decimal_year | 소수 연도 |
| 5 | co2 | 월별 관측 CO₂, ppm. 주 분석의 기준 열 |
| 6 | seasonally_adjusted | 공급자가 계절성을 제거한 관측 농도 |
| 7 | fit | 공급자의 경직된 3차 스플라인과 4개 조화항·선형 진폭 변화 모형 적합값 |
| 8 | seasonally_adjusted_fit | 7열에서 계절성을 제거한 적합값 |
| 9 | co2_filled | 5열의 결측을 7열 적합값으로 채운 농도 |
| 10 | seasonally_adjusted_filled | 6열의 결측을 8열 적합값으로 채운 농도 |
| 11 | station | MLO(마우나로아) 또는 MKO(마우나케아) |

- 단위: μmol/mol (= ppm), 2012 SIO 보정 척도
- 월별 값: 각 월 15일 24:00 기준으로 조정됨. 일별 값의 단순 평균으로 해석하지 않음
- 결측 표시: `-99.99`. 점검 코드에서 결측으로 읽으며 농도나 이상치로 취급하지 않음
- 제공처의 계절조정: 선형 진폭 변화 인자가 있는 4개 조화항 적합 이용
- 제공처 적합 열의 선형 진폭 가정을 그대로 읽은 진폭 추세를 독립 추정 결과로 제시하지 않음. 결과 2는 원 논문을 확인해 관측 농도에서 별도로 계절 진폭 추정
- 제공처 보충값은 관측값과 구분. 수집·점검 단계에서 자체 보간·이상치 삭제 없음. 결과 1·3은 제공처 보충 열을 사용하고 원 관측만 쓴 값도 대조, 결과 2는 논문에 따라 1964년 2~4월만 선형 보간 (세부 방법은 REPORT 부록 B). 원본 파일은 수정하지 않음

## 확보한 버전의 관측 범위와 결측

- 취득 시각(UTC): 2026-11-13T03:39:24.550576+00:00
- 원본 내부 설명: 2026-10-20까지의 기초 자료, 2026-10-21 14:16:02 아카이브
- 달력 행: **828개**, 1958-01~2026-12
- 5열의 유효 관측: **818개**, 1958-03~2026-09
- 달력 행의 존재와 해당 월의 관측 존재는 다름. 2026년 10~12월은 확보한 버전에서 비어 있음
- 관측 농도 결측 10개월: 1958-01, 1958-02, 1958-06, 1958-10, 1964-02, 1964-03, 1964-04, 2026-10, 2026-11, 2026-12
- 공급자가 채운 5개월: 1958-06, 1958-10, 1964-02, 1964-03, 1964-04
- 5열이 12개월 모두 있는 연도: 1959~2025년 중 1964년 제외
- 9열이 12개월 모두 있는 연도: 1959~2025년
- 1958년과 2026년은 연간 평균·증가량 비교에서 완전한 연도로 취급하지 않음

## 관측 중단과 대체 관측

원본 헤더는 마우나로아 화산 분화에 따른 Scripps 측정 중단을 **2022년 12월~2023년 2월**로 설명. 해당 월은 원본의 관측소 열에 MKO로 표시되며 값이 존재

| 월 | 관측소 | CO₂(ppm) |
|---|---|---:|
| 2022-12 | MKO | 418.47 |
| 2023-01 | MKO | 419.13 |
| 2023-02 | MKO | 420.33 |

이 구간은 빈 관측을 임의 보간한 것이 아니라 제공처가 포함한 대체 관측. 다른 기관의 관측 재개 날짜를 이 자료에 그대로 적용하지 않음

## 공식 발표값과의 초기 대조

12개월 농도의 산술평균을 구하고 전년도 평균을 뺀 값. 아래 연도에는 5열 결측이 없어 관측 열과 제공처 보간 열의 계산값이 동일

| 항목 | 현재 원본으로 계산 | 2025년 Scripps 발표 |
|---|---:|---:|
| 2016년 연평균 차분 | 3.342500ppm | 3.41ppm |
| 2024년 연평균 차분 | 3.574167ppm | 3.58ppm |

2024년 계산값을 소수 둘째 자리로 반올림하면 3.57ppm이므로 발표값과 정확히 같다고 기록하지 않음. 2016년 차이도 단순한 둘째 자리 반올림으로 설명되지 않음

원본은 표준 가스 재보정에 따라 자료가 개정될 수 있다고 명시. 다만 **자료 개정이 이번 차이의 실제 원인인지는 미확인**. 후속 조사에서 발표 원문도 12개월 평균 차분임을 확인했고, 별도 CSV 파서와 Decimal 산술로 계산 대조. 과거 공식 CSV의 2025년 캡처를 Internet Archive 인덱스에서 찾았으나 파일 요청이 HTTP 429를 반환해 당시 버전 값은 미확보. 확인한 차이는 그대로 보존하며 발표값에 맞추기 위해 값을 바꾸지 않음. 상세 기록: `references/scripps2025_record.md`

공식 발표: https://scripps.ucsd.edu/news/new-record-annual-increase-keeling-curve-readings

## 현재 확인 범위

이 문서는 원본의 수집·정의·품질과 발표값 대조를 기록. 결과 1~3의 계산·그래프·해석은 [REPORT.md](../REPORT.md)에 있음.
