# 2024년 증가량 공식 발표와 현재 자료의 차이

## 확인한 공식 발표

- Robert Monroe, Scripps, 2025-01-16, *New Record for Annual Increase in Keeling Curve Readings*
- URL: https://scripps.ucsd.edu/news/new-record-annual-increase-keeling-curve-readings
- 원문 재확인일(UTC): 2026-11-13

원문은 2024년 12개월 평균과 2023년 평균의 차이를 **3.58ppm**, 이전 기록인 2016년을 **3.41ppm**으로 설명한다. 따라서 연초·연말 또는 전년 동월 차분을 연평균 차분으로 오독한 것은 아니다.

Ralph Keeling은 두 해의 큰 증가에 엘니뇨가 영향을 줬다고 설명한다. 2023~2024년 엘니뇨가 2024년 초 끝났어도 증가율의 영향이 북반구 여름까지 이어질 수 있으며, 남·북미 산불의 추가 영향 가능성을 언급한다. 장기 상승의 근본 원인은 화석연료 연소, 연도별 변동은 육지·해양과의 CO₂ 교환에서도 발생한다고 설명한다. 원인별 ppm 기여량을 제공하지는 않는다.

## 현재 원본에서의 확인

`data/raw/monthly_in_situ_co2_mlo.csv`의 관측 열과 공급자 보충 열은 2015~2016년, 2023~2024년에 결측이 없고 값도 같다.

| 증가량 연도 | 현재 원본의 12개월 평균 차분 | 공식 발표 | 현재−발표 |
|---|---:|---:|---:|
| 2016 | 3.342500ppm | 3.41ppm | −0.067500ppm |
| 2024 | 3.574167ppm | 3.58ppm | −0.005833ppm |

현재 원본의 2024년 값은 소수 둘째 자리로 3.57ppm이다. 2016년 차이는 단순한 소수 둘째 자리 반올림으로 설명되지 않는다.

관측 열 선택·공급자 보충 여부와 별개로 동일한 차이가 남고, 연도별 원본 값을 별도 파서와 Decimal 산술로 재계산해 확인한다. 본문에 정의된 계산을 다른 통계로 바꾸거나 값을 조정해 맞추지 않는다.

## 과거 자료 버전 확보 시도

원본 헤더는 표준 가스 재보정에 따른 개정 가능성을 명시한다. 이것이 이번 차이의 실제 원인이라는 증거는 아직 확보하지 못했다.

Internet Archive의 CDX 인덱스에서 Scripps의 과거 공식 CSV 경로를 조회했다.

- 과거 URL: https://scrippsco2.ucsd.edu/assets/data/atmospheric/stations/in_situ_co2/monthly/monthly_in_situ_co2_mlo.csv
- CDX 조회: https://web.archive.org/cdx/search/cdx?url=scrippsco2.ucsd.edu/assets/data/atmospheric/stations/in_situ_co2/monthly/monthly_in_situ_co2_mlo.csv&output=json&filter=statuscode:200&filter=timestamp:2025&collapse=timestamp:6
- 인덱스에서 확인한 캡처 예: `20250105162453`, `20250607162505`
- 두 캡처의 CSV 재생 요청은 HTTP 429를 반환해 과거 원본을 확보하지 못했다. 인덱스에 캡처가 있다는 사실만으로 그 데이터 값이나 발표값 재현 여부를 확인했다고 하지 않는다.
- 과거 공식 URL의 현재 직접 요청은 HTTP 404를 반환했다.
- 현재 `keelinglabsites.ucsd.edu` CSV 주소에 대한 2025년 CDX 조회는 빈 목록이었다.

따라서 정확한 수치 차이의 원인은 **미해결**이다. 보고서에는 발표값과 현재 계산값을 따로 기재하고, 동일한 기록 순위와 핵심 해석이 유지되는지 확인한다.

## 다른 Scripps 글과의 정의 차이

Scripps의 2021년 글도 확인했다:
https://keelingcurve.ucsd.edu/2021/05/03/why-covid-didnt-have-a-bigger-effect-on-co2-emissions/

이 글의 2020년 2.0ppm 등은 **1월 1일을 중심으로 한 2개월 평균끼리의 차이**라고 명시돼 있다. 12개월 연평균 차분과 직접 비교하거나 그 글의 2016년 3.0ppm을 이번 발표의 3.41ppm과 같은 통계로 취급하지 않는다. 이번 결과에서는 이 글을 기후·생태계 변화가 연도별 대기 증가량에 영향을 준다는 원리의 설명에만 사용한다.

## 서술 원칙

- 주 분석 수치는 보관한 현재 Scripps 원본에서 직접 계산한다.
- 당시 발표값은 날짜와 함께 인용한다.
- 2024년까지의 순위와 최신 완전 연도인 2025년까지의 순위를 구분한다.
- 기록·백분위는 관측 자료의 요약이다. 자연 변동을 통제한 인과효과·예측 초과량·재현 기간으로 해석하지 않는다.
- 2025년 값은 같은 마우나로아 기록에서 계산한다. 전 지구 전망치나 다른 관측망의 값으로 대체하지 않는다.
