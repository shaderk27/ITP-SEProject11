from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_UPLOAD_ROLES = {"admin", "teamlead"}


@router.post("/process")
async def process_upload(
    file: UploadFile = File(...),
    x_user_email: str = Header(default="demo.teamlead@sit.edu.sg"),
    x_user_name: str = Header(default="Demo Team Lead"),
    x_user_role: str = Header(default="teamlead"),
) -> dict:
    role = x_user_role.lower().strip()
    if role not in ALLOWED_UPLOAD_ROLES:
        raise HTTPException(
            status_code=403, detail="Lab IC users cannot upload PR files."
        )

    payload = await file.read()
    service = UploadService(repository=UploadRepository())
    return service.process_upload(
        filename=file.filename or "upload",
        content=payload,
        uploader_email=x_user_email,
        uploader_name=x_user_name,
        uploader_role=role,
    )
