"""API routes for World Bank data sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBSource, WBSourceAccess, WBSourceFavorite
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


@router.post("/{source_id}/favorite")
async def toggle_favorite(source_id: int, session: AsyncSession = Depends(get_session)):
    """Toggle a source as favorite. Returns whether it is now favorited."""
    source = (await session.execute(
        select(WBSource).where(WBSource.id == source_id)
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Source not found")

    existing = (await session.execute(
        select(WBSourceFavorite).where(WBSourceFavorite.source_id == source_id)
    )).scalar_one_or_none()

    if existing:
        await session.execute(
            delete(WBSourceFavorite).where(WBSourceFavorite.source_id == source_id)
        )
        await session.commit()
        return {"favorited": False}
    else:
        session.add(WBSourceFavorite(source_id=source_id))
        await session.commit()
        return {"favorited": True}


@router.post("/{source_id}/access")
async def record_access(source_id: int, session: AsyncSession = Depends(get_session)):
    """Record that a source was accessed."""
    session.add(WBSourceAccess(source_id=source_id))
    await session.commit()
    return {"ok": True}
