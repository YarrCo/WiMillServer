from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


ConnectionStatus = Literal["online", "offline"]
UsbStatus = Literal["attached", "detached", "switching", "unknown"]
BusyStatus = Literal["idle", "busy", "error", "unknown"]
JobStatus = Literal["pending", "running", "done", "error", "queued"]
JobType = Literal["download_file", "upload_file", "attach", "detach"]
JobSource = Literal["user", "server", "device"]
ActionStatus = Literal["done", "error"]


class WiMillBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AllowedDeviceCreate(WiMillBaseModel):
    device_name: str
    description: str | None = None


class AllowedDeviceToggleRequest(WiMillBaseModel):
    device_name: str


class AllowedDeviceInfo(WiMillBaseModel):
    device_name: str
    description: str | None = None
    is_enabled: bool
    created_at: str
    updated_at: str


class DeviceHelloRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    firmware_version: str = Field(validation_alias=AliasChoices("firmware_version", "firmware"))
    ip_address: str | None = None


class DeviceHelloResponse(WiMillBaseModel):
    status: str
    authorized: bool
    reason: str | None = None


class DevicePollRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    firmware_version: str = Field(validation_alias=AliasChoices("firmware_version", "firmware"))
    connection_status: ConnectionStatus = "online"
    usb_status: UsbStatus = "unknown"
    busy_status: BusyStatus = "unknown"
    free_space: int | None = None
    total_space: int | None = None
    ip_address: str | None = None


class DevicePollResponse(WiMillBaseModel):
    job_type: str = Field(serialization_alias="job")
    file_name: str | None = None
    status: str | None = None
    authorized: bool | None = None
    reason: str | None = None
    note: str | None = None


class DeviceFileItem(WiMillBaseModel):
    file_name: str
    file_size: int | None = None
    modified_at: str | None = None


class DeviceFilesRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    files: list[DeviceFileItem]


class DeviceFilesResponse(WiMillBaseModel):
    status: str
    files_received: int


class DeviceActionResultRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    action: JobType
    status: ActionStatus
    message: str | None = None


class DeviceActionResultResponse(WiMillBaseModel):
    status: str
    action: JobType
    device_name: str
    message: str | None = None


class UploadResponse(WiMillBaseModel):
    status: str
    file_name: str


class CreateJobRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    file_name: str | None = None
    job_type: JobType = "download_file"
    source: JobSource = "user"
    note: str | None = None


class JobCreateResponse(WiMillBaseModel):
    status: str
    job_id: int
    device_name: str
    job_type: JobType
    file_name: str | None = None
    job_status: JobStatus
    source: JobSource
    note: str | None = None


class JobDoneRequest(WiMillBaseModel):
    device_name: str = Field(validation_alias=AliasChoices("device_name", "device_id"))
    file_name: str | None = None
    status: Literal["done", "error"]
    message: str | None = Field(default=None, validation_alias=AliasChoices("message", "error_message"))


class JobDoneResponse(WiMillBaseModel):
    status: str
    device_name: str
    file_name: str | None = None


class JobInfo(WiMillBaseModel):
    id: int
    device_name: str | None = None
    job_type: JobType
    file_name: str | None = None
    status: JobStatus
    progress: int
    created_at: str
    updated_at: str | None = None
    error_message: str | None = None
    source: JobSource
    note: str | None = None


class DeviceInfo(WiMillBaseModel):
    device_name: str
    is_online: bool
    last_seen: str | None = None
    connection_status: ConnectionStatus = "offline"
    usb_status: UsbStatus = "unknown"
    busy_status: BusyStatus = "unknown"
    free_space: int | None = None
    total_space: int | None = None
    ip_address: str | None = None
    firmware_version: str | None = None


class ActivityLogEntry(WiMillBaseModel):
    timestamp: str
    direction: str
    device_name: str | None = None
    endpoint: str
    event_type: str
    status: str
    request_summary: str | None = None
    response_summary: str | None = None
    details: str | None = None


class ServerFileInfo(WiMillBaseModel):
    file_name: str
    file_size: int
    modified_at: str


class DeviceFileInfo(WiMillBaseModel):
    device_name: str
    file_name: str
    file_size: int | None = None
    modified_at: str | None = None
    synced_at: str
