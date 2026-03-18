from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.database import UPLOADS_DIR, get_connection
from app.models import (
    CreateJobRequest,
    JobCreateResponse,
    JobDoneRequest,
    JobDoneResponse,
    UploadResponse,
)


router = APIRouter()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def safe_file_name(file_name: str) -> str:
    normalized_name = Path(file_name).name
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_name is required",
        )
    return normalized_name


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    request: Request,
    file_name: str = Query(..., description="Target file name, for example test.nc"),
) -> UploadResponse:
    safe_name = safe_file_name(file_name)
    content = await request.body()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is empty",
        )

    destination = UPLOADS_DIR / safe_name
    destination.write_bytes(content)

    return UploadResponse(status="ok", file_name=safe_name)


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: CreateJobRequest) -> JobCreateResponse:
    safe_name = safe_file_name(payload.file_name)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (device_id, job_type, file_name, status, created_at)
            VALUES (?, 'download', ?, 'pending', ?)
            """,
            (payload.device_id, safe_name, utc_now()),
        )
        connection.commit()

    return JobCreateResponse(
        status="ok",
        job_id=cursor.lastrowid,
        device_id=payload.device_id,
        file_name=safe_name,
    )


@router.post("/jobs/done", response_model=JobDoneResponse)
def job_done(payload: JobDoneRequest) -> JobDoneResponse:
    safe_name = safe_file_name(payload.file_name)

    with get_connection() as connection:
        job = connection.execute(
            """
            SELECT id
            FROM jobs
            WHERE device_id = ? AND file_name = ? AND status IN ('running', 'pending')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (payload.device_id, safe_name),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        connection.execute(
            "UPDATE jobs SET status = ? WHERE id = ?",
            (payload.status, job["id"]),
        )
        connection.commit()

    return JobDoneResponse(
        status=payload.status,
        device_id=payload.device_id,
        file_name=safe_name,
    )
