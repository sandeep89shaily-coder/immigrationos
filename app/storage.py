"""Development-only encrypted blob store for fictional/synthetic test documents.

Not production approved: antivirus, DLP, retention, backups and enterprise key
management are deliberately out of scope. No server-side MIME sniffing library.
"""
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.settings import get_settings

MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {
    "application/pdf": (".pdf", lambda b: b.startswith(b"%PDF-")),
    "image/png": (".png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/jpeg": (".jpg", lambda b: b.startswith(b"\xff\xd8")),
    "text/plain": (".txt", lambda b: b.find(b"\x00") == -1),
}


def _conf():
    settings = get_settings()
    if not settings.uploads_enabled or settings.environment == "production":
        raise HTTPException(status_code=503, detail="Document uploads disabled in this environment")
    try:
        cipher = Fernet(settings.document_encryption_key.encode())
    except Exception:
        raise HTTPException(status_code=503, detail="Invalid document encryption configuration") from None
    return Path(settings.document_storage_root), cipher


def save_blob(data: bytes, mime: str) -> tuple[str, str]:
    root, cipher = _conf()
    validator = ALLOWED.get(mime)
    if validator is None or not validator[1](data):
        raise HTTPException(status_code=415, detail="Unsupported or mismatched document type")
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Document must be between 1 byte and 8 MB")
    if mime == "text/plain":
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail="Text upload must be UTF-8") from None
    key = uuid4().hex
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL avoids accidental overwrite; key is generated server-side.
    path = root / key
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(cipher.encrypt(data))
    return key, hashlib.sha256(data).hexdigest()


def load_blob(key: str) -> bytes:
    root, cipher = _conf()
    if len(key) != 32 or not all(ch in '0123456789abcdef' for ch in key):
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return cipher.decrypt((root / key).read_bytes())
    except (FileNotFoundError, InvalidToken):
        raise HTTPException(status_code=404, detail="Document not found") from None


def delete_failed_blob(key: str):
    root = Path(get_settings().document_storage_root)
    (root / key).unlink(missing_ok=True)
