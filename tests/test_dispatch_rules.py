from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from app.allowed_devices import create_allowed_device
from app.database import init_db
from app.devices import mark_upload_job_completed, try_dispatch_job, update_job_from_action
from app.jobs import create_job
from app.models import AllowedDeviceCreate, CreateJobRequest, DevicePollRequest
import app.database as database


class DispatchRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="wimill-dispatch-test-"))
        database.DB_PATH = self.temp_dir / "test.db"
        database.STORAGE_DIR = self.temp_dir / "storage"
        database.UPLOADS_DIR = database.STORAGE_DIR / "uploads"
        database.DEVICES_DIR = database.STORAGE_DIR / "devices"
        init_db()
        create_allowed_device(AllowedDeviceCreate(device_name="mill-01", description="test"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def poll_payload(self, usb_status: str) -> DevicePollRequest:
        return DevicePollRequest(
            device_name="mill-01",
            firmware_version="0.2",
            connection_status="online",
            usb_status=usb_status,
            busy_status="idle",
            ip_address="192.168.1.10",
        )

    def test_sd_access_job_is_not_dispatched_while_usb_attached(self) -> None:
        create_job(
            CreateJobRequest(
                device_name="mill-01",
                job_type="download_file",
                file_name="test.nc",
                source="user",
            )
        )

        with database.get_connection() as connection:
            job = try_dispatch_job(connection, self.poll_payload("attached"))
            row = connection.execute(
                "SELECT status FROM jobs WHERE device_name = ? ORDER BY id ASC LIMIT 1",
                ("mill-01",),
            ).fetchone()

        self.assertIsNone(job)
        self.assertEqual(row["status"], "pending")

    def test_sd_access_job_is_dispatched_when_usb_detached(self) -> None:
        create_job(
            CreateJobRequest(
                device_name="mill-01",
                job_type="refresh_files",
                source="user",
            )
        )

        with database.get_connection() as connection:
            job = try_dispatch_job(connection, self.poll_payload("detached"))
            row = connection.execute(
                "SELECT status FROM jobs WHERE device_name = ? ORDER BY id ASC LIMIT 1",
                ("mill-01",),
            ).fetchone()

        self.assertIsNotNone(job)
        self.assertEqual(job["job_type"], "refresh_files")
        self.assertEqual(row["status"], "running")

    def test_attach_job_dispatches_even_when_usb_attached(self) -> None:
        create_job(
            CreateJobRequest(
                device_name="mill-01",
                job_type="attach",
                source="user",
            )
        )

        with database.get_connection() as connection:
            job = try_dispatch_job(connection, self.poll_payload("attached"))
            row = connection.execute(
                "SELECT status FROM jobs WHERE device_name = ? ORDER BY id ASC LIMIT 1",
                ("mill-01",),
            ).fetchone()

        self.assertIsNotNone(job)
        self.assertEqual(job["job_type"], "attach")
        self.assertEqual(row["status"], "running")

    def test_running_action_updates_job_progress(self) -> None:
        create_job(
            CreateJobRequest(
                device_name="mill-01",
                job_type="upload_file",
                file_name="logs/run.gcode",
                source="user",
            )
        )

        with database.get_connection() as connection:
            dispatched = try_dispatch_job(connection, self.poll_payload("detached"))
            self.assertIsNotNone(dispatched)
            update_job_from_action(connection, "mill-01", "upload_file", "running", "copying", 55)
            row = connection.execute(
                "SELECT status, progress FROM jobs WHERE device_name = ? ORDER BY id ASC LIMIT 1",
                ("mill-01",),
            ).fetchone()

        self.assertEqual(row["status"], "running")
        self.assertEqual(row["progress"], 55)

    def test_mark_upload_job_completed_sets_done_and_100_percent(self) -> None:
        create_job(
            CreateJobRequest(
                device_name="mill-01",
                job_type="upload_file",
                file_name="logs/run.gcode",
                source="user",
            )
        )

        with database.get_connection() as connection:
            dispatched = try_dispatch_job(connection, self.poll_payload("detached"))
            self.assertIsNotNone(dispatched)
            mark_upload_job_completed(connection, "mill-01", "logs/run.gcode")
            row = connection.execute(
                "SELECT status, progress FROM jobs WHERE device_name = ? ORDER BY id ASC LIMIT 1",
                ("mill-01",),
            ).fetchone()

        self.assertEqual(row["status"], "done")
        self.assertEqual(row["progress"], 100)


if __name__ == "__main__":
    unittest.main()
