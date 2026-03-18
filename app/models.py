from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


JobStatus = Literal["pending", "running", "done", "error"]


class DevicePoll(BaseModel):
    device_id: str
    firmware: str
    status: str


class JobResponse(BaseModel):
    job_type: str = Field(
        validation_alias=AliasChoices("job", "job_type"),
        serialization_alias="job",
    )
    file_name: str | None = None


class UploadResponse(BaseModel):
    status: str
    file_name: str


class CreateJobRequest(BaseModel):
    device_id: str
    file_name: str


class JobDoneRequest(BaseModel):
    device_id: str
    file_name: str
    status: Literal["done", "error"]


class DeviceInfo(BaseModel):
    device_id: str
    last_seen: str
    status: str


class JobCreateResponse(BaseModel):
    status: str
    job_id: int
    device_id: str
    file_name: str


class JobDoneResponse(BaseModel):
    status: str
    device_id: str
    file_name: str
