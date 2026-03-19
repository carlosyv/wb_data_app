"""Async World Bank API v2 client with rate limiting, retries, and UA rotation.

Key design decisions
--------------------
- ``asyncio.Semaphore`` caps concurrent outgoing requests.
- ``asyncio.sleep`` between every request keeps average rate ≈ 2 req/s.
- ``tenacity`` handles transient errors with exponential backoff.
- User-Agent strings rotate per request to reduce fingerprinting.
- All responses are returned as parsed Python dicts / lists.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import settings

logger = logging.getLogger(__name__)

# ── User-Agent rotation pool ────────────────────────────────────────────

_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (compatible; AcademicResearchBot/1.0; +https://example.edu)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Python-httpx/0.27 (WorldBankDataResearch; academic-use)",
]

# ── Data classes for parsed responses ────────────────────────────────────


@dataclass
class WBSourceDTO:
    id: int
    name: str
    description: str = ""
    url: str = ""


@dataclass
class WBCountryDTO:
    iso3_code: str
    iso2_code: str
    name: str
    region: str = ""
    income_level: str = ""


@dataclass
class WBIndicatorDTO:
    code: str
    name: str
    source_id: int | None = None
    source_note: str = ""
    topic: str = ""


@dataclass
class WBDataPointDTO:
    indicator_code: str
    country_code: str  # iso3
    year: int
    value: float | None = None


@dataclass
class PaginatedResult:
    page: int = 1
    pages: int = 1
    per_page: int = 1000
    total: int = 0
    items: list[Any] = field(default_factory=list)


# ── Retry-decorated HTTP helper ──────────────────────────────────────────


class WBClient:
    """Async World Bank API v2 client."""

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(settings.wb_max_concurrent_requests)
        self._delay = settings.wb_delay_between_requests
        self._base = settings.wb_api_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def open(self) -> None:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=settings.wb_max_concurrent_requests,
                    max_keepalive_connections=3,
                ),
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── low-level request with rate limit + retry ────────────────────────

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    async def _request(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Make a single GET request with semaphore, delay, and retry."""
        await self.open()
        assert self._client is not None

        async with self._sem:
            headers = {"User-Agent": random.choice(_USER_AGENTS)}
            logger.debug("GET %s params=%s", url, params)

            resp = await self._client.get(url, params=params, headers=headers)

            # Handle rate-limiting explicitly
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning("Rate-limited (429). Sleeping %ss …", retry_after)
                await asyncio.sleep(retry_after)
                resp.raise_for_status()

            resp.raise_for_status()

            # Polite delay after every request
            await asyncio.sleep(self._delay)

            return resp.json()

    # ── WB API v2 response parser ────────────────────────────────────────

    async def _get_wb(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        per_page: int = 1000,
    ) -> PaginatedResult:
        """Fetch a WB v2 endpoint, auto-paginating.

        WB API v2 returns ``[metadata_dict, data_list | None]``.
        """
        params = dict(params or {})
        params.setdefault("format", "json")
        params.setdefault("per_page", per_page)

        url = f"{self._base}/{path.lstrip('/')}"

        all_items: list[Any] = []
        page = 1

        while True:
            params["page"] = page
            raw = await self._request(url, params)

            # WB returns [meta, data]
            if not isinstance(raw, list) or len(raw) < 2:
                logger.warning("Unexpected WB response shape for %s: %s", url, type(raw))
                break

            meta, data = raw[0], raw[1]
            if data is None:
                break

            all_items.extend(data)

            total_pages = int(meta.get("pages", 1))
            total_items = int(meta.get("total", 0))

            if page >= total_pages:
                break
            page += 1

            # Extra sleep between pagination pages
            await asyncio.sleep(self._delay)

        return PaginatedResult(
            page=1,
            pages=page,
            per_page=per_page,
            total=len(all_items),
            items=all_items,
        )

    # ── Public API methods ───────────────────────────────────────────────

    async def get_sources(self) -> list[WBSourceDTO]:
        """Fetch all World Bank data source catalogues."""
        result = await self._get_wb("sources", per_page=100)
        sources: list[WBSourceDTO] = []
        for item in result.items:
            sources.append(
                WBSourceDTO(
                    id=int(item["id"]),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                )
            )
        return sources

    async def get_countries(self) -> list[WBCountryDTO]:
        """Fetch all countries / regions from WB."""
        result = await self._get_wb("country", per_page=500)
        countries: list[WBCountryDTO] = []
        for item in result.items:
            iso3 = item.get("id", "")
            if len(iso3) != 3:
                continue  # skip aggregates like "WLD"... actually keep them
            countries.append(
                WBCountryDTO(
                    iso3_code=iso3,
                    iso2_code=item.get("iso2Code", ""),
                    name=item.get("name", ""),
                    region=item.get("region", {}).get("value", "") if isinstance(item.get("region"), dict) else "",
                    income_level=item.get("incomeLevel", {}).get("value", "") if isinstance(item.get("incomeLevel"), dict) else "",
                )
            )
        return countries

    async def get_indicators(
        self,
        source_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        per_page: int = 1000,
    ) -> PaginatedResult:
        """Fetch indicators, optionally filtered by source or search query.

        Returns a PaginatedResult whose ``.items`` are ``WBIndicatorDTO``.
        """
        if source_id is not None:
            path = f"source/{source_id}/indicator"
        else:
            path = "indicator"

        params: dict[str, Any] = {}
        if search:
            # WB uses the undocumented but working `search` param (V2) :contentReference[oaicite:0]{index=0}
            params["search"] = search  # keyword search across indicator names

        # For indicator listing we do server-side pagination (not auto-all)
        params["page"] = page
        params["per_page"] = per_page
        params["format"] = "json"

        url = f"{self._base}/{path}"
        raw = await self._request(url, params)

        if not isinstance(raw, list) or len(raw) < 2 or raw[1] is None:
            return PaginatedResult()

        meta, data = raw[0], raw[1]
        items = [
            WBIndicatorDTO(
                code=ind["id"],
                name=ind.get("name", ""),
                source_id=int(ind["source"]["id"]) if ind.get("source") else None,
                source_note=ind.get("sourceNote", ""),
                topic=(
                    "; ".join(t["value"] for t in ind.get("topics", []) if t.get("value"))
                    if ind.get("topics")
                    else ""
                ),
            )
            for ind in data
        ]
        return PaginatedResult(
            page=int(meta.get("page", 1)),
            pages=int(meta.get("pages", 1)),
            per_page=int(meta.get("per_page", per_page)),
            total=int(meta.get("total", 0)),
            items=items,
        )

    async def get_all_indicators_for_source(self, source_id: int) -> list[WBIndicatorDTO]:
        """Fetch ALL indicators for a source, auto-paginating."""
        result = await self._get_wb(f"source/{source_id}/indicator", per_page=1000)
        return [
            WBIndicatorDTO(
                code=ind["id"],
                name=ind.get("name", ""),
                source_id=int(ind["source"]["id"]) if ind.get("source") else source_id,
                source_note=ind.get("sourceNote", ""),
                topic=(
                    "; ".join(t["value"] for t in ind.get("topics", []) if t.get("value"))
                    if ind.get("topics")
                    else ""
                ),
            )
            for ind in result.items
        ]

    async def get_data(
        self,
        indicator: str,
        countries: list[str],
        year_start: int,
        year_end: int,
    ) -> list[WBDataPointDTO]:
        """Download data for one indicator across countries and year range.

        Uses the WB country batching trick:
            ``/country/ARG;BRA;CHL/indicator/NY.GDP.MKTP.KD``
        """
        # WB API accepts semicolon-separated country codes (max ~60 per request)
        batch_size = 50
        all_points: list[WBDataPointDTO] = []

        for i in range(0, len(countries), batch_size):
            batch = countries[i : i + batch_size]
            country_str = ";".join(batch)
            path = f"country/{country_str}/indicator/{indicator}"
            params = {"date": f"{year_start}:{year_end}"}

            result = await self._get_wb(path, params=params)

            for item in result.items:
                val = item.get("value")
                country_info = item.get("country", {})
                iso3 = item.get("countryiso3code", country_info.get("id", ""))
                year_str = item.get("date", "")

                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    continue

                all_points.append(
                    WBDataPointDTO(
                        indicator_code=indicator,
                        country_code=iso3,
                        year=year,
                        value=float(val) if val is not None else None,
                    )
                )

            # Extra sleep between country batches
            await asyncio.sleep(self._delay * 2)

        return all_points


# Module-level singleton
wb_client = WBClient()
