# WiMill Server MVP

Minimal local server for the WiMill MVP built with FastAPI, Uvicorn and SQLite.

## Stack

- Python 3.12
- FastAPI
- Uvicorn
- SQLite

## Project structure

```text
WiMillServer/
?? app/
?  ?? main.py
?  ?? database.py
?  ?? models.py
?  ?? devices.py
?  ?? jobs.py
?? storage/
?  ?? uploads/
?  ?? devices/
?? requirements.txt
?? wimill.db
```

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Open:

- API docs: http://127.0.0.1:8000/docs

At startup the server creates:

- `wimill.db`
- `storage/uploads/`
- `storage/devices/`

## API

### 1. Device poll

`POST /device/poll`

Request:

```json
{
  "device_id": "mill01",
  "firmware": "0.1",
  "status": "idle"
}
```

Response without job:

```json
{
  "job": "none",
  "file_name": null
}
```

Response with job:

```json
{
  "job": "download",
  "file_name": "test.nc"
}
```

Example:

```bash
curl -X POST "http://127.0.0.1:8000/device/poll" ^
  -H "Content-Type: application/json" ^
  -d "{\"device_id\":\"mill01\",\"firmware\":\"0.1\",\"status\":\"idle\"}"
```

### 2. Upload file

`POST /upload`

The current MVP accepts the file as raw request body. File name is passed in the query string.

Example:

```bash
curl -X POST "http://127.0.0.1:8000/upload?file_name=test.nc" ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "@test.nc"
```

Response:

```json
{
  "status": "ok",
  "file_name": "test.nc"
}
```

### 3. Create job

`POST /jobs`

Request:

```json
{
  "device_id": "mill01",
  "file_name": "test.nc"
}
```

Example:

```bash
curl -X POST "http://127.0.0.1:8000/jobs" ^
  -H "Content-Type: application/json" ^
  -d "{\"device_id\":\"mill01\",\"file_name\":\"test.nc\"}"
```

Response:

```json
{
  "status": "ok",
  "job_id": 1,
  "device_id": "mill01",
  "file_name": "test.nc"
}
```

### 4. Job done

`POST /jobs/done`

Request:

```json
{
  "device_id": "mill01",
  "file_name": "test.nc",
  "status": "done"
}
```

Example:

```bash
curl -X POST "http://127.0.0.1:8000/jobs/done" ^
  -H "Content-Type: application/json" ^
  -d "{\"device_id\":\"mill01\",\"file_name\":\"test.nc\",\"status\":\"done\"}"
```

Response:

```json
{
  "status": "done",
  "device_id": "mill01",
  "file_name": "test.nc"
}
```

### 5. Devices list

`GET /devices`

Example:

```bash
curl "http://127.0.0.1:8000/devices"
```

Response:

```json
[
  {
    "device_id": "mill01",
    "last_seen": "2026-03-11T22:16:23.546930+00:00",
    "status": "idle"
  }
]
```

## Job statuses

- `pending`
- `running`
- `done`
- `error`

## Notes

- Device registration happens automatically on the first `POST /device/poll`.
- When a device polls and has a pending job, the job is returned and marked as `running`.
- `POST /jobs/done` updates the latest matching job for the device and file.
