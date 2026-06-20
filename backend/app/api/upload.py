import hashlib

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    role = x_user_role.lower().strip()
    _ensure_upload_role(role)

    payload = await file.read()

    service = UploadService(repository=UploadRepository(), db=db)

    return service.process_upload(
        filename=file.filename or "upload",
        content=payload,
        uploader_email=x_user_email,
        uploader_name=x_user_name,
        uploader_role=role,
        current_user=current_user,
    )


@router.post("/process-batch")
async def process_upload_batch(
    files: list[UploadFile] = File(...),
    x_user_email: str = Header(default="demo.teamlead@sit.edu.sg"),
    x_user_name: str = Header(default="Demo Team Lead"),
    x_user_role: str = Header(default="teamlead"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    role = x_user_role.lower().strip()
    _ensure_upload_role(role)

    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one CSV or Excel file.")

    service = UploadService(repository=UploadRepository(), db=db)
    results = []
    seen_file_hashes: dict[str, str] = {}
    for file in files:
        payload = await file.read()
        digest = hashlib.sha256(payload).hexdigest()
        if digest in seen_file_hashes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Duplicate file in batch: "
                    f"{file.filename or 'upload'} has the same content as {seen_file_hashes[digest]}."
                ),
            )
        seen_file_hashes[digest] = file.filename or "upload"
        results.append(
            service.process_upload(
                filename=file.filename or "upload",
                content=payload,
                uploader_email=x_user_email,
                uploader_name=x_user_name,
                uploader_role=role,
                current_user=current_user,
            )
        )

    return _combine_batch_results(results, x_user_email, x_user_name, role)


def _ensure_upload_role(role: str) -> None:
    if role not in ALLOWED_UPLOAD_ROLES:
        raise HTTPException(status_code=403, detail="Lab IC users cannot upload PR files.")


def _combine_batch_results(results: list[dict], uploader_email: str, uploader_name: str, role: str) -> dict:
    combined = {
        "success": all(result["success"] for result in results),
        "metadata": {
            "batch_id": ",".join(result["metadata"]["batch_id"] for result in results),
            "filename": f"{len(results)} files",
            "uploader_email": uploader_email,
            "uploader_name": uploader_name,
            "uploader_role": role,
            "uploaded_at": results[-1]["metadata"]["uploaded_at"],
            "files": [result["metadata"] for result in results],
        },
        "counts": {
            "total_lines": 0,
            "accepted": 0,
            "duplicate_skipped": 0,
            "reupload_updated": 0,
            "needs_review": 0,
            "rejected": 0,
        },
        "validation_errors": [],
        "records": {"inserted": [], "updated": [], "duplicate": []},
    }

    for result in results:
        filename = result["metadata"]["filename"]
        for key in combined["counts"]:
            combined["counts"][key] += result["counts"][key]
        for error in result["validation_errors"]:
            combined["validation_errors"].append({**error, "field": f"{filename} - {error['field']}"})
        for status in combined["records"]:
            combined["records"][status].extend(result["records"][status])

    return combined
