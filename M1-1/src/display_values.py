"""Consistent human-readable rounding; never used for analytical calculations."""
from decimal import Decimal, ROUND_HALF_UP


def format_number(value: float, places: int = 4) -> str:
    # CSVs retain 10 decimals. Normalize binary round-off at that display boundary
    # so e.g. 2.564250000000004 and 2.5642500000 have the same printed value.
    number = Decimal(str(value)).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)
    unit = Decimal(1).scaleb(-places)
    return format(number.quantize(unit, rounding=ROUND_HALF_UP), "f")
