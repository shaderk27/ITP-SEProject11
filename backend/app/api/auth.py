from typing import List

from fastapi import APIRouter, Depends, Response, Cookie, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth_schema import LoginRequest,CreateUserRequest, RoleResponse
from app.services.auth_service import AuthService
from app.repositories.auth_repository import AuthRepository


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/login")
async def login(
    request: Request,  # Brought in the request object to read the raw body if it fails
    response: Response,
    db: Session = Depends(get_db)
):
    raw_body = await request.body()
    
    try:
        payload = LoginRequest.model_validate_json(raw_body)
    except Exception as exc:
        print("\n--- 422 VALIDATION DEBUGGER LOG ---")
        print(f"Raw body string received from React: {raw_body.decode('utf-8', errors='ignore')}")
        print(f"Validation details: {str(exc)}")
        print("-----------------------------------\n")
        
        raise RequestValidationError(errors=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}])

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
        path="/",
        httponly=True,
        samesite="lax"
    )
    return {
        "message": "Logged out"
    }
    
@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db)
):
    service = AuthService(
        repository=AuthRepository(),
        db=db
    )
    return service.create_user(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role_id=payload.role_id,
        staff_id=payload.staff_id,
        lab_group_id=payload.lab_group_id
    )
@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(
    db: Session = Depends(get_db)
):
    service = AuthService(
        repository=AuthRepository(),
        db=db
    )
    return service.get_all_roles()