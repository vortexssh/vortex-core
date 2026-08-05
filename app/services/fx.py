"""Frankfurter (ECB) FX rates with Redis cache."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

import httpx

from app.core.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


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
        base = self._settings.frankfurter_base_url.rstrip("/")
        url = f"{base}/latest"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params={"from": src, "to": dst})
                if response.status_code != 200:
                    logger.debug(
                        "Frankfurter %s→%s status %s", src, dst, response.status_code
                    )
                    return None
                data = response.json()
            rates = data.get("rates") or {}
            raw = rates.get(dst)
            if raw is None:
                return None
            return Decimal(str(raw))
        except Exception:
            logger.debug("Frankfurter lookup failed %s→%s", src, dst, exc_info=True)
            return None
