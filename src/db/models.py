"""SQLAlchemy ORM models for World Bank data.

Tables
------
- wb_sources        — WB dataset catalogues (WDI, IDS, GEM, …)
- wb_countries      — Country / region master list
- wb_indicators     — Indicator definitions, linked to a source
- wb_download_jobs  — Background download job tracking
- wb_data_points    — The actual numeric observations
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


# ── Base ─────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ── Sources ──────────────────────────────────────────────────────────────


class WBSource(Base):
    __tablename__ = "wb_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    indicators: Mapped[list[WBIndicator]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<WBSource id={self.id} name={self.name!r}>"


# ── Countries ────────────────────────────────────────────────────────────


class WBCountry(Base):
    __tablename__ = "wb_countries"

    iso3_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    iso2_code: Mapped[str | None] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    income_level: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<WBCountry {self.iso3_code} {self.name!r}>"


# ── Indicators ───────────────────────────────────────────────────────────


class WBIndicator(Base):
    __tablename__ = "wb_indicators"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wb_sources.id"), index=True
    )
    source_note: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[WBSource | None] = relationship(back_populates="indicators")

    __table_args__ = (
        # Trigram index for fuzzy search — requires pg_trgm extension
        Index(
            "ix_wb_indicators_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<WBIndicator {self.code} {self.name!r}>"


# ── Download Jobs ────────────────────────────────────────────────────────


class WBDownloadJob(Base):
    __tablename__ = "wb_download_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending/running/completed/failed
    source_id: Mapped[int | None] = mapped_column(Integer)
    indicator_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    country_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    year_start: Mapped[int | None] = mapped_column(SmallInteger)
    year_end: Mapped[int | None] = mapped_column(SmallInteger)
    total_requests: Mapped[int | None] = mapped_column(Integer)
    completed_requests: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    data_points: Mapped[list[WBDataPoint]] = relationship(back_populates="download_job")

    def __repr__(self) -> str:
        return f"<WBDownloadJob id={self.id} status={self.status!r}>"


# ── Data Points ──────────────────────────────────────────────────────────


class WBDataPoint(Base):
    __tablename__ = "wb_data_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    indicator_code: Mapped[str] = mapped_column(
        Text, ForeignKey("wb_indicators.code"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("wb_countries.iso3_code"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    download_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wb_download_jobs.id")
    )

    download_job: Mapped[WBDownloadJob | None] = relationship(back_populates="data_points")

    __table_args__ = (
        UniqueConstraint("indicator_code", "country_code", "year", name="uq_data_point"),
        Index("ix_data_indicator_country", "indicator_code", "country_code"),
    )

    def __repr__(self) -> str:
        return (
            f"<WBDataPoint {self.indicator_code} "
            f"{self.country_code} {self.year}={self.value}>"
        )
