"""Frankfurter FX rates (v2 multi-provider, includes RUB via CBR) + Redis cache."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.core.config import get_settings
from app.services.http_out import outbound_client

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


def _api_root(raw: str) -> str:
    """Normalize to api.frankfurter.dev root (strip legacy /v1 paths)."""
    value = raw.strip().rstrip("/")
    # Legacy host had no RUB (ECB-only). Prefer the multi-provider public API.
    if "frankfurter.app" in value:
        return "https://api.frankfurter.dev"
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value


class FxService:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis
        self._settings = get_settings()

    async def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> Decimal | None:
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rate = await self.get_rate(src, dst)
        if rate is None:
            return None
        return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def get_rate(self, from_currency: str, to_currency: str) -> Decimal | None:
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return Decimal("1")

        cache_key = f"fx:{src}:{dst}"
        if self._redis is not None:
            cached = await self._redis.get(cache_key)
            if cached:
                try:
                    return Decimal(str(cached))
                except Exception:
                    pass

        rate = await self._fetch_rate(src, dst)
        if rate is None and src != "EUR" and dst != "EUR":
            to_eur = await self._fetch_rate(src, "EUR")
            from_eur = await self._fetch_rate("EUR", dst)
            if to_eur is not None and from_eur is not None:
                rate = to_eur * from_eur

        if rate is not None and self._redis is not None:
            await self._redis.set(
                cache_key,
                str(rate),
                ex=self._settings.fx_cache_ttl_seconds,
            )
        return rate

    async def _fetch_rate(self, src: str, dst: str) -> Decimal | None:
        root = _api_root(self._settings.frankfurter_base_url)
        # v2 single-pair: {"date","base","quote","rate"} — covers RUB via CBR blend.
        url = f"{root}/v2/rate/{src}/{dst}"
        try:
            async with outbound_client(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning(
                        "Frankfurter %s→%s status %s body=%s",
                        src,
                        dst,
                        response.status_code,
                        response.text[:120],
                    )
                    return None
                data = response.json()
            raw = data.get("rate")
            if raw is None:
                return None
            return Decimal(str(raw))
        except Exception:
            logger.warning("Frankfurter lookup failed %s→%s", src, dst, exc_info=True)
            return None
