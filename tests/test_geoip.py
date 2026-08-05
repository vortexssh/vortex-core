import pytest

from app.core.client_ip import extract_client_ip, websocket_client_ip


def test_extract_client_ip_prefers_forwarded_for() -> None:
    assert (
        extract_client_ip(
            host="10.0.0.1",
            forwarded_for="203.0.113.5, 10.0.0.1",
            real_ip="198.51.100.2",
        )
        == "203.0.113.5"
    )


def test_extract_client_ip_falls_back_to_real_ip() -> None:
    assert (
        extract_client_ip(host="10.0.0.1", forwarded_for=None, real_ip="198.51.100.2")
        == "198.51.100.2"
    )


def test_extract_client_ip_falls_back_to_peer() -> None:
    assert extract_client_ip(host="203.0.113.5", forwarded_for=None) == "203.0.113.5"


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeWebSocket:
    def __init__(self, headers: dict[str, str], host: str) -> None:
        self.headers = headers
        self.client = _FakeClient(host)


def test_websocket_client_ip_reads_proxy_headers() -> None:
    ws = _FakeWebSocket(
        {"x-forwarded-for": "203.0.113.9, 172.18.0.1"},
        "172.18.0.1",
    )
    assert websocket_client_ip(ws) == "203.0.113.9"


def test_is_public_ip() -> None:
    from app.services.geoip import is_public_ip

    assert is_public_ip("8.8.8.8")
    assert not is_public_ip("10.0.0.1")
    assert not is_public_ip("192.168.1.1")
    assert not is_public_ip("127.0.0.1")
    assert not is_public_ip("not-an-ip")


@pytest.mark.asyncio
async def test_lookup_country_code_http_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.services import geoip as geoip_module

    get_settings.cache_clear()
    geoip_module._mmdb_reader.cache_clear()

    monkeypatch.setenv("GEOIP_HTTP_FALLBACK", "true")
    monkeypatch.setenv("GEOIP_DB_PATH", "/nonexistent/GeoLite2-Country.mmdb")
    get_settings.cache_clear()
    geoip_module._mmdb_reader.cache_clear()

    async def fake_http(ip: str) -> str | None:
        assert ip == "8.8.8.8"
        return "US"

    monkeypatch.setattr(geoip_module, "_lookup_http", fake_http)

    code = await geoip_module.lookup_country_code("8.8.8.8")
    assert code == "US"

    get_settings.cache_clear()
    geoip_module._mmdb_reader.cache_clear()
