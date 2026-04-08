from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from app.activity import log_activity, make_summary
from app.allowed_devices import is_device_allowed
from app.database import ONLINE_TIMEOUT_SECONDS, get_connection, utc_now
from app.files import device_upload_path
from app.models import (
    DeviceActionResultRequest,
    DeviceActionResultResponse,
    DeviceFilesRequest,
    DeviceFilesResponse,
    DeviceHelloRequest,
    DeviceHelloResponse,
    DeviceInfo,
    DeviceUploadResponse,
    DevicePollRequest,
    DevicePollResponse,
)


router = APIRouter()


SD_ACCESS_JOB_TYPES = {"download_file", "upload_file", "refresh_files"}


def update_device_state(
    connection,
    *,
    device_name: str,
    firmware_version: str | None = None,
    last_seen: str | None = None,
    is_online: bool | None = None,
    connection_status: str | None = None,
    usb_status: str | None = None,
    busy_status: str | None = None,
    free_space: int | None = None,
    total_space: int | None = None,
    ip_address: str | None = None,
    last_error: str | None = None,
) -> None:
    now = utc_now()
    existing = connection.execute(
        "SELECT device_name FROM device_state WHERE device_name = ?",
        (device_name,),
    ).fetchone()

    if existing is None:
        connection.execute(
            """
            INSERT INTO device_state (
                device_name,
                firmware_version,
                last_seen,
                is_online,
                connection_status,
                usb_status,
                busy_status,
                free_space,
                total_space,
                ip_address,
                last_error,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_name,
                firmware_version,
                last_seen,
                1 if is_online else 0,
                connection_status or "offline",
                usb_status or "unknown",
                busy_status or "unknown",
                free_space,
                total_space,
                ip_address,
                last_error,
                now,
            ),
        )
        return

    current = connection.execute(
        "SELECT * FROM device_state WHERE device_name = ?",
        (device_name,),
    ).fetchone()
    connection.execute(
        """
        UPDATE device_state
        SET firmware_version = ?,
            last_seen = ?,
            is_online = ?,
            connection_status = ?,
            usb_status = ?,
            busy_status = ?,
            free_space = ?,
            total_space = ?,
            ip_address = ?,
            last_error = ?,
            updated_at = ?
        WHERE device_name = ?
        """,
        (
            firmware_version if firmware_version is not None else current["firmware_version"],
            last_seen if last_seen is not None else current["last_seen"],
            (1 if is_online else 0) if is_online is not None else current["is_online"],
            connection_status if connection_status is not None else current["connection_status"],
            usb_status if usb_status is not None else current["usb_status"],
            busy_status if busy_status is not None else current["busy_status"],
            free_space if free_space is not None else current["free_space"],
            total_space if total_space is not None else current["total_space"],
            ip_address if ip_address is not None else current["ip_address"],
            last_error if last_error is not None else current["last_error"],
            now,
            device_name,
        ),
    )


def device_rejected_response(connection, endpoint: str, device_name: str, request_summary: str, reason: str):
    response_summary = make_summary(authorized=False, reason=reason)
    log_activity(
        connection,
        direction="device_to_server",
        endpoint=endpoint,
        event_type="device_rejected",
        status="rejected",
        device_name=device_name,
        request_summary=request_summary,
        response_summary=response_summary,
        details=reason,
    )
    return {"status": "rejected", "authorized": False, "reason": reason}


def promote_next_job(connection, device_name: str) -> None:
    running_job = connection.execute(
        "SELECT id FROM jobs WHERE device_name = ? AND status = 'running' LIMIT 1",
        (device_name,),
    ).fetchone()
    if running_job is not None:
        return

    pending_and_queued = connection.execute(
        """
        SELECT id, job_type, status
        FROM jobs
        WHERE device_name = ? AND status IN ('pending', 'queued')
        ORDER BY created_at ASC, id ASC
        """,
        (device_name,),
    ).fetchall()
    if not pending_and_queued:
        return

    priority_job = next((row for row in pending_and_queued if row["job_type"] in {"attach", "detach"}), None)
    if priority_job is not None:
        selected_job = priority_job
    else:
        selected_job = next((row for row in pending_and_queued if row["status"] == 'pending'), pending_and_queued[0])

    now = utc_now()
    connection.execute(
        "UPDATE jobs SET status = 'queued', updated_at = ? WHERE device_name = ? AND status = 'pending' AND id != ?",
        (now, device_name, selected_job["id"]),
    )
    if selected_job["status"] != 'pending':
        connection.execute(
            "UPDATE jobs SET status = 'pending', updated_at = ? WHERE id = ?",
            (now, selected_job["id"]),
        )


def try_dispatch_job(connection, payload: DevicePollRequest):
    if payload.connection_status != "online" or payload.busy_status == "busy":
        return None

    running_job = connection.execute(
        "SELECT id FROM jobs WHERE device_name = ? AND status = 'running' LIMIT 1",
        (payload.device_name,),
    ).fetchone()
    if running_job is not None:
        return None

    promote_next_job(connection, payload.device_name)

    next_job = connection.execute(
        """
        SELECT id, job_type, file_name, note
        FROM jobs
        WHERE device_name = ? AND status = 'pending'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (payload.device_name,),
    ).fetchone()
    if next_job is None:
        return None

    if next_job["job_type"] in SD_ACCESS_JOB_TYPES and payload.usb_status != "detached":
        return None

    connection.execute(
        "UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ?",
        (utc_now(), next_job["id"]),
    )
    return next_job


def update_job_from_action(
    connection,
    device_name: str,
    action: str,
    status_value: str,
    message: str | None,
    progress: int | None = None,
) -> None:
    row = connection.execute(
        """
        SELECT id, progress
        FROM jobs
        WHERE device_name = ? AND job_type = ? AND status IN ('running', 'pending')
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (device_name, action),
    ).fetchone()
    if row is None:
        return

    next_progress = row["progress"]
    if progress is not None:
        next_progress = progress
    elif status_value == "done":
        next_progress = 100

    next_status = "running" if status_value == "running" else status_value
    next_error_message = message if status_value == "error" else None
    connection.execute(
        "UPDATE jobs SET status = ?, progress = ?, updated_at = ?, error_message = ? WHERE id = ?",
        (next_status, next_progress, utc_now(), next_error_message, row["id"]),
    )
    if status_value in {"done", "error"}:
        promote_next_job(connection, device_name)


def mark_upload_job_completed(connection, device_name: str, file_name: str) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM jobs
        WHERE device_name = ? AND job_type = 'upload_file' AND file_name = ? AND status IN ('running', 'pending')
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (device_name, file_name),
    ).fetchone()
    if row is None:
        return

    connection.execute(
        "UPDATE jobs SET status = 'done', progress = 100, updated_at = ?, error_message = NULL WHERE id = ?",
        (utc_now(), row["id"]),
    )
    promote_next_job(connection, device_name)


@router.post("/device/hello", response_model=DeviceHelloResponse)
def device_hello(payload: DeviceHelloRequest) -> DeviceHelloResponse:
    request_summary = make_summary(
        firmware_version=payload.firmware_version,
        ip_address=payload.ip_address,
    )

    with get_connection() as connection:
        if not is_device_allowed(connection, payload.device_name):
            response = device_rejected_response(
                connection,
                "/device/hello",
                payload.device_name,
                request_summary,
                "device_not_allowed",
            )
            connection.commit()
            return DeviceHelloResponse(**response)

        update_device_state(
            connection,
            device_name=payload.device_name,
            firmware_version=payload.firmware_version,
            last_seen=utc_now(),
            is_online=True,
            connection_status="online",
            ip_address=payload.ip_address,
        )
        log_activity(
            connection,
            direction="device_to_server",
            endpoint="/device/hello",
            event_type="device_hello",
            status="ok",
            device_name=payload.device_name,
            request_summary=request_summary,
            response_summary="authorized=true",
        )
        connection.commit()

    return DeviceHelloResponse(status="ok", authorized=True)


@router.post("/device/poll", response_model=DevicePollResponse)
def device_poll(payload: DevicePollRequest) -> DevicePollResponse:
    request_summary = make_summary(
        firmware_version=payload.firmware_version,
        connection_status=payload.connection_status,
        usb_status=payload.usb_status,
        busy_status=payload.busy_status,
        free_space=payload.free_space,
        total_space=payload.total_space,
        ip_address=payload.ip_address,
    )

    with get_connection() as connection:
        if not is_device_allowed(connection, payload.device_name):
            response = device_rejected_response(
                connection,
                "/device/poll",
                payload.device_name,
                request_summary,
                "device_not_allowed",
            )
            connection.commit()
            return DevicePollResponse(job_type="none", **response)

        update_device_state(
            connection,
            device_name=payload.device_name,
            firmware_version=payload.firmware_version,
            last_seen=utc_now(),
            is_online=payload.connection_status == "online",
            connection_status=payload.connection_status,
            usb_status=payload.usb_status,
            busy_status=payload.busy_status,
            free_space=payload.free_space,
            total_space=payload.total_space,
            ip_address=payload.ip_address,
        )

        job = try_dispatch_job(connection, payload)
        if job is None:
            log_activity(
                connection,
                direction="device_to_server",
                endpoint="/device/poll",
                event_type="device_poll",
                status="ok",
                device_name=payload.device_name,
                request_summary=request_summary,
                response_summary="job=none",
            )
            connection.commit()
            return DevicePollResponse(job_type="none")

        response = DevicePollResponse(
            job_type=job["job_type"],
            file_name=job["file_name"] or None,
            note=job["note"],
        )
        log_activity(
            connection,
            direction="server_to_device",
            endpoint="/device/poll",
            event_type="job_sent",
            status="ok",
            device_name=payload.device_name,
            request_summary=request_summary,
            response_summary=make_summary(job=job["job_type"], file_name=job["file_name"], note=job["note"]),
        )
        connection.commit()
        return response


@router.post("/device/files", response_model=DeviceFilesResponse)
def device_files(payload: DeviceFilesRequest) -> DeviceFilesResponse:
    directories_count = sum(1 for item in payload.files if item.is_dir)
    request_summary = make_summary(files_received=len(payload.files), directories=directories_count)

    with get_connection() as connection:
        if not is_device_allowed(connection, payload.device_name):
            response = device_rejected_response(
                connection,
                "/device/files",
                payload.device_name,
                request_summary,
                "device_not_allowed",
            )
            connection.commit()
            return DeviceFilesResponse(status=response["status"], files_received=0)

        synced_at = utc_now()
        connection.execute("DELETE FROM device_files WHERE device_name = ?", (payload.device_name,))
        for item in payload.files:
            connection.execute(
                """
                INSERT INTO device_files (device_name, file_name, file_size, modified_at, is_dir, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.device_name, item.file_name, item.file_size, item.modified_at, 1 if item.is_dir else 0, synced_at),
            )

        log_activity(
            connection,
            direction="device_to_server",
            endpoint="/device/files",
            event_type="file_list_updated",
            status="ok",
            device_name=payload.device_name,
            request_summary=request_summary,
            response_summary=make_summary(files_received=len(payload.files), directories=directories_count),
        )
        connection.commit()

    return DeviceFilesResponse(status="ok", files_received=len(payload.files))


@router.post("/device/action-result", response_model=DeviceActionResultResponse)
def device_action_result(payload: DeviceActionResultRequest) -> DeviceActionResultResponse:
    request_summary = make_summary(action=payload.action, status=payload.status, progress=payload.progress, message=payload.message)

    with get_connection() as connection:
        if not is_device_allowed(connection, payload.device_name):
            response = device_rejected_response(
                connection,
                "/device/action-result",
                payload.device_name,
                request_summary,
                "device_not_allowed",
            )
            connection.commit()
            return DeviceActionResultResponse(
                status=response["status"],
                action=payload.action,
                device_name=payload.device_name,
                message=payload.message,
            )

        last_error = payload.message if payload.status == "error" else ""
        usb_status = None
        if payload.status == "running":
            busy_status = "busy"
        elif payload.status == "done":
            busy_status = "idle"
        else:
            busy_status = "error"
        if payload.action == "attach" and payload.status == "done":
            usb_status = "attached"
        elif payload.action == "detach" and payload.status == "done":
            usb_status = "detached"

        update_device_state(
            connection,
            device_name=payload.device_name,
            is_online=True,
            last_seen=utc_now(),
            busy_status=busy_status,
            usb_status=usb_status,
            last_error=last_error,
        )
        update_job_from_action(connection, payload.device_name, payload.action, payload.status, payload.message, payload.progress)
        log_activity(
            connection,
            direction="device_to_server",
            endpoint="/device/action-result",
            event_type="job_progress" if payload.status == "running" else "job_done" if payload.status == "done" else "error",
            status=payload.status,
            device_name=payload.device_name,
            request_summary=request_summary,
            response_summary=make_summary(action=payload.action, status=payload.status, progress=payload.progress),
            details=payload.message,
        )
        connection.commit()

    return DeviceActionResultResponse(
        status=payload.status,
        action=payload.action,
        device_name=payload.device_name,
        message=payload.message,
        progress=payload.progress,
    )


@router.post("/device/upload", response_model=DeviceUploadResponse)
async def device_upload_file(
    request: Request,
    device_name: str = Query(...),
    file_name: str = Query(...),
) -> DeviceUploadResponse:
    content = await request.body()

    with get_connection() as connection:
        if not is_device_allowed(connection, device_name):
            response = device_rejected_response(
                connection,
                "/device/upload",
                device_name,
                make_summary(file_name=file_name, bytes=len(content)),
                "device_not_allowed",
            )
            connection.commit()
            return DeviceUploadResponse(
                status=response["status"],
                device_name=device_name,
                file_name=file_name,
                stored_path="",
                bytes_received=0,
            )

        destination = device_upload_path(device_name, file_name)
        destination.write_bytes(content)
        stored_path = str(destination.relative_to(destination.parents[2])).replace(chr(92), "/")
        mark_upload_job_completed(connection, device_name, file_name)
        log_activity(
            connection,
            direction="device_to_server",
            endpoint="/device/upload",
            event_type="device_file_uploaded_to_server",
            status="ok",
            device_name=device_name,
            request_summary=make_summary(file_name=file_name, bytes=len(content)),
            response_summary=make_summary(stored_path=stored_path),
        )
        connection.commit()

    return DeviceUploadResponse(
        status="ok",
        device_name=device_name,
        file_name=file_name,
        stored_path=stored_path,
        bytes_received=len(content),
    )


@router.get("/devices", response_model=list[DeviceInfo])
def list_devices() -> list[DeviceInfo]:
    now = datetime.now(UTC)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT ad.device_name,
                   ds.last_seen,
                   ds.connection_status,
                   ds.usb_status,
                   ds.busy_status,
                   ds.free_space,
                   ds.total_space,
                   ds.ip_address,
                   ds.firmware_version
            FROM allowed_devices ad
            LEFT JOIN device_state ds ON ds.device_name = ad.device_name
            ORDER BY ad.device_name ASC
            """
        ).fetchall()

        devices: list[DeviceInfo] = []
        stale_device_names: list[str] = []
        for row in rows:
            last_seen = row["last_seen"]
            is_online = False
            if last_seen:
                seen_at = datetime.fromisoformat(last_seen)
                is_online = (now - seen_at).total_seconds() <= ONLINE_TIMEOUT_SECONDS

            effective_connection_status = row["connection_status"] or "offline"
            if not is_online:
                effective_connection_status = "offline"
                if row["connection_status"] and row["connection_status"] != "offline":
                    stale_device_names.append(row["device_name"])

            devices.append(
                DeviceInfo(
                    device_name=row["device_name"],
                    is_online=is_online,
                    last_seen=last_seen,
                    connection_status=effective_connection_status,
                    usb_status=row["usb_status"] or "unknown",
                    busy_status=row["busy_status"] or "unknown",
                    free_space=row["free_space"],
                    total_space=row["total_space"],
                    ip_address=row["ip_address"],
                    firmware_version=row["firmware_version"],
                )
            )

        if stale_device_names:
            connection.executemany(
                "UPDATE device_state SET is_online = 0, connection_status = 'offline', updated_at = ? WHERE device_name = ?",
                [(utc_now(), device_name) for device_name in stale_device_names],
            )
            connection.commit()

    return devices
