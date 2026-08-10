"""Billing payer CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_payer import BillingPayer
from app.repositories.billing_payer import BillingPayerRepository
from app.repositories.host import HostRepository
from app.schemas.billing import (
    BillingPayerCreate,
    BillingPayerDetail,
    BillingPayerHostBrief,
    BillingPayerRead,
    BillingPayerUpdate,
)


class BillingPayerService:
    def __init__(self, session: AsyncSession) -> None:
        self._payers = BillingPayerRepository(session)
        self._hosts = HostRepository(session)
        self._session = session

    async def list_payers(self, user_id: UUID) -> list[BillingPayerRead]:
        rows = await self._payers.list_for_user(user_id)
        out: list[BillingPayerRead] = []
        for row in rows:
            count = await self._payers.count_hosts(row.id, user_id)
            out.append(
                BillingPayerRead(
                    id=row.id,
                    name=row.name,
                    notes=row.notes,
                    host_count=count,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return out

    async def get_payer(self, user_id: UUID, payer_id: UUID) -> BillingPayerDetail:
        payer = await self._require_payer(user_id, payer_id)
        hosts = await self._hosts.list_for_payer(user_id, payer_id)
        host_briefs = [
            BillingPayerHostBrief(
                id=h.id,
                name=h.name,
                billing_enabled=h.billing_enabled,
                billing_amount=h.billing_amount,
                billing_currency=h.billing_currency,
                billing_renewal_at=h.billing_renewal_at,
                billing_cycle=h.billing_cycle,
                billing_auto_renew=h.billing_auto_renew,
                country_code=h.country_code,
            )
            for h in hosts
        ]
        return BillingPayerDetail(
            id=payer.id,
            name=payer.name,
            notes=payer.notes,
            host_count=len(host_briefs),
            created_at=payer.created_at,
            updated_at=payer.updated_at,
            hosts=host_briefs,
        )

    async def create_payer(self, user_id: UUID, payload: BillingPayerCreate) -> BillingPayerRead:
        payer = BillingPayer(
            user_id=user_id,
            name=payload.name.strip(),
            notes=payload.notes,
        )
        payer = await self._payers.create(payer)
        await self._session.commit()
        return BillingPayerRead(
            id=payer.id,
            name=payer.name,
            notes=payer.notes,
            host_count=0,
            created_at=payer.created_at,
            updated_at=payer.updated_at,
        )

    async def update_payer(
        self,
        user_id: UUID,
        payer_id: UUID,
        payload: BillingPayerUpdate,
    ) -> BillingPayerRead:
        payer = await self._require_payer(user_id, payer_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            payer.name = data["name"].strip()
        if "notes" in data:
            payer.notes = data["notes"]
        payer = await self._payers.save(payer)
        await self._session.commit()
        count = await self._payers.count_hosts(payer.id, user_id)
        return BillingPayerRead(
            id=payer.id,
            name=payer.name,
            notes=payer.notes,
            host_count=count,
            created_at=payer.created_at,
            updated_at=payer.updated_at,
        )

    async def delete_payer(self, user_id: UUID, payer_id: UUID) -> None:
        payer = await self._require_payer(user_id, payer_id)
        await self._payers.delete(payer)
        await self._session.commit()

    async def require_owned(self, user_id: UUID, payer_id: UUID) -> BillingPayer:
        return await self._require_payer(user_id, payer_id)

    async def _require_payer(self, user_id: UUID, payer_id: UUID) -> BillingPayer:
        payer = await self._payers.get_by_id(payer_id, user_id)
        if payer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "payer_not_found", "message": "Billing payer not found"},
            )
        return payer
