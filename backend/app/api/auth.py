
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.auth import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth_schema import (
    AssignLabGroupSchema,
    AssignLabSchema,
    CreateUserRequest,
    ForgotPasswordSchema,
    LoginRequest,
    ResetPasswordSchema,
    RoleResponse,
    UpdateProfileRequest,
)
from app.services.audit_service import log_audit_action
from app.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    COOKIE_NAME,
    COOKIE_SECURE,
    AuthService,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(repository=AuthRepository(), db=db)


def require_admin_or_teamlead(  # allow manager too
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    current_user = service.get_current_user(access_token)
    if current_user.get("role") not in ("admin", "teamlead"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or team lead access is required.",
        )
    return current_user


def get_current_user_allow_reset(
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    return service.get_current_user_allow_reset(access_token)


def _ensure_can_manage(service: AuthService, actor: dict, user_id: int):
    """Admins can manage anyone. Team leads can manage team leads and
    lab ICs, but never admins. Returns the target user."""
    target = service.repository.get_user_by_id(service.db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.role.role_name == "admin" and actor.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Team leads cannot manage admin accounts.",
        )
    return target


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    try:
        res = service.login(payload.email, payload.password, response)
        user = service.db.query(User).filter(User.email == payload.email).first()
        if user:
            log_audit_action(
                db=service.db,
                user_id=user.user_id,
                action_type="LOGIN_SUCCESS",
                entity_name="Authentication",
                record_id=str(user.user_id),
                request=request,
            )
        return res
    except HTTPException as e:
        user = service.db.query(User).filter(User.email == payload.email).first()
        if user:
            log_audit_action(
                db=service.db,
                user_id=user.user_id,
                action_type="LOGIN_FAILED",
                entity_name="Authentication",
                record_id=str(user.user_id),
                new_value={"reason": getattr(e, "detail", "Unknown")},
                request=request,
            )
        raise


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
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    res = service.create_user(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role_id=payload.role_id,
        staff_id=payload.staff_id,
        lab_group_id=payload.lab_group_id,
        lab_ids=payload.lab_ids,
        primary_lab_id=payload.primary_lab_id,
        creator_admin_id=admin.get("id"),
        creator_role=admin.get("role"),
    )
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="CREATE",
        entity_name="User",
        record_id=payload.email,
        new_value={
            "email": payload.email,
            "role_id": payload.role_id,
            "full_name": payload.full_name,
        },
        request=request,
    )
    return res


@router.get("/roles", response_model=list[RoleResponse])
async def get_all_roles(service: AuthService = Depends(get_auth_service)):
    return service.get_all_roles()


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordSchema,
    service: AuthService = Depends(get_auth_service),
):
    service.forgot_password(payload.email)
    return {"message": "If that email exists, a temporary password has been sent."}


@router.get("/users")
async def get_all_users(
    role: str | None = Query(None),
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin_or_teamlead),
):
    if role:
        return service.get_users_by_role(role.strip().lower())
    return service.get_all_users()


@router.get("/assignment-targets")
async def get_assignment_targets(
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin_or_teamlead),
):
    """Lab Groups and Labs (id/name/group only, NO budget data) that an Admin
    or Team Lead may use when assigning users, across ALL Lab Groups.
    Budget/config endpoints stay scoped to the Team Lead's own Lab Group."""
    return service.get_assignment_targets()


@router.get("/assignments")
async def get_assignments(
    service: AuthService = Depends(get_auth_service),
    _admin: dict = Depends(require_admin_or_teamlead),
):
    return service.get_assignments()


@router.put("/users/{user_id}/assign-lab")
async def assign_lab_ic(
    user_id: int,
    payload: AssignLabSchema,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    res = service.assign_lab_to_user(
        user_id=user_id,
        lab_id=payload.lab_id,
        is_primary=payload.is_primary,
        assigned_by=admin.get("id"),
    )
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="UPDATE",
        entity_name="UserScope",
        record_id=str(user_id),
        new_value={
            "assigned_lab_id": payload.lab_id,
            "is_primary": payload.is_primary,
        },
        request=request,
    )
    return res


@router.put("/users/{user_id}/assign-labgroup")
async def assign_team_lead(
    user_id: int,
    payload: AssignLabGroupSchema,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    res = service.assign_labgroup_to_user(user_id, payload.lab_group_id)
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="UPDATE",
        entity_name="UserScope",
        record_id=str(user_id),
        new_value={"assigned_lab_group_id": payload.lab_group_id},
        request=request,
    )
    return res


@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    return service.deactivate_user(user_id, current_admin_id=admin["id"])


@router.put("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    return service.activate_user(user_id, current_admin_id=admin.get("id"))


@router.post("/users/{user_id}/send-reset")
async def admin_send_reset(
    user_id: int,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    user = _ensure_can_manage(service, admin, user_id)
    if user.role.role_name == "admin":
        raise HTTPException(
            status_code=403, detail="Admin passwords cannot be reset by another user."
        )
    service.forgot_password(user.email)
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="UPDATE",
        entity_name="UserPassword",
        record_id=str(user_id),
        new_value={"action": "admin_triggered_reset"},
        request=request,
    )
    return {"message": f"Temporary password sent to {user.email}."}


@router.put("/users/{user_id}/unassign-scope")
async def unassign_user_scope(
    user_id: int,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    res = service.unassign_user_scope(user_id)
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="UPDATE",
        entity_name="UserScope",
        record_id=str(user_id),
        new_value={"scope": "unassigned"},
        request=request,
    )
    return res


@router.delete("/users/{user_id}/labs/{lab_id}")
async def unassign_lab_from_user(
    user_id: int,
    lab_id: int,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    admin: dict = Depends(require_admin_or_teamlead),
):
    _ensure_can_manage(service, admin, user_id)
    res = service.unassign_lab_from_user(user_id, lab_id)
    log_audit_action(
        db=service.db,
        user_id=admin["id"],
        action_type="UPDATE",
        entity_name="UserScope",
        record_id=str(user_id),
        old_value={"assigned_lab_id": lab_id},
        new_value={"scope": "unassigned"},
        request=request,
    )
    return res


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


@router.post("/refresh")
async def refresh_session(
    response: Response,
    access_token: str | None = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    current_user = service.get_current_user(access_token)

    if current_user.get("must_reset_password", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset required before session can be extended.",
        )

    lab_ids = current_user.get("lab_ids", [])

    token_payload = {
        "sub": str(current_user["id"]),
        "email": current_user["email"],
        "role": current_user["role"],
        "lab_group_id": current_user["lab_group_id"],
        "lab_ids": lab_ids,
        "must_reset_password": current_user["must_reset_password"],
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
