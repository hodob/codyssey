"""LLM에 전달할 필드와 주소만 축약하며 원본 자료는 변경하지 않는다."""

from .places import normalize_city


_REGIONS = set(('서울 서울특별시 부산 부산광역시 대구 대구광역시 인천 인천광역시 '
                '광주 광주광역시 대전 대전광역시 울산 울산광역시 세종 세종특별자치시 '
                '경기 경기도 강원 강원도 강원특별자치도 충북 충청북도 충남 충청남도 '
                '전북 전라북도 전북특별자치도 전남 전라남도 경북 경상북도 경남 경상남도 '
                '제주 제주도 제주특별자치도').split())


def compact_address(address, city):
    if not isinstance(address, str):
        return None
    parts = address.split()
    city = normalize_city(city)
    base = city[:-1] if city.endswith('시') else city
    aliases = {city, base, base + '시'}
    for suffix in ('특별시', '광역시', '특별자치시'):
        if city.endswith(suffix):
            aliases.add(city[:-len(suffix)])
        else:
            aliases.add(base + suffix)
    # 앞의 도/광역시 다음에 추천 도시가 정확히 있을 때만 함께 생략한다.
    # 도로명에 포함된 도시명이나 다른 도시(예: 서귀포시)는 건드리지 않는다.
    index = 1 if len(parts) > 1 and parts[0] in _REGIONS and parts[1] in aliases else 0
    if parts and parts[index] in aliases and len(parts) > index + 1:
        parts = parts[index + 1:]
    return ' '.join(parts)


def place_input(item, city):
    result = {key: item[key] for key in ('kind', 'name', 'category', 'start_date', 'end_date')
              if item.get(key)}
    address = compact_address(item.get('address'), city)
    if address:
        result['address'] = address
    return result
