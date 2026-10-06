from __future__ import annotations

from datetime import date

AS_OF_DATE = date(2026, 1, 1)
DEFAULT_DB_PATH = "data/supply_chain.db"
DEFAULT_TRADE_LOOKBACK_MONTHS = 3


def trade_period_end(as_of: date = AS_OF_DATE) -> date:
    return as_of


def trade_period_start(
    months: int = DEFAULT_TRADE_LOOKBACK_MONTHS,
    as_of: date = AS_OF_DATE,
) -> date:
    month = as_of.month - months
    year = as_of.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)
