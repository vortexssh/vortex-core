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
    mock_host.country_code = None

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

    apply_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "apply_geoip", apply_mock)

    payload = HostCreate(
        name="dns",
        ip_address="8.8.8.8",
        username="root",
    )
    result = await service.create_host(user_id, payload)

    assert result is mock_host
    apply_mock.assert_awaited_once_with(host_id, "8.8.8.8", None)
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
