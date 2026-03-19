"""API routes for querying stored World Bank data (reads from local DB only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBDataPoint

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("")
async def query_data(
    indicator: str | None = Query(None, description="Indicator code"),
    country: str | None = Query(None, description="ISO3 country code"),
    year_start: int | None = Query(None),
    year_end: int | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    """Query data points from the local database.

    All parameters are optional filters. Data is served entirely from the
    local PostgreSQL DB — no World Bank API calls are made here.
    """
    stmt = select(WBDataPoint)

    if indicator:
        stmt = stmt.where(WBDataPoint.indicator_code == indicator)
    if country:
        stmt = stmt.where(WBDataPoint.country_code == country)
    if year_start is not None:
        stmt = stmt.where(WBDataPoint.year >= year_start)
    if year_end is not None:
        stmt = stmt.where(WBDataPoint.year <= year_end)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = (
        stmt.order_by(WBDataPoint.indicator_code, WBDataPoint.country_code, WBDataPoint.year)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    points = result.scalars().all()

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
        "items": [
            {
                "indicator_code": p.indicator_code,
                "country_code": p.country_code,
                "year": p.year,
                "value": p.value,
            }
            for p in points
        ],
    }


@router.get("/export")
async def export_csv(
    indicator: str | None = Query(None),
    country: str | None = Query(None),
    year_start: int | None = Query(None),
    year_end: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Export queried data as a CSV download (from local DB)."""
    import csv
    import io

    stmt = select(WBDataPoint)
    if indicator:
        stmt = stmt.where(WBDataPoint.indicator_code == indicator)
    if country:
        stmt = stmt.where(WBDataPoint.country_code == country)
    if year_start is not None:
        stmt = stmt.where(WBDataPoint.year >= year_start)
    if year_end is not None:
        stmt = stmt.where(WBDataPoint.year <= year_end)

    stmt = stmt.order_by(
        WBDataPoint.indicator_code, WBDataPoint.country_code, WBDataPoint.year
    )
    result = await session.execute(stmt)
    points = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["indicator_code", "country_code", "year", "value"])
    for p in points:
        writer.writerow([p.indicator_code, p.country_code, p.year, p.value])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=wb_data_export.csv"},
    )
