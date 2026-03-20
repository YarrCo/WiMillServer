from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.activity import log_activity, make_summary
from app.allowed_devices import get_allowed_device_row
from app.database import UPLOADS_DIR, get_connection
from app.models import DeviceFileInfo, ServerFileInfo


router = APIRouter()


def safe_server_file_name(file_name: str) -> str:
    safe_name = Path(file_name).name.strip()
    if not safe_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_name is required")
    return safe_name


def server_file_path(file_name: str) -> Path:
    safe_name = safe_server_file_name(file_name)
    path = UPLOADS_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server file not found")
    return path


def server_file_infos() -> list[ServerFileInfo]:
    files: list[ServerFileInfo] = []
    for path in sorted(UPLOADS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name == ".gitkeep":
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


def delete_server_file(file_name: str, *, endpoint: str = "/files/server/delete") -> str:
    path = server_file_path(file_name)
    path.unlink()

    with get_connection() as connection:
        log_activity(
            connection,
            direction="user_to_server",
            endpoint=endpoint,
            event_type="server_file_deleted",
            status="ok",
            request_summary=make_summary(file_name=path.name),
            response_summary="deleted=true",
        )
        connection.commit()

    return path.name


@router.get("/files/server", response_model=list[ServerFileInfo])
def list_server_files() -> list[ServerFileInfo]:
    return server_file_infos()


@router.get("/files/server/download/{file_name}")
def download_server_file(file_name: str) -> FileResponse:
    path = server_file_path(file_name)
    return FileResponse(path, filename=path.name)


@router.post("/files/server/delete/{file_name}")
def delete_server_file_endpoint(file_name: str) -> dict[str, str]:
    deleted_name = delete_server_file(file_name)
    return {"status": "ok", "file_name": deleted_name}


@router.get("/files/device/{device_name}", response_model=list[DeviceFileInfo])
def list_device_files(device_name: str) -> list[DeviceFileInfo]:
    with get_connection() as connection:
        allowed = get_allowed_device_row(connection, device_name)
        if allowed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed device not found")

        rows = connection.execute(
            """
            SELECT device_name, file_name, file_size, modified_at, is_dir, synced_at
            FROM device_files
            WHERE device_name = ?
            ORDER BY is_dir DESC, file_name ASC
            """,
            (device_name,),
        ).fetchall()

    return [
        DeviceFileInfo(
            device_name=row["device_name"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            modified_at=row["modified_at"],
            is_dir=bool(row["is_dir"]),
            synced_at=row["synced_at"],
        )
        for row in rows
    ]
