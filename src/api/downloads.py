"""API routes for managing download jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.etl.download_manager import create_job, get_job, list_jobs, start_job_background

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class DownloadRequest(BaseModel):
    source_id: int | None = None
    indicator_codes: list[str]
    country_codes: list[str]
    year_start: int = 1960
    year_end: int = 2025


@router.post("")
async def start_download(
    req: DownloadRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a download job and start it in the background."""
    if not req.indicator_codes:
        raise HTTPException(400, "At least one indicator code is required")
    if not req.country_codes:
        raise HTTPException(400, "At least one country code is required")

    job = await create_job(
        session,
        source_id=req.source_id,
        indicator_codes=req.indicator_codes,
        country_codes=req.country_codes,
        year_start=req.year_start,
        year_end=req.year_end,
    )
    start_job_background(job.id)

    return {
        "job_id": job.id,
        "status": job.status,
        "total_requests": job.total_requests,
    }


@router.get("/{job_id}")
async def get_download_status(
    job_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get the current status of a download job."""
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    return {
        "id": job.id,
        "status": job.status,
        "source_id": job.source_id,
        "indicator_codes": job.indicator_codes,
        "country_codes": job.country_codes,
        "year_start": job.year_start,
        "year_end": job.year_end,
        "total_requests": job.total_requests,
        "completed_requests": job.completed_requests,
        "error_log": job.error_log,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("")
async def list_downloads(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List recent download jobs."""
    jobs = await list_jobs(session, limit=limit, offset=offset)
    return [
        {
            "id": j.id,
            "status": j.status,
            "total_requests": j.total_requests,
            "completed_requests": j.completed_requests,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]
