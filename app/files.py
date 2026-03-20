from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.allowed_devices import get_allowed_device_row
from app.database import UPLOADS_DIR, get_connection
from app.models import DeviceFileInfo, ServerFileInfo


router = APIRouter()


@router.get("/files/server", response_model=list[ServerFileInfo])
def list_server_files() -> list[ServerFileInfo]:
    files: list[ServerFileInfo] = []
    for path in sorted(UPLOADS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            ServerFileInfo(
                file_name=path.name,
                file_size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            )
        )
    return files


@router.get("/files/device/{device_name}", response_model=list[DeviceFileInfo])
def list_device_files(device_name: str) -> list[DeviceFileInfo]:
    with get_connection() as connection:
        allowed = get_allowed_device_row(connection, device_name)
        if allowed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed device not found")

        rows = connection.execute(
            """
            SELECT device_name, file_name, file_size, modified_at, synced_at
            FROM device_files
            WHERE device_name = ?
            ORDER BY file_name ASC
            """,
            (device_name,),
        ).fetchall()

    return [
        DeviceFileInfo(
            device_name=row["device_name"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            modified_at=row["modified_at"],
            synced_at=row["synced_at"],
        )
        for row in rows
    ]
