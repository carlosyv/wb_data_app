"""Read stored World Bank data from the local PostgreSQL database.

Provides DataFrame and CSV export — no WB API calls are made here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import WBDataPoint


async def get_dataframe(
    session: AsyncSession,
    indicator_codes: list[str] | None = None,
    country_codes: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> pd.DataFrame:
    """Query data points and return a wide-format DataFrame.

    Rows   = (country_code, year)
    Columns = indicator codes
    """
    stmt = select(
        WBDataPoint.indicator_code,
        WBDataPoint.country_code,
        WBDataPoint.year,
        WBDataPoint.value,
    )

    if indicator_codes:
        stmt = stmt.where(WBDataPoint.indicator_code.in_(indicator_codes))
    if country_codes:
        stmt = stmt.where(WBDataPoint.country_code.in_(country_codes))
    if year_start is not None:
        stmt = stmt.where(WBDataPoint.year >= year_start)
    if year_end is not None:
        stmt = stmt.where(WBDataPoint.year <= year_end)

    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["indicator_code", "country_code", "year", "value"])

    # Pivot to wide format: columns = indicator codes
    df_wide = df.pivot_table(
        index=["country_code", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    ).reset_index()

    # Flatten MultiIndex columns
    df_wide.columns = [
        col if not isinstance(col, tuple) else col[-1]
        for col in df_wide.columns
    ]

    return df_wide


async def export_csv(
    session: AsyncSession,
    filepath: str | Path,
    indicator_codes: list[str] | None = None,
    country_codes: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> Path:
    """Export data to a CSV file and return the path."""
    df = await get_dataframe(
        session,
        indicator_codes=indicator_codes,
        country_codes=country_codes,
        year_start=year_start,
        year_end=year_end,
    )
    filepath = Path(filepath)
    df.to_csv(filepath, index=False)
    return filepath
