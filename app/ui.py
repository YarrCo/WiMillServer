from __future__ import annotations

from collections import Counter
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.activity import list_activity
from app.allowed_devices import create_allowed_device
from app.database import BASE_DIR
from app.devices import list_devices
from app.files import delete_server_file, list_device_files, list_server_files
from app.jobs import clear_finished_jobs, create_job, finish_job, list_jobs, save_upload_content
from app.models import AllowedDeviceCreate, CreateJobRequest


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def redirect_with_message(url: str, message: str, level: str = "success") -> RedirectResponse:
    separator = "&" if "?" in url else "?"
    target = f"{url}{separator}{urlencode({'message': message, 'level': level})}"
    return RedirectResponse(url=target, status_code=303)


def page_context(request: Request, title: str, page_name: str, **kwargs):
    context = {
        "request": request,
        "title": title,
        "page_name": page_name,
        "message": request.query_params.get("message"),
        "message_level": request.query_params.get("level", "info"),
        "ui_config": {"page": page_name},
    }
    context.update(kwargs)
    return context


@router.get("/")
def dashboard_page(request: Request):
    devices = list_devices()
    jobs = list_jobs(device_name=None, status_value=None, limit=500)
    recent_activity = list_activity(limit=10)

    job_counts = Counter(job.status for job in jobs)
    stats = {
        "devices_total": len(devices),
        "devices_online": sum(1 for device in devices if device.is_online),
        "devices_offline": sum(1 for device in devices if not device.is_online),
        "jobs_pending": job_counts.get("pending", 0) + job_counts.get("queued", 0),
        "jobs_running": job_counts.get("running", 0),
        "jobs_done": job_counts.get("done", 0),
        "jobs_error": job_counts.get("error", 0),
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(request, "Dashboard", "dashboard", stats=stats, recent_activity=recent_activity),
    )


@router.get("/ui/devices")
def devices_page(request: Request):
    devices = list_devices()
    return templates.TemplateResponse(
        request,
        "devices.html",
        page_context(request, "Devices", "devices", devices=devices),
    )


@router.post("/ui/devices/add")
def add_device_ui(device_name: str = Form(...), description: str = Form(default="")):
    create_allowed_device(AllowedDeviceCreate(device_name=device_name.strip(), description=description.strip() or None))
    return redirect_with_message("/ui/devices", f"Device {device_name} added")


@router.post("/ui/device/{device_name}/attach")
def attach_device_ui(device_name: str):
    create_job(CreateJobRequest(device_name=device_name, job_type="attach", source="user", note="ui attach request"))
    return redirect_with_message("/ui/devices", f"Attach job created for {device_name}")


@router.post("/ui/device/{device_name}/detach")
def detach_device_ui(device_name: str):
    create_job(CreateJobRequest(device_name=device_name, job_type="detach", source="user", note="ui detach request"))
    return redirect_with_message("/ui/devices", f"Detach job created for {device_name}")


@router.post("/ui/device/{device_name}/refresh")
def refresh_device_files_ui(device_name: str):
    create_job(
        CreateJobRequest(
            device_name=device_name,
            job_type="refresh_files",
            source="user",
            note="ui refresh device files",
        )
    )
    return redirect_with_message(f"/ui/files/device/{device_name}", f"Refresh files job created for {device_name}")


@router.get("/ui/jobs")
def jobs_page(request: Request, device_name: str | None = None, status: str | None = None):
    jobs = list_jobs(device_name=device_name, status_value=status, limit=200)
    devices = list_devices()
    server_files = list_server_files()
    ui_config = {"page": "jobs", "device_name": device_name or "", "status": status or ""}
    return templates.TemplateResponse(
        request,
        "jobs.html",
        page_context(
            request,
            "Jobs",
            "jobs",
            jobs=jobs,
            devices=devices,
            server_files=server_files,
            selected_device=device_name or "",
            selected_status=status or "",
            ui_config=ui_config,
        ),
    )


@router.post("/ui/jobs/create-download")
def create_download_job_ui(device_name: str = Form(...), file_name: str = Form(...)):
    create_job(
        CreateJobRequest(
            device_name=device_name,
            file_name=file_name,
            job_type="download_file",
            source="user",
            note="ui send server file",
        )
    )
    return redirect_with_message("/ui/jobs", f"Download job created for {device_name}")


@router.post("/ui/jobs/{job_id}/finish")
def finish_job_ui(job_id: int):
    job = finish_job(job_id, endpoint="/ui/jobs/finish", message="finished from ui")
    return redirect_with_message("/ui/jobs", f"Job {job['id']} marked done", level="warning")


@router.post("/ui/jobs/clear-finished")
def clear_finished_jobs_ui():
    deleted = clear_finished_jobs(endpoint="/ui/jobs/clear-finished")
    return redirect_with_message("/ui/jobs", f"Cleared {deleted} finished jobs", level="warning")


@router.get("/ui/files/server")
def server_files_page(request: Request):
    server_files = list_server_files()
    devices = list_devices()
    return templates.TemplateResponse(
        request,
        "files_server.html",
        page_context(request, "Server Files", "files_server", server_files=server_files, devices=devices),
    )


@router.post("/ui/files/server/upload")
async def upload_server_file_ui(file: UploadFile = File(...)):
    content = await file.read()
    save_upload_content(file_name=file.filename or "", content=content, endpoint="/ui/files/server/upload")
    return redirect_with_message("/ui/files/server", f"File {file.filename} uploaded")


@router.post("/ui/files/server/delete/{file_name}")
def delete_server_file_ui(file_name: str):
    deleted_name = delete_server_file(file_name, endpoint="/ui/files/server/delete")
    return redirect_with_message("/ui/files/server", f"File {deleted_name} deleted", level="warning")


@router.post("/ui/files/server/send")
def send_server_file_to_device_ui(device_name: str = Form(...), file_name: str = Form(...)):
    create_job(
        CreateJobRequest(
            device_name=device_name,
            file_name=file_name,
            job_type="download_file",
            source="user",
            note="ui send to device",
        )
    )
    return redirect_with_message("/ui/files/server", f"Send-to-device job created for {device_name}")


@router.get("/ui/files/device/{device_name}")
def device_files_page(request: Request, device_name: str):
    device_files = list_device_files(device_name)
    devices = list_devices()
    current_device = next((item for item in devices if item.device_name == device_name), None)
    return templates.TemplateResponse(
        request,
        "files_device.html",
        page_context(
            request,
            f"Device Files: {device_name}",
            "files_device",
            device=current_device,
            device_name=device_name,
            device_files=device_files,
        ),
    )


@router.get("/ui/activity")
def activity_page(request: Request):
    activity = list_activity(limit=100)
    return templates.TemplateResponse(
        request,
        "activity.html",
        page_context(request, "Activity", "activity", activity=activity, ui_config={"page": "activity"}),
    )
