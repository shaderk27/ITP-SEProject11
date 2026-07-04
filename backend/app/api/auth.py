from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, Cookie, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth_schema import (
    ForgotPasswordSchema,
    LoginRequest,
    CreateUserRequest,
    ResetPasswordSchema,
    RoleResponse,
    UpdateProfileRequest,
    AssignLabGroupSchema,
    AssignLabSchema,
)
from app.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    COOKIE_NAME,
    COOKIE_SECURE,
    AuthService,
)
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


def get_current_user_allow_reset(
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    return service.get_current_user_allow_reset(access_token)


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
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session."
        )
    return service.update_user_profile(
        user_id=int(user_id),
        full_name=payload.full_name,
    )


@router.get("/me/reset")
async def me_reset(
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    """For temp-reset sessions only — returns minimal user info."""
    return service.get_current_user_allow_reset(access_token)


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


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordSchema,
    service: AuthService = Depends(get_auth_service),
):
    # Always return 200 even if email not found — don't leak whether email exists
    service.forgot_password(payload.email)
    return {"message": "If that email exists, a temporary password has been sent."}


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
async def assign_team_lead(
    user_id: int,
    payload: AssignLabGroupSchema,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.assign_labgroup_to_user(user_id, payload.lab_group_id)


@router.put("/users/{user_id}/unassign-scope")
async def unassign_user_scope(
    user_id: int,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    return service.unassign_user_scope(user_id)


@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin),
):
    return service.deactivate_user(user_id, current_admin_id=admin["id"])


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordSchema,
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user_allow_reset),
):
    service.reset_password(
        current_user["id"],
        payload.current_password,
        payload.new_password,
    )
    return {"message": "Password reset successfully."}


@router.post("/users/{user_id}/send-reset")
async def admin_send_reset(
    user_id: int,
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin),
):
    user = service.repository.get_user_by_id(service.db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role.role_name == "admin":
        raise HTTPException(
            status_code=403, detail="Admin passwords cannot be reset by another admin."
        )
    service.forgot_password(user.email)
    return {"message": f"Temporary password sent to {user.email}."}


@router.post("/refresh")
async def refresh_session(
    response: Response,
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    """Reissue a fresh JWT cookie to extend the session."""
    current_user = service.get_current_user(access_token)
    token_payload = {
        "sub": str(current_user["id"]),
        "email": current_user["email"],
        "role": current_user["role"],
        "lab_group_id": current_user["lab_group_id"],
        "lab_id": current_user["lab_id"],
        "must_reset_password": current_user.get("must_reset_password", False),
    }
    token = service._create_access_token(data=token_payload)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"message": "Session extended."}
