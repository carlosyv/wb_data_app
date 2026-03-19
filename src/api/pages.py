"""HTML page routes served via Jinja2 templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBCountry, WBDataPoint, WBDownloadJob, WBIndicator, WBSource

router = APIRouter(tags=["pages"])


def _templates(request: Request):
    """Helper to access the Jinja2 templates instance attached to the app."""
    return request.app.state.templates


# ── Dashboard ────────────────────────────────────────────────────────────


@router.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    templates = _templates(request)
    sources = (await session.execute(select(WBSource).order_by(WBSource.id))).scalars().all()
    recent_jobs = (
        await session.execute(
            select(WBDownloadJob).order_by(WBDownloadJob.created_at.desc()).limit(10)
        )
    ).scalars().all()

    # Count total data points
    total_points = (
        await session.execute(select(func.count()).select_from(WBDataPoint))
    ).scalar_one()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sources": sources,
            "recent_jobs": recent_jobs,
            "total_points": total_points,
        },
    )


# ── Indicator Browser ───────────────────────────────────────────────────


@router.get("/sources/{source_id}/indicators")
async def indicators_page(
    request: Request,
    source_id: int,
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_session),
):
    templates = _templates(request)
    per_page = 50

    source = (
        await session.execute(select(WBSource).where(WBSource.id == source_id))
    ).scalar_one_or_none()

    stmt = select(WBIndicator).where(WBIndicator.source_id == source_id)
    if q:
        stmt = stmt.where(WBIndicator.name.ilike(f"%{q}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(WBIndicator.code).offset((page - 1) * per_page).limit(per_page)
    indicators = (await session.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "indicators.html",
        {
            "source": source,
            "indicators": indicators,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if per_page else 1,
        },
    )


# ── Download Config ──────────────────────────────────────────────────────


@router.get("/download")
async def download_page(request: Request, session: AsyncSession = Depends(get_session)):
    templates = _templates(request)
    sources = (await session.execute(select(WBSource).order_by(WBSource.id))).scalars().all()
    countries = (await session.execute(select(WBCountry).order_by(WBCountry.name))).scalars().all()
    return templates.TemplateResponse(
        request,
        "download.html",
        {"sources": sources, "countries": countries},
    )


# ── Job Monitor ──────────────────────────────────────────────────────────


@router.get("/jobs")
async def jobs_page(request: Request, session: AsyncSession = Depends(get_session)):
    templates = _templates(request)
    jobs = (
        await session.execute(
            select(WBDownloadJob).order_by(WBDownloadJob.created_at.desc()).limit(50)
        )
    ).scalars().all()

    # Count data points per job, grouped by indicator
    job_data_points: dict[int, dict[str, int]] = {}
    for job in jobs:
        rows = (
            await session.execute(
                select(
                    WBDataPoint.indicator_code,
                    func.count().label("cnt"),
                )
                .where(WBDataPoint.download_job_id == job.id)
                .group_by(WBDataPoint.indicator_code)
            )
        ).all()
        job_data_points[job.id] = {row.indicator_code: row.cnt for row in rows}

    return templates.TemplateResponse(
        request, "jobs.html", {"jobs": jobs, "job_data_points": job_data_points}
    )


# ── Data Browser ─────────────────────────────────────────────────────────


@router.get("/browse")
async def browse_page(
    request: Request,
    indicator: str | None = Query(None),
    country: str | None = Query(None),
    year_start: int | None = Query(None),
    year_end: int | None = Query(None),
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_session),
):
    templates = _templates(request)
    per_page = 100

    stmt = select(WBDataPoint)
    if indicator:
        stmt = stmt.where(WBDataPoint.indicator_code == indicator)
    if country:
        stmt = stmt.where(WBDataPoint.country_code == country)
    if year_start is not None:
        stmt = stmt.where(WBDataPoint.year >= year_start)
    if year_end is not None:
        stmt = stmt.where(WBDataPoint.year <= year_end)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(WBDataPoint.indicator_code, WBDataPoint.country_code, WBDataPoint.year)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    data_points = (await session.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "browse.html",
        {
            "data_points": data_points,
            "indicator": indicator or "",
            "country": country or "",
            "year_start": year_start or "",
            "year_end": year_end or "",
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if per_page else 1,
        },
    )
