# app/core/media.py
import os
import uuid
from fastapi import UploadFile, HTTPException, status

from app.core.config import settings

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


async def save_upload_file(upload_file: UploadFile, subdir: str) -> str:
    """
    Saves an uploaded file under MEDIA_ROOT/subdir/<uuid><ext> and returns
    the path *relative to MEDIA_ROOT* (e.g. "expenses/ab12cd.jpg") — store
    this relative path in the DB, not an absolute path or full URL, same
    pattern already used for photo storage on ONA24 (backend stores
    relative paths; whatever serves the app in front builds the full URL).
    """
    ext = os.path.splitext(upload_file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )

    contents = await upload_file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size is {settings.MAX_UPLOAD_MB}MB",
        )

    target_dir = os.path.join(settings.MEDIA_ROOT, subdir)
    _ensure_dir(target_dir)

    filename = f"{uuid.uuid4().hex}{ext}"
    relative_path = os.path.join(subdir, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    with open(full_path, "wb") as f:
        f.write(contents)

    return relative_path.replace(os.sep, "/")


def delete_upload_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    try:
        if os.path.isfile(full_path):
            os.remove(full_path)
    except OSError:
        pass
