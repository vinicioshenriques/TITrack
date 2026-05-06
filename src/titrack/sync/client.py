"""Supabase REST client wrapper for cloud sync."""

import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("titrack")


@dataclass
class CloudPrice:
    """Aggregated price from cloud."""

    config_base_id: int
    season_id: int
    price_fe_median: float
    price_fe_p10: Optional[float] = None
    price_fe_p90: Optional[float] = None
    submission_count: Optional[int] = None
    unique_devices: Optional[int] = None
    updated_at: Optional[datetime] = None


@dataclass
class CloudPriceHistory:
    """Hourly price history point from cloud."""

    config_base_id: int
    season_id: int
    hour_bucket: datetime
    price_fe_median: float
    price_fe_p10: Optional[float] = None
    price_fe_p90: Optional[float] = None
    submission_count: Optional[int] = None


@dataclass
class SubmitResult:
    """Result of a price submission."""

    success: bool
    error: Optional[str] = None
    rate_limited: bool = False


class CloudClient:
    """
    Supabase REST client for cloud price sync.

    The previous Python Supabase SDK pulls a large optional storage dependency
    chain, which is brittle on newer Python versions. TITrack only needs
    PostgREST table reads and two RPC calls, so urllib is enough.
    """

    ENV_SUPABASE_URL = "TITRACK_SUPABASE_URL"
    ENV_SUPABASE_KEY = "TITRACK_SUPABASE_KEY"

    DEFAULT_SUPABASE_URL = "https://qhjulyngunwiculnharg.supabase.co"
    DEFAULT_SUPABASE_KEY = "sb_publishable_YgqYSMUarrM_IKvcNpJlBw_KwTpp7ho"

    def __init__(self) -> None:
        self._url: Optional[str] = None
        self._key: Optional[str] = None
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Check if cloud sync is configured."""
        url, key = self.get_config()
        return bool(url and key)

    @property
    def is_connected(self) -> bool:
        """Check if currently configured for requests."""
        return self._connected and bool(self._url and self._key)

    def get_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get Supabase configuration from environment or defaults."""
        url = os.environ.get(self.ENV_SUPABASE_URL, self.DEFAULT_SUPABASE_URL)
        key = os.environ.get(self.ENV_SUPABASE_KEY, self.DEFAULT_SUPABASE_KEY)
        if not url or not key:
            return None, None
        return url, key

    def connect(self) -> bool:
        """Initialize REST client configuration."""
        url, key = self.get_config()
        if not url or not key:
            return False

        self._url = url.rstrip("/")
        self._key = key
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from Supabase."""
        self._url = None
        self._key = None
        self._connected = False

    def submit_price(
        self,
        device_id: str,
        config_base_id: int,
        season_id: int,
        price_fe: float,
        prices_array: list[float],
    ) -> SubmitResult:
        """Submit a price observation to the cloud."""
        if not self.is_connected:
            return SubmitResult(success=False, error="Not connected")

        try:
            result = self._request(
                "POST",
                "rpc/submit_price",
                body={
                    "p_device_id": device_id,
                    "p_config_base_id": config_base_id,
                    "p_season_id": season_id,
                    "p_price_fe": price_fe,
                    "p_prices_array": prices_array,
                },
            )

            if isinstance(result, dict) and result.get("rate_limited"):
                return SubmitResult(success=False, error="Rate limited", rate_limited=True)

            if isinstance(result, dict) and result.get("success") is False:
                return SubmitResult(success=False, error=result.get("error", "Submit failed"))

            return SubmitResult(success=True)
        except Exception as e:
            error_str = str(e)
            rate_limited = "rate" in error_str.lower() or "429" in error_str
            return SubmitResult(success=False, error=error_str, rate_limited=rate_limited)

    def fetch_prices_delta(
        self, season_id: int, since: Optional[datetime] = None
    ) -> list[CloudPrice]:
        """Fetch aggregated prices that have changed since a timestamp."""
        if not self.is_connected:
            return []

        try:
            query: dict[str, str | int] = {
                "select": "*",
                "season_id": f"eq.{season_id}",
            }
            if since:
                query["updated_at"] = f"gt.{since.isoformat()}"

            rows = self._fetch_rows("aggregated_prices", query)
            return [
                CloudPrice(
                    config_base_id=row["config_base_id"],
                    season_id=row["season_id"],
                    price_fe_median=row["price_fe_median"],
                    price_fe_p10=row.get("price_fe_p10"),
                    price_fe_p90=row.get("price_fe_p90"),
                    submission_count=row.get("submission_count"),
                    unique_devices=row.get("unique_devices"),
                    updated_at=(
                        datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                        if row.get("updated_at")
                        else None
                    ),
                )
                for row in rows
            ]
        except Exception as e:
            print(f"Cloud sync: Failed to fetch prices: {e}")
            return []

    def fetch_price_history(
        self,
        season_id: int,
        hours: int = 72,
        config_base_ids: list[int] | None = None,
    ) -> list[CloudPriceHistory]:
        """Fetch price history for sparklines."""
        if not self.is_connected:
            return []

        if config_base_ids:
            try:
                logger.info(f"Cloud sync: Fetching history via RPC for {len(config_base_ids)} items")
                rows = self._fetch_rpc_rows(
                    "get_price_history_for_items",
                    {
                        "p_season_id": season_id,
                        "p_config_base_ids": config_base_ids,
                        "p_hours": hours,
                    },
                )
                logger.info(f"Cloud sync: RPC returned {len(rows)} history rows")
                if rows:
                    return self._parse_history_rows(rows)
                logger.info("Cloud sync: RPC returned empty, falling back to table query")
            except Exception as e:
                logger.warning(f"Cloud sync: RPC fetch failed, falling back to table query: {e}")

        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            rows = self._fetch_rows(
                "price_history",
                {
                    "select": "*",
                    "season_id": f"eq.{season_id}",
                    "hour_bucket": f"gt.{cutoff.isoformat()}",
                    "order": "hour_bucket.asc",
                },
            )
            return self._parse_history_rows(rows)
        except Exception as e:
            print(f"Cloud sync: Failed to fetch price history: {e}")
            return []

    def fetch_item_history(
        self, config_base_id: int, season_id: int, hours: int = 72
    ) -> list[CloudPriceHistory]:
        """Fetch price history for a specific item."""
        if not self.is_connected:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            rows = self._fetch_rows(
                "price_history",
                {
                    "select": "*",
                    "config_base_id": f"eq.{config_base_id}",
                    "season_id": f"eq.{season_id}",
                    "hour_bucket": f"gt.{cutoff.isoformat()}",
                    "order": "hour_bucket.asc",
                },
            )
            return self._parse_history_rows(rows)
        except Exception as e:
            print(f"Cloud sync: Failed to fetch item history: {e}")
            return []

    def _parse_history_rows(self, rows: list[dict]) -> list[CloudPriceHistory]:
        history = []
        for row in rows:
            history.append(
                CloudPriceHistory(
                    config_base_id=row["config_base_id"],
                    season_id=row["season_id"],
                    hour_bucket=datetime.fromisoformat(
                        row["hour_bucket"].replace("Z", "+00:00")
                    ),
                    price_fe_median=row["price_fe_median"],
                    price_fe_p10=row.get("price_fe_p10"),
                    price_fe_p90=row.get("price_fe_p90"),
                    submission_count=row.get("submission_count"),
                )
            )
        return history

    def _headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        headers = {
            "apikey": self._key or "",
            "Authorization": f"Bearer {self._key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TITrack-CloudSync",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[dict[str, str | int]] = None,
        body: Optional[dict] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: int = 30,
    ) -> object:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        url = f"{self._url}/rest/v1/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=self._headers(headers),
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))

    def _fetch_rows(
        self,
        path: str,
        query: dict[str, str | int],
        *,
        page_size: int = 1000,
    ) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            page_query = dict(query)
            page_query["limit"] = page_size
            page_query["offset"] = offset
            page = self._request("GET", path, query=page_query)
            if not isinstance(page, list):
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def _fetch_rpc_rows(
        self,
        function_name: str,
        body: dict,
        *,
        page_size: int = 1000,
    ) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            page = self._request(
                "POST",
                f"rpc/{function_name}",
                body=body,
                headers={"Range": f"{offset}-{offset + page_size - 1}"},
            )
            if not isinstance(page, list):
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows
