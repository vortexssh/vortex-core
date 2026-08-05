"""Country lookup for host flags (MaxMind GeoLite2 + optional HTTP fallback)."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.core.config import get_settings

if TYPE_CHECKING:
    from geoip2.database import Reader
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


@lru_cache
def _mmdb_reader() -> Reader | None:
    settings = get_settings()
    path = Path(settings.geoip_db_path)
    if not path.is_file():
        return None
    try:
        import geoip2.database

        return geoip2.database.Reader(str(path))
    except Exception:
        logger.exception("Failed to open GeoIP database at %s", path)
        return None


def _lookup_mmdb(ip: str) -> str | None:
    reader = _mmdb_reader()
    if reader is None:
        return None
    try:
        response = reader.country(ip)
        code = response.country.iso_code
        return code.upper() if code else None
    except Exception:
        return None


async def _lookup_http(ip: str) -> str | None:
    settings = get_settings()
    if not settings.geoip_http_fallback:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"https://ipwho.is/{ip}",
                headers={"User-Agent": f"{settings.app_name}/1.0"},
            )
            response.raise_for_status()
            data = response.json()
        if data.get("success") and data.get("country_code"):
            return str(data["country_code"]).upper()
    except Exception:
        logger.debug("HTTP GeoIP lookup failed for %s", ip, exc_info=True)
    return None


async def lookup_country_code(ip: str, redis: Redis | None = None) -> str | None:
    """Return ISO-3166 alpha-2 country code for a public IP, or None."""
    settings = get_settings()
    if not settings.geoip_enabled:
        return None

    normalized = ip.strip()
    if not is_public_ip(normalized):
        return None

    cache_key = f"geoip:{normalized}"
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached is not None:
            return normalize_cached_country(str(cached))

    code = await asyncio.to_thread(_lookup_mmdb, normalized)
    if code is None:
        code = await _lookup_http(normalized)

    if redis is not None:
        # Cache hits and misses so list backfill does not hammer the provider
        ttl = settings.geoip_cache_ttl_seconds if code else min(3600, settings.geoip_cache_ttl_seconds)
        await redis.set(cache_key, code or "-", ex=ttl)

    return code


def normalize_cached_country(raw: str | None) -> str | None:
    if not raw or raw == "-":
        return None
    return str(raw).upper()
