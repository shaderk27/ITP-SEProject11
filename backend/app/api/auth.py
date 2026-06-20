from fastapi import APIRouter, Depends, Response, Cookie, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
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
    request: Request,  # Brought in the request object to read the raw body if it fails
    response: Response,
    db: Session = Depends(get_db)
):
    # We read the body safely first, then manually validate it to catch the 422 error
    raw_body = await request.body()
    
    try:
        # Manually trigger validation against your Pydantic schema
        # In Pydantic v2 use: LoginRequest.model_validate_json(raw_body)
        # In Pydantic v1 use: LoginRequest.parse_raw(raw_body)
        payload = LoginRequest.model_validate_json(raw_body)
    except Exception as exc:
        print("\n--- 422 VALIDATION DEBUGGER LOG ---")
        print(f"Raw body string received from React: {raw_body.decode('utf-8', errors='ignore')}")
        print(f"Validation details: {str(exc)}")
        print("-----------------------------------\n")
        
        # Re-raise it so the frontend still gets its expected 422 structural breakdown
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