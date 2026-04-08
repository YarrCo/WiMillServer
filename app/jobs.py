from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.activity import log_activity, make_summary
from app.allowed_devices import is_device_allowed
from app.files import safe_device_relative_path
from app.database import UPLOADS_DIR, get_connection, utc_now
from app.models import CreateJobRequest, JobCreateResponse, JobDoneRequest, JobDoneResponse, JobInfo, UploadResponse


router = APIRouter()

LEGACY_JOB_TYPE_MAP = {
    "download": "download_file",
    "upload": "upload_file",
}
FINISHED_STATUSES = {"done", "error"}
ACTIVE_STATUSES = {"pending", "running"}


def normalize_job_type(job_type: str | None) -> str:
    if not job_type:
        return "download_file"
    return LEGACY_JOB_TYPE_MAP.get(job_type, job_type)


def safe_file_name(file_name: str | None) -> str:
    if file_name is None:
        return ""
    return Path(file_name).name.strip()


def normalize_job_file_name(job_type: str, file_name: str | None) -> str:
    if file_name is None:
        return ""
    if job_type == "upload_file":
        return safe_device_relative_path(file_name).as_posix()
    return safe_file_name(file_name)


def save_upload_content(
    *,
    file_name: str,
    content: bytes,
    endpoint: str = "/upload",
    direction: str = "user_to_server",
) -> str:
    safe_name = safe_file_name(file_name)
    if not safe_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_name is required")

    destination = UPLOADS_DIR / safe_name
    destination.write_bytes(content)

    with get_connection() as connection:
        log_activity(
            connection,
            direction=direction,
            endpoint=endpoint,
            event_type="file_uploaded",
            status="ok",
            request_summary=make_summary(file_name=safe_name, bytes=len(content)),
            response_summary=make_summary(file_name=safe_name),
        )
        connection.commit()

    return safe_name


def ensure_user_device_exists(connection, device_name: str) -> None:
    if not is_device_allowed(connection, device_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed device not found")


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


def finish_job(job_id: int, *, endpoint: str = "/ui/jobs/finish", message: str = "finished from ui") -> dict[str, object]:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, device_name, job_type, file_name, status FROM jobs WHERE id = ? LIMIT 1",
            (job_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        previous_status = row["status"]
        if previous_status not in FINISHED_STATUSES:
            connection.execute(
                "UPDATE jobs SET status = 'done', updated_at = ?, error_message = ? WHERE id = ?",
                (utc_now(), message, job_id),
            )
            device_name = row["device_name"]
            if device_name and previous_status in ACTIVE_STATUSES:
                promote_next_job(connection, device_name)
            log_activity(
                connection,
                direction="user_to_server",
                endpoint=endpoint,
                event_type="job_finished_manually",
                status="ok",
                device_name=device_name,
                request_summary=make_summary(job_id=job_id, previous_status=previous_status),
                response_summary=make_summary(job_id=job_id, status="done"),
                details=message,
            )
            connection.commit()
            previous_status = "done"

        return {
            "id": row["id"],
            "device_name": row["device_name"],
            "job_type": normalize_job_type(row["job_type"]),
            "file_name": row["file_name"],
            "status": previous_status,
        }


def clear_finished_jobs(*, endpoint: str = "/ui/jobs/clear-finished") -> int:
    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS total FROM jobs WHERE status IN ('done', 'error')"
        ).fetchone()["total"]
        if count:
            connection.execute("DELETE FROM jobs WHERE status IN ('done', 'error')")
            log_activity(
                connection,
                direction="user_to_server",
                endpoint=endpoint,
                event_type="jobs_cleared",
                status="ok",
                request_summary="statuses=done,error",
                response_summary=make_summary(deleted=count),
            )
            connection.commit()
        return int(count)


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
            job_type=normalize_job_type(row["job_type"]),
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
    safe_name = save_upload_content(file_name=file_name, content=await request.body())
    return UploadResponse(status="ok", file_name=safe_name)


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: CreateJobRequest) -> JobCreateResponse:
    safe_name = normalize_job_file_name(payload.job_type, payload.file_name)
    if payload.job_type in {"download_file", "upload_file"} and not safe_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_name is required for file jobs")

    now = utc_now()
    event_type = {
        "attach": "manual_attach_request",
        "detach": "manual_detach_request",
        "refresh_files": "file_list_refresh_requested",
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
                device_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)
            """,
            (
                payload.device_name,
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed device not found")

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
