"""Background download manager for World Bank data.

Creates WBDownloadJob rows, fetches data via WBClient, and upserts into
wb_data_points using INSERT … ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import async_session_factory
from src.db.models import WBDataPoint, WBDownloadJob
from src.etl.wb_client import wb_client

logger = logging.getLogger(__name__)

# Keep track of running background tasks so they aren't GC'd
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


async def create_job(
    session: AsyncSession,
    *,
    source_id: int | None,
    indicator_codes: list[str],
    country_codes: list[str],
    year_start: int,
    year_end: int,
) -> WBDownloadJob:
    """Create a new download job (status=pending) and return it."""
    job = WBDownloadJob(
        status="pending",
        source_id=source_id,
        indicator_codes=indicator_codes,
        country_codes=country_codes,
        year_start=year_start,
        year_end=year_end,
        total_requests=len(indicator_codes),
        completed_requests=0,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _run_job(job_id: int) -> None:
    """Execute a download job in the background."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(WBDownloadJob).where(WBDownloadJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Job %d not found", job_id)
            return

        # Mark as running
        job.status = "running"
        await session.commit()

        errors: list[str] = []
        completed = 0

        for indicator_code in (job.indicator_codes or []):
            try:
                data_points = await wb_client.get_data(
                    indicator=indicator_code,
                    countries=job.country_codes or [],
                    year_start=job.year_start or 1960,
                    year_end=job.year_end or 2025,
                )

                # Upsert data points in batches
                for dp in data_points:
                    stmt = pg_insert(WBDataPoint).values(
                        indicator_code=dp.indicator_code,
                        country_code=dp.country_code,
                        year=dp.year,
                        value=dp.value,
                        download_job_id=job_id,
                    ).on_conflict_do_update(
                        constraint="uq_data_point",
                        set_={
                            "value": dp.value,
                            "downloaded_at": datetime.now(timezone.utc),
                            "download_job_id": job_id,
                        },
                    )
                    await session.execute(stmt)

                await session.commit()
                completed += 1

                # Update progress
                await session.execute(
                    update(WBDownloadJob)
                    .where(WBDownloadJob.id == job_id)
                    .values(completed_requests=completed)
                )
                await session.commit()

                logger.info(
                    "Job %d: %d/%d — downloaded %d points for %s",
                    job_id,
                    completed,
                    len(job.indicator_codes or []),
                    len(data_points),
                    indicator_code,
                )

            except Exception as exc:
                msg = f"{indicator_code}: {exc}"
                errors.append(msg)
                logger.exception("Job %d error on %s", job_id, indicator_code)

        # Finalize job
        final_status = "completed" if not errors else ("failed" if completed == 0 else "completed")
        await session.execute(
            update(WBDownloadJob)
            .where(WBDownloadJob.id == job_id)
            .values(
                status=final_status,
                completed_requests=completed,
                error_log="\n".join(errors) if errors else None,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        logger.info("Job %d finished with status=%s", job_id, final_status)


def start_job_background(job_id: int) -> asyncio.Task:  # type: ignore[type-arg]
    """Schedule a download job to run in the background event loop."""
    task = asyncio.create_task(_run_job(job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def get_job(session: AsyncSession, job_id: int) -> WBDownloadJob | None:
    result = await session.execute(
        select(WBDownloadJob).where(WBDownloadJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def list_jobs(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[WBDownloadJob]:
    result = await session.execute(
        select(WBDownloadJob)
        .order_by(WBDownloadJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
