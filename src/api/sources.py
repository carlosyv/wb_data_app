"""API routes for World Bank data sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBSource
from src.etl.catalog_sync import sync_sources

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def list_sources(session: AsyncSession = Depends(get_session)):
    """Return all World Bank data sources from the local DB."""
    result = await session.execute(
        select(WBSource).order_by(WBSource.id)
    )
    sources = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "url": s.url,
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None,
        }
        for s in sources
    ]


@router.post("/sync")
async def trigger_sync(session: AsyncSession = Depends(get_session)):
    """Re-sync sources from the World Bank API."""
    count = await sync_sources(session)
    return {"synced": count}
