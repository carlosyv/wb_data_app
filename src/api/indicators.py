"""API routes for World Bank indicators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBIndicator
from src.etl.catalog_sync import sync_indicators_for_source

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


@router.get("")
async def list_indicators(
    source_id: int | None = Query(None, description="Filter by source ID"),
    q: str | None = Query(None, description="Search indicator names"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    """List / search indicators from local DB."""
    stmt = select(WBIndicator)

    if source_id is not None:
        stmt = stmt.where(WBIndicator.source_id == source_id)

    if q:
        # Use ILIKE for case-insensitive search (trigram index accelerates this)
        stmt = stmt.where(
            or_(
                WBIndicator.name.ilike(f"%{q}%"),
                WBIndicator.code.ilike(f"%{q}%"),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = stmt.order_by(WBIndicator.code).offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    indicators = result.scalars().all()

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
        "items": [
            {
                "code": ind.code,
                "name": ind.name,
                "source_id": ind.source_id,
                "source_note": ind.source_note[:200] + "…" if ind.source_note and len(ind.source_note) > 200 else ind.source_note,
                "topic": ind.topic,
            }
            for ind in indicators
        ],
    }


@router.post("/sync/{source_id}")
async def trigger_indicator_sync(
    source_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Re-sync indicators for a specific source from the WB API."""
    count = await sync_indicators_for_source(session, source_id)
    return {"source_id": source_id, "synced": count}
