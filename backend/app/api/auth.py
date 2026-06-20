from fastapi import APIRouter, Depends, Response, Cookie
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth_schema import LoginRequest
from app.services.auth_service import AuthService
from app.repositories.auth_repository import AuthRepository

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    service = AuthService(
        repository=AuthRepository(),
        db=db
    )
    return service.login(
        payload.email,
        payload.password,
        response
    )

@router.get("/me")
async def me(
    access_token: str | None = Cookie(None),
    db: Session = Depends(get_db)
):
    service = AuthService(
        repository=AuthRepository(),
        db=db
    )
    return service.get_current_user(
        access_token
    )

@router.post("/logout")
async def logout(
    response: Response
):
    response.delete_cookie(
        "access_token",
        path="/",          # Explicit path ensures it clears reliably across sub-routes
        httponly=True,     # Matches secure cookie standards
        samesite="lax"
    )
    return {
        "message": "Logged out"
    }