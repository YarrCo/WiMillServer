from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.activity import log_activity, make_summary
from app.allowed_devices import is_device_allowed
from app.database import UPLOADS_DIR, get_connection, utc_now
from app.models import CreateJobRequest, JobCreateResponse, JobDoneRequest, JobDoneResponse, JobInfo, UploadResponse


router = APIRouter()


def safe_file_name(file_name: str | None) -> str:
    if file_name is None:
        return ""
    return Path(file_name).name.strip()


def ensure_user_device_exists(connection, device_name: str) -> None:
    if not is_device_allowed(connection, device_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allowed device not found",
        )


def promote_next_job(connection, device_name: str) -> None:
    active_job = connection.execute(
        "SELECT id FROM jobs WHERE device_name = ? AND status IN ('pending', 'running') LIMIT 1",
        (device_name,),
    ).fetchone()
    if active_job is not None:
        return

    queued_job = connection.execute(
        """
        SELECT id FROM jobs
        WHERE device_name = ? AND status = 'queued'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (device_name,),
    ).fetchone()
    if queued_job is None:
        return

    connection.execute(
        "UPDATE jobs SET status = 'pending', updated_at = ? WHERE id = ?",
        (utc_now(), queued_job["id"]),
    )


@router.get("/jobs", response_model=list[JobInfo])
def list_jobs(
    device_name: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JobInfo]:
    query = """
        SELECT id, device_name, job_type, file_name, status, progress,
               created_at, updated_at, error_message, source, note
        FROM jobs
    """
    conditions: list[str] = []
    params: list[object] = []

    if device_name:
        conditions.append("device_name = ?")
        params.append(device_name)
    if status_value:
        conditions.append("status = ?")
        params.append(status_value)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at ASC, id ASC LIMIT ?"
    params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    return [
        JobInfo(
            id=row["id"],
            device_name=row["device_name"],
            job_type=row["job_type"],
            file_name=row["file_name"] or None,
            status=row["status"],
            progress=row["progress"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
            source=row["source"],
            note=row["note"],
        )
        for row in rows
    ]


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    request: Request,
    file_name: str = Query(..., description="Target file name, for example test.nc"),
) -> UploadResponse:
    safe_name = safe_file_name(file_name)
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_name is required",
        )

    content = await request.body()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is empty",
        )

    destination = UPLOADS_DIR / safe_name
    destination.write_bytes(content)

    with get_connection() as connection:
        log_activity(
            connection,
            direction="user_to_server",
            endpoint="/upload",
            event_type="file_uploaded",
            status="ok",
            request_summary=make_summary(file_name=safe_name, bytes=len(content)),
            response_summary=make_summary(file_name=safe_name),
        )
        connection.commit()

    return UploadResponse(status="ok", file_name=safe_name)


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: CreateJobRequest) -> JobCreateResponse:
    safe_name = safe_file_name(payload.file_name)
    if payload.job_type in {"download_file", "upload_file"} and not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_name is required for file jobs",
        )

    now = utc_now()
    event_type = {
        "attach": "manual_attach_request",
        "detach": "manual_detach_request",
    }.get(payload.job_type, "job_created")

    with get_connection() as connection:
        ensure_user_device_exists(connection, payload.device_name)
        active_job = connection.execute(
            "SELECT id FROM jobs WHERE device_name = ? AND status IN ('pending', 'running') LIMIT 1",
            (payload.device_name,),
        ).fetchone()
        job_status = "queued" if active_job is not None else "pending"

        cursor = connection.execute(
            """
            INSERT INTO jobs (
                device_name,
                job_type,
                file_name,
                status,
                created_at,
                updated_at,
                error_message,
                progress,
                source,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)
            """,
            (
                payload.device_name,
                payload.job_type,
                safe_name,
                job_status,
                now,
                now,
                payload.source,
                payload.note,
            ),
        )
        log_activity(
            connection,
            direction="user_to_server",
            endpoint="/jobs",
            event_type=event_type,
            status="ok",
            device_name=payload.device_name,
            request_summary=make_summary(
                job_type=payload.job_type,
                file_name=safe_name,
                source=payload.source,
                note=payload.note,
            ),
            response_summary=make_summary(job_id=cursor.lastrowid, job_status=job_status),
        )
        connection.commit()

    return JobCreateResponse(
        status="ok",
        job_id=cursor.lastrowid,
        device_name=payload.device_name,
        job_type=payload.job_type,
        file_name=safe_name or None,
        job_status=job_status,
        source=payload.source,
        note=payload.note,
    )


@router.post("/jobs/done", response_model=JobDoneResponse)
def job_done(payload: JobDoneRequest) -> JobDoneResponse:
    safe_name = safe_file_name(payload.file_name)

    with get_connection() as connection:
        if not is_device_allowed(connection, payload.device_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Allowed device not found",
            )

        if safe_name:
            job = connection.execute(
                """
                SELECT id
                FROM jobs
                WHERE device_name = ? AND file_name = ? AND status IN ('running', 'pending')
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT 1
                """,
                (payload.device_name, safe_name),
            ).fetchone()
        else:
            job = connection.execute(
                """
                SELECT id
                FROM jobs
                WHERE device_name = ? AND status IN ('running', 'pending')
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT 1
                """,
                (payload.device_name,),
            ).fetchone()

        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        connection.execute(
            "UPDATE jobs SET status = ?, updated_at = ?, error_message = ? WHERE id = ?",
            (payload.status, utc_now(), payload.message, job["id"]),
        )
        promote_next_job(connection, payload.device_name)
        log_activity(
            connection,
            direction="device_to_server",
            endpoint="/jobs/done",
            event_type="job_done" if payload.status == "done" else "error",
            status=payload.status,
            device_name=payload.device_name,
            request_summary=make_summary(file_name=safe_name, message=payload.message),
            response_summary=make_summary(file_name=safe_name, status=payload.status),
        )
        connection.commit()

    return JobDoneResponse(status=payload.status, device_name=payload.device_name, file_name=safe_name or None)
