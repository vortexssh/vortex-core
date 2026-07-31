from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import UserRead, UserUpdate
from app.services.auth import AuthService
from app.repositories.user import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    user: CurrentUser,
    session: DbSession,
) -> UserRead:
    service = AuthService(session)
    db_user = await UserRepository(session).get_by_id(user.id)
    assert db_user is not None
    updated = await service.update_profile(db_user, payload.email)
    return UserRead.model_validate(updated)
