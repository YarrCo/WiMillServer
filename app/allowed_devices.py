from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.activity import log_activity, make_summary
from app.database import get_connection, utc_now
from app.models import AllowedDeviceCreate, AllowedDeviceInfo, AllowedDeviceToggleRequest


router = APIRouter()


def get_allowed_device_row(connection, device_name: str):
    return connection.execute(
        """
        SELECT device_name, description, is_enabled, created_at, updated_at
        FROM allowed_devices
        WHERE device_name = ?
        """,
        (device_name,),
    ).fetchone()


def is_device_allowed(connection, device_name: str) -> bool:
    row = get_allowed_device_row(connection, device_name)
    return bool(row and row["is_enabled"] == 1)


@router.get("/allowed-devices", response_model=list[AllowedDeviceInfo])
def list_allowed_devices() -> list[AllowedDeviceInfo]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT device_name, description, is_enabled, created_at, updated_at
            FROM allowed_devices
            ORDER BY device_name ASC
            """
        ).fetchall()

    return [
        AllowedDeviceInfo(
            device_name=row["device_name"],
            description=row["description"],
            is_enabled=bool(row["is_enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.post("/allowed-devices", response_model=AllowedDeviceInfo, status_code=status.HTTP_201_CREATED)
def create_allowed_device(payload: AllowedDeviceCreate) -> AllowedDeviceInfo:
    now = utc_now()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO allowed_devices (device_name, description, is_enabled, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(device_name) DO UPDATE SET
                description = excluded.description,
                is_enabled = 1,
                updated_at = excluded.updated_at
            """,
            (payload.device_name, payload.description, now, now),
        )
        log_activity(
            connection,
            direction="user_to_server",
            endpoint="/allowed-devices",
            event_type="allowed_device_saved",
            status="ok",
            device_name=payload.device_name,
            request_summary=make_summary(device_name=payload.device_name, description=payload.description),
            response_summary="is_enabled=1",
        )
        row = get_allowed_device_row(connection, payload.device_name)
        connection.commit()

    return AllowedDeviceInfo(
        device_name=row["device_name"],
        description=row["description"],
        is_enabled=bool(row["is_enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def set_allowed_device_enabled(payload: AllowedDeviceToggleRequest, enabled: bool) -> AllowedDeviceInfo:
    now = utc_now()

    with get_connection() as connection:
        row = get_allowed_device_row(connection, payload.device_name)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed device not found")

        connection.execute(
            "UPDATE allowed_devices SET is_enabled = ?, updated_at = ? WHERE device_name = ?",
            (1 if enabled else 0, now, payload.device_name),
        )
        log_activity(
            connection,
            direction="user_to_server",
            endpoint=f"/allowed-devices/{'enable' if enabled else 'disable'}",
            event_type="allowed_device_enabled" if enabled else "allowed_device_disabled",
            status="ok",
            device_name=payload.device_name,
            request_summary=make_summary(device_name=payload.device_name),
            response_summary=make_summary(is_enabled=1 if enabled else 0),
        )
        row = get_allowed_device_row(connection, payload.device_name)
        connection.commit()

    return AllowedDeviceInfo(
        device_name=row["device_name"],
        description=row["description"],
        is_enabled=bool(row["is_enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/allowed-devices/enable", response_model=AllowedDeviceInfo)
def enable_allowed_device(payload: AllowedDeviceToggleRequest) -> AllowedDeviceInfo:
    return set_allowed_device_enabled(payload, True)


@router.post("/allowed-devices/disable", response_model=AllowedDeviceInfo)
def disable_allowed_device(payload: AllowedDeviceToggleRequest) -> AllowedDeviceInfo:
    return set_allowed_device_enabled(payload, False)
