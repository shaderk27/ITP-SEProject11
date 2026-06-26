from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, Cookie, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth_schema import (
    LoginRequest,
    CreateUserRequest,
    RoleResponse,
    UpdateProfileRequest,
    AssignLabGroupSchema,
    AssignLabSchema,
)
from app.services.auth_service import AuthService
from app.repositories.auth_repository import AuthRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(repository=AuthRepository(), db=db)


def require_admin(
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    current_user = service.get_current_user(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    return current_user


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    return service.login(payload.email, payload.password, response)


@router.get("/me")
async def me(
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    return service.get_current_user(access_token)


@router.put("/me")
async def update_me(
    payload: UpdateProfileRequest,
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    current_user = service.get_current_user(access_token)
    user_id = current_user.get("id")

    return service.update_user_profile(
        user_id=user_id,
        full_name=payload.full_name,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/", httponly=True, samesite="lax")
    return {"message": "Logged out"}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.create_user(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role_id=payload.role_id,
        staff_id=payload.staff_id,
        lab_group_id=payload.lab_group_id,
        lab_id=payload.lab_id,
    )


@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(service: AuthService = Depends(get_auth_service)):
    return service.get_all_roles()


# @router.get("/users")
# async def get_all_users(
#     service: AuthService = Depends(get_auth_service),
#     _admin: dict = Depends(require_admin),
# ):
#     return service.get_all_users()
@router.get("/users")
async def get_all_users(
    role: Optional[str] = Query(None),
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    if role:
        return service.get_users_by_role(role)
    return service.get_all_users()


@router.get("/assignments")
async def get_assignments(
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.get_assignments()
@router.put("/users/{user_id}/assign-lab")
async def assign_lab_ic(
    user_id: int,
    payload: AssignLabSchema,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.assign_lab_to_user(user_id, payload.lab_id)

@router.put("/users/{user_id}/assign-labgroup")
async def assign_team_ic(
    user_id: int,
    payload: AssignLabGroupSchema,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.assign_labgroup_to_user(user_id, payload.lab_group_id)
