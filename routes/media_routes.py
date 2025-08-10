from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from routes.auth_routes import get_current_user
from db import get_db
import os
import shutil
import uuid

router = APIRouter(prefix="/media", tags=["media"]) 

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_ROOT = os.path.join(os.getcwd(), "static", "uploads")

os.makedirs(UPLOAD_ROOT, exist_ok=True)


def _allowed(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS


@router.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    alt_text: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not _allowed(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type. Allowed: png, jpg, jpeg, gif, webp")

    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    save_path = os.path.join(UPLOAD_ROOT, unique_name)

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save image: {e}")
    finally:
        file.file.close()

    public_url = f"/static/uploads/{unique_name}"
    alt = alt_text or safe_name
    markdown = f"![{alt}]({public_url})"

    return JSONResponse(
        status_code=201,
        content={
            "url": public_url,
            "filename": unique_name,
            "markdown": markdown,
            "message": "Image uploaded successfully",
        },
    )
