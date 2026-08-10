from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_payer import BillingPayer


class BillingPayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payer_id: UUID, user_id: UUID) -> BillingPayer | None:
        result = await self._session.execute(
            select(BillingPayer).where(
                BillingPayer.id == payer_id,
                BillingPayer.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[BillingPayer]:
        result = await self._session.execute(
            select(BillingPayer)
            .where(BillingPayer.user_id == user_id)
            .order_by(BillingPayer.name.asc())
        )
        return list(result.scalars().all())

    async def count_hosts(self, payer_id: UUID, user_id: UUID) -> int:
        from app.models.host import Host

        result = await self._session.execute(
            select(func.count())
            .select_from(Host)
            .where(
                Host.user_id == user_id,
                Host.billing_payer_id == payer_id,
            )
        )
        return int(result.scalar_one())

    async def create(self, payer: BillingPayer) -> BillingPayer:
        self._session.add(payer)
        await self._session.flush()
        await self._session.refresh(payer)
        return payer

    async def save(self, payer: BillingPayer) -> BillingPayer:
        self._session.add(payer)
        await self._session.flush()
        await self._session.refresh(payer)
        return payer

    async def delete(self, payer: BillingPayer) -> None:
        await self._session.delete(payer)
        await self._session.flush()
