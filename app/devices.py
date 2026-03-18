from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.database import get_connection
from app.models import DeviceInfo, DevicePoll, JobResponse


router = APIRouter()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@router.post("/device/poll", response_model=JobResponse)
def device_poll(payload: DevicePoll) -> JobResponse:
    last_seen = utc_now()

    with get_connection() as connection:
        existing_device = connection.execute(
            "SELECT device_id FROM devices WHERE device_id = ?",
            (payload.device_id,),
        ).fetchone()

        if existing_device:
            connection.execute(
                """
                UPDATE devices
                SET last_seen = ?, status = ?
                WHERE device_id = ?
                """,
                (last_seen, payload.status, payload.device_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO devices (device_id, device_name, last_seen, status)
                VALUES (?, ?, ?, ?)
                """,
                (payload.device_id, payload.device_id, last_seen, payload.status),
            )

        job = connection.execute(
            """
            SELECT id, job_type, file_name
            FROM jobs
            WHERE device_id = ? AND status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (payload.device_id,),
        ).fetchone()

        if job is None:
            connection.commit()
            return JobResponse(job_type="none", file_name=None)

        connection.execute(
            "UPDATE jobs SET status = 'running' WHERE id = ?",
            (job["id"],),
        )
        connection.commit()

    return JobResponse(job_type=job["job_type"], file_name=job["file_name"])


@router.get("/devices", response_model=list[DeviceInfo])
def list_devices() -> list[DeviceInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT device_id, last_seen, status
            FROM devices
            ORDER BY device_id ASC
            """
        ).fetchall()

    return [
        DeviceInfo(
            device_id=row["device_id"],
            last_seen=row["last_seen"],
            status=row["status"],
        )
        for row in rows
    ]
