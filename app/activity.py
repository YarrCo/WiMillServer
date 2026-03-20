from __future__ import annotations

from fastapi import APIRouter, Query

from app.database import get_connection, utc_now
from app.models import ActivityLogEntry


router = APIRouter()


def make_summary(**values: object) -> str:
    parts: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def log_activity(
    connection,
    *,
    direction: str,
    endpoint: str,
    event_type: str,
    status: str,
    device_name: str | None = None,
    request_summary: str | None = None,
    response_summary: str | None = None,
    details: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO activity_log (
            timestamp,
            direction,
            device_name,
            endpoint,
            event_type,
            request_summary,
            response_summary,
            status,
            details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now(),
            direction,
            device_name,
            endpoint,
            event_type,
            request_summary,
            response_summary,
            status,
            details,
        ),
    )


@router.get("/activity", response_model=list[ActivityLogEntry])
def list_activity(limit: int = Query(default=100, ge=1, le=500)) -> list[ActivityLogEntry]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT timestamp, direction, device_name, endpoint, event_type, status,
                   request_summary, response_summary, details
            FROM activity_log
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        ActivityLogEntry(
            timestamp=row["timestamp"],
            direction=row["direction"],
            device_name=row["device_name"],
            endpoint=row["endpoint"],
            event_type=row["event_type"],
            status=row["status"],
            request_summary=row["request_summary"],
            response_summary=row["response_summary"],
            details=row["details"],
        )
        for row in rows
    ]
