"""API routes for managing download jobs."""

from __future__ import annotations

import csv
import io
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_session
from src.db.models import WBDataPoint
from src.etl.download_manager import create_job, get_job, list_jobs, start_job_background

logger = logging.getLogger(__name__)

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


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile,
    country_codes: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Parse a World Bank CSV file and upsert data points into the database.

    Expected WB CSV format:
        Row 1: "Data Source","World Development Indicators",
        Row 2: (blank)
        Row 3: "Last Updated Date","YYYY-MM-DD",
        Row 4: (blank)
        Row 5: "Country Name","Country Code","Indicator Name","Indicator Code","1960","1961",...
        Row 6+: data rows
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    # Find the header row (contains "Country Code" and "Indicator Code")
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) >= 5 and "Country Code" in row and "Indicator Code" in row:
            header_idx = i
            break

    if header_idx is None:
        raise HTTPException(
            400,
            "Could not find header row with 'Country Code' and 'Indicator Code'. "
            "Make sure this is a World Bank CSV download.",
        )

    header = rows[header_idx]
    # Find column indices
    country_col = header.index("Country Code")
    indicator_col = header.index("Indicator Code")

    # Year columns: everything after "Indicator Code" that looks like a year
    year_columns: list[tuple[int, int]] = []  # (col_index, year)
    for col_i in range(indicator_col + 1, len(header)):
        val = header[col_i].strip()
        if val.isdigit() and 1900 <= int(val) <= 2100:
            year_columns.append((col_i, int(val)))

    if not year_columns:
        raise HTTPException(400, "No year columns found in CSV header")

    # Build allowed country set if a filter was provided
    allowed_countries: set[str] = set()
    if country_codes.strip():
        allowed_countries = {
            c.strip().upper()
            for c in country_codes.replace(",", "\n").split("\n")
            if c.strip()
        }

    # Parse data rows
    upserted = 0
    skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not row or len(row) <= indicator_col:
            continue

        country_code = row[country_col].strip()
        indicator_code = row[indicator_col].strip()

        if not country_code or not indicator_code:
            continue

        if allowed_countries and country_code not in allowed_countries:
            continue

        for col_i, year in year_columns:
            if col_i >= len(row):
                continue
            val_str = row[col_i].strip()
            if not val_str:
                skipped += 1
                continue

            try:
                value = float(val_str)
            except ValueError:
                skipped += 1
                continue

            stmt = pg_insert(WBDataPoint).values(
                indicator_code=indicator_code,
                country_code=country_code,
                year=year,
                value=value,
            ).on_conflict_do_update(
                constraint="uq_data_point",
                set_={"value": value},
            )
            try:
                await session.execute(stmt)
                upserted += 1
            except Exception as exc:
                errors.append(f"Row {row_num}, {indicator_code}/{country_code}/{year}: {exc}")
                await session.rollback()

    await session.commit()

    logger.info("CSV upload: %d upserted, %d skipped, %d errors", upserted, skipped, len(errors))

    return {
        "upserted": upserted,
        "skipped": skipped,
        "errors": errors[:20],  # limit error output
    }


@router.post("/{job_id}/retry")
async def retry_download(
    job_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Create a new job with the same parameters as a failed job."""
    original = await get_job(session, job_id)
    if original is None:
        raise HTTPException(404, "Job not found")
    if original.status not in ("failed", "running", "empty"):
        raise HTTPException(400, "Only failed, empty, or running jobs can be retried")

    new_job = await create_job(
        session,
        source_id=original.source_id,
        indicator_codes=original.indicator_codes or [],
        country_codes=original.country_codes or [],
        year_start=original.year_start or 1960,
        year_end=original.year_end or 2025,
    )
    start_job_background(new_job.id)
    return {"job_id": new_job.id, "status": new_job.status}


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
