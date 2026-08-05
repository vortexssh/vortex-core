import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.schemas.host import HostCreate, HostUpdate
from app.services.host import HostService


@pytest.mark.asyncio
async def test_create_host_sets_country_from_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    host_id = uuid4()

    mock_host = MagicMock()
    mock_host.id = host_id
    mock_host.ip_address = "8.8.8.8"
    mock_host.country_code = "US"

    saved_hosts: list[MagicMock] = []

    class FakeHostRepo:
        async def next_sort_order(self, _uid) -> int:
            return 0

        async def create(self, host) -> MagicMock:
            host.id = host_id
            saved_hosts.append(host)
            return host

        async def get_by_id(self, hid, uid):
            if hid == host_id and uid == user_id:
                return mock_host
            return None

        async def get_by_id_any(self, hid):
            return mock_host if hid == host_id else None

        async def save(self, host) -> MagicMock:
            return host

    class FakeTagRepo:
        pass

    session = AsyncMock()
    service = HostService(session)
    service._hosts = FakeHostRepo()
    service._tags = FakeTagRepo()

    sync_mock = AsyncMock()
    monkeypatch.setattr(service, "_sync_country_from_ip", sync_mock)

    payload = HostCreate(
        name="dns",
        ip_address="8.8.8.8",
        username="root",
    )
    result = await service.create_host(user_id, payload)

    assert result is mock_host
    sync_mock.assert_awaited_once_with(host_id, "8.8.8.8", None)
    assert saved_hosts[0].country_code is None


@pytest.mark.asyncio
async def test_update_host_clears_country_when_ip_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    host_id = uuid4()

    mock_host = MagicMock()
    mock_host.id = host_id
    mock_host.ip_address = None
    mock_host.country_code = "US"

    class FakeHostRepo:
        async def get_by_id(self, hid, uid):
            return mock_host if hid == host_id and uid == user_id else None

        async def get_by_id_any(self, hid):
            return mock_host if hid == host_id else None

        async def save(self, host) -> MagicMock:
            return host

    class FakeTagRepo:
        pass

    session = AsyncMock()
    service = HostService(session)
    service._hosts = FakeHostRepo()
    service._tags = FakeTagRepo()

    sync_mock = AsyncMock()
    monkeypatch.setattr(service, "_sync_country_from_ip", sync_mock)

    await service.update_host(
        user_id,
        host_id,
        HostUpdate(ip_address=None),
    )

    sync_mock.assert_awaited_once_with(host_id, None, None)


@pytest.mark.asyncio
async def test_list_hosts_backfills_missing_country(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    host = MagicMock()
    host.id = uuid4()
    host.ip_address = "157.22.205.226"
    host.country_code = None

    class FakeHostRepo:
        async def list_for_user(self, *_a, **_k):
            return [host]

        async def get_by_id_any(self, hid):
            return host if hid == host.id else None

        async def save(self, h):
            return h

    session = AsyncMock()
    service = HostService(session)
    service._hosts = FakeHostRepo()

    async def fake_apply(host_id, ip, redis=None):
        host.country_code = "RU"
        return True

    monkeypatch.setattr(service, "apply_geoip", fake_apply)

    result = await service.list_hosts(user_id)
    assert result[0].country_code == "RU"
