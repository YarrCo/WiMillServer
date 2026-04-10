# WiMill Server MVP

WiMill Server MVP — это локальный сервер на `FastAPI` и `SQLite` для управления устройствами WiMill, файлами, заданиями и журналом активности.

Сервер решает две задачи:
- backend для обмена между устройством и сервером
- простой встроенный web UI без React/Vue, чтобы можно было управлять системой из браузера

## Что умеет сервер

Backend:
- хранит white list разрешённых устройств
- принимает только разрешённые устройства
- принимает `hello`, `poll`, `files`, `action-result` от устройства
- хранит текущее состояние устройства
- хранит очередь jobs и историю их выполнения
- хранит список файлов на сервере и список файлов, которые сообщил device
- ведёт `activity_log`
- отдаёт API для UI и для ручной проверки через `/docs`

Web UI:
- показывает dashboard по устройствам, jobs и последней активности
- показывает список устройств и позволяет создать `attach`, `detach`, `refresh_files`
- показывает очередь jobs с фильтрами
- позволяет загружать файл на сервер, скачивать, удалять и отправлять на устройство
- показывает последние события activity log
- делает автообновление страниц каждые 5 секунд через обычный JS polling
- пишет действия UI и ответы сервера в блок `Live Log`

## Стек

- `Python 3.12`
- `FastAPI`
- `Uvicorn`
- `SQLite`
- `Pydantic`
- `Jinja2`
- `python-multipart`

## Структура проекта

```text
WiMillServer/
├─ app/
│  ├─ main.py
│  ├─ database.py
│  ├─ models.py
│  ├─ devices.py
│  ├─ jobs.py
│  ├─ activity.py
│  ├─ allowed_devices.py
│  ├─ files.py
│  └─ ui.py
├─ templates/
│  ├─ base.html
│  ├─ dashboard.html
│  ├─ devices.html
│  ├─ jobs.html
│  ├─ files_server.html
│  ├─ files_device.html
│  └─ activity.html
├─ static/
│  ├─ style.css
│  └─ app.js
├─ storage/
│  ├─ uploads/
│  └─ devices/
├─ requirements.txt
├─ README.md
└─ wimill.db
```

Назначение файлов:
- `app/main.py` — создание приложения, подключение API-роутов, UI-роутов и static files
- `app/database.py` — работа с SQLite, создание таблиц, storage-папок и мягкая миграция
- `app/models.py` — Pydantic-модели запросов и ответов
- `app/devices.py` — `device/hello`, `device/poll`, `device/files`, `device/action-result`, `GET /devices`
- `app/jobs.py` — создание jobs, загрузка файлов в backend, завершение jobs, `GET /jobs`
- `app/activity.py` — activity log и `GET /activity`
- `app/allowed_devices.py` — управление white list устройств
- `app/files.py` — файлы на сервере и файлы устройства
- `app/ui.py` — HTML-страницы и формы web UI
- `templates/` — Jinja2-шаблоны интерфейса
- `static/` — CSS и JS для интерфейса

## Установка зависимостей

```bash
pip install -r requirements.txt
```

Что делает команда:
- `pip` — менеджер пакетов Python
- `install` — установить зависимости
- `-r requirements.txt` — взять список пакетов из файла `requirements.txt`

## Запуск сервера

Локальный запуск:

```bash
uvicorn app.main:app --reload
```

Что означает команда:
- `uvicorn` — сервер, который запускает FastAPI-приложение
- `app.main:app` — взять объект `app` из файла `app/main.py`
- `--reload` — перезапускать сервер при изменении кода

После запуска доступны:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Web UI: `http://127.0.0.1:8000/`

### Запуск для локальной сети

Если сервер должен открываться с другого ПК в LAN:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

После этого UI и API будут доступны, например, по адресу:
- `http://192.168.1.48:8000/`
- `http://192.168.1.48:8000/docs`

## White list логика

Сервер не регистрирует устройство автоматически.

Порядок такой:
1. Пользователь добавляет устройство в `allowed_devices`
2. Устройство вызывает `POST /device/hello`
3. Сервер проверяет, есть ли `device_name` в white list и включено ли устройство
4. Если устройство разрешено, сервер обновляет `device_state`
5. Если устройства нет в white list, сервер возвращает отказ и пишет событие в `activity_log`

## База данных

По умолчанию используется файл:
- `wimill.db`

Основные таблицы:

### `allowed_devices`
Список разрешённых устройств:
- `id`
- `device_name`
- `description`
- `is_enabled`
- `created_at`
- `updated_at`

### `device_state`
Текущее состояние устройства:
- `device_name`
- `firmware_version`
- `last_seen`
- `is_online`
- `connection_status`
- `usb_status`
- `busy_status`
- `free_space`
- `total_space`
- `ip_address`
- `last_error`
- `updated_at`

### `device_files`
Последний список файлов, который прислал device:
- `device_name`
- `file_name`
- `file_size`
- `modified_at`
- `synced_at`

### `jobs`
Очередь заданий:
- `id`
- `device_name`
- `job_type`
- `file_name`
- `status`
- `progress`
- `created_at`
- `updated_at`
- `error_message`
- `source`
- `note`

Возможные `job_type`:
- `download_file`
- `upload_file`
- `attach`
- `detach`
- `refresh_files`

Возможные `status`:
- `pending`
- `queued`
- `running`
- `done`
- `error`

### `activity_log`
Живой журнал активности:
- `timestamp`
- `direction`
- `device_name`
- `endpoint`
- `event_type`
- `request_summary`
- `response_summary`
- `status`
- `details`

## Activity log

`activity_log` нужен для анализа того, что реально происходит между устройством, сервером и пользователем.

Туда пишутся:
- входящие запросы от устройств
- ответы сервера устройствам
- действия пользователя через API и web UI
- создание jobs
- отправка jobs устройству
- загрузка и удаление файлов
- отказы неразрешённым устройствам
- внутренние события backend

Получить лог можно через API:

```bash
curl "http://127.0.0.1:8000/activity?limit=20"
```

Или через web UI:
- `http://127.0.0.1:8000/ui/activity`

## API endpoints

## Allowed devices

### `GET /allowed-devices`
Возвращает список разрешённых устройств.

### `POST /allowed-devices`
Добавляет устройство в white list.

Пример:

```json
{
  "device_name": "mill-01",
  "description": "RichAuto test stand"
}
```

### `POST /allowed-devices/enable`
Включает устройство.

### `POST /allowed-devices/disable`
Выключает устройство.

## Devices API

### `POST /device/hello`
Первый запрос устройства после старта.

Пример:

```json
{
  "device_name": "mill-01",
  "firmware_version": "0.2",
  "ip_address": "192.168.1.77"
}
```

Успешный ответ:

```json
{
  "status": "ok",
  "authorized": true
}
```

Ответ для неразрешённого устройства:

```json
{
  "status": "rejected",
  "authorized": false,
  "reason": "device_not_allowed"
}
```

### `POST /device/poll`
Устройство сообщает состояние и получает job.

Пример:

```json
{
  "device_name": "mill-01",
  "firmware_version": "0.2",
  "connection_status": "online",
  "usb_status": "attached",
  "busy_status": "idle",
  "free_space": 1200000000,
  "total_space": 32000000000,
  "ip_address": "192.168.1.77"
}
```

Ответ без job:

```json
{
  "job": "none"
}
```

Ответ с job:

```json
{
  "job": "download_file",
  "file_name": "test.nc"
}
```

### `POST /device/files`
Устройство отправляет актуальный список файлов.

### `POST /device/action-result`
Устройство отправляет результат действия, например `attach`, `detach`, `download_file`.

### `GET /devices`
Возвращает расширенное состояние устройств.

Поля ответа:
- `device_name`
- `is_online`
- `last_seen`
- `connection_status`
- `usb_status`
- `busy_status`
- `free_space`
- `total_space`
- `ip_address`
- `firmware_version`

## Files API

### `POST /upload`
Базовый API-загрузчик файла в `storage/uploads`.

Сейчас он принимает raw body и имя файла в query string:

```bash
curl -X POST "http://127.0.0.1:8000/upload?file_name=test.nc" ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "@test.nc"
```

### `GET /files/server`
Список файлов на сервере.

### `GET /files/server/download/{file_name}`
Скачать файл с сервера.

### `POST /files/server/delete/{file_name}`
Удалить файл на сервере.

### `GET /files/device/{device_name}`
Список файлов, который сообщил конкретный device.

## Jobs API

### `GET /jobs`
Возвращает список jobs для просмотра очереди через API.

Поддерживаются query-параметры:
- `device_name`
- `status`
- `limit`

Возвращаемые поля:
- `id`
- `device_name`
- `job_type`
- `file_name`
- `status`
- `progress`
- `created_at`
- `updated_at`
- `error_message`
- `source`
- `note`

Примеры:

```bash
curl "http://127.0.0.1:8000/jobs"
```

```bash
curl "http://127.0.0.1:8000/jobs?device_name=mill-01&status=pending&limit=20"
```

### `POST /jobs`
Создаёт job для устройства.

Пример download job:

```json
{
  "device_name": "mill-01",
  "file_name": "test.nc",
  "job_type": "download_file",
  "source": "user"
}
```

Пример attach job:

```json
{
  "device_name": "mill-01",
  "job_type": "attach",
  "source": "user",
  "note": "manual usb attach"
}
```

### `POST /jobs/done`
Совместимый endpoint для завершения job по устройству и файлу.

## Web UI

UI встроен прямо в FastAPI-приложение и использует существующие API, а не дублирует backend-логику.

Страницы:
- `/` — dashboard
- `/ui/devices` — список устройств и действия `Attach`, `Detach`, `Refresh Files`
- `/ui/jobs` — очередь jobs, фильтры и форма создания `download_file`
- `/ui/files/server` — upload, download, delete и `Send to Device`
- `/ui/files/device/{device_name}` — список файлов устройства
- `/ui/activity` — последние события activity log

Что делает UI:
- периодически запрашивает `/devices`, `/jobs`, `/activity`
- обновляет таблицы без тяжёлого frontend-фреймворка
- пишет все UI-действия и ответы от polling в блок `Live Log`

## Ручная проверка через Web UI

1. Запустите сервер и откройте `http://127.0.0.1:8000/`
2. Перейдите в `Devices`
3. Добавьте устройство, например `mill-01`
4. Отправьте `POST /device/hello` через `/docs` или с реального устройства
5. Вернитесь в UI и убедитесь, что устройство появилось как online
6. Перейдите в `Server Files` и загрузите файл
7. Нажмите `Send to Device`, выберите `mill-01`
8. Перейдите в `Jobs` и убедитесь, что появился `download_file`
9. С устройства вызовите `POST /device/poll` и убедитесь, что job выдана
10. С устройства вызовите `POST /device/action-result`
11. Проверьте `Activity` и `Live Log`

## Ручная проверка через `/docs`

Рекомендуемый порядок:
1. `POST /allowed-devices`
2. `POST /device/hello`
3. `POST /device/poll`
4. `POST /upload`
5. `POST /jobs`
6. ещё раз `POST /device/poll`
7. `POST /device/action-result`
8. `POST /device/files`
9. `GET /devices`
10. `GET /jobs`
11. `GET /files/server`
12. `GET /files/device/mill-01`
13. `GET /activity`
14. `POST /device/hello` с неизвестным устройством, чтобы проверить отказ

## Что проверено локально после доработки

Локально на временной базе и временном storage были проверены:
- открытие `GET /`
- открытие `GET /ui/devices`
- добавление устройства через `POST /ui/devices/add`
- `POST /device/hello`
- `POST /device/poll`
- загрузка файла через `POST /ui/files/server/upload`
- создание download job через UI
- создание attach job через UI
- `GET /jobs` и фильтрация по `device_name`
- `POST /device/files`
- открытие `GET /ui/files/device/{device_name}`
- открытие `GET /ui/activity`

## Важные замечания

- устройство должно быть добавлено в white list до `hello` и `poll`
- сервер не управляет железом напрямую, а только ставит задания в очередь
- если устройство занято, jobs не пропадают, а остаются в `pending` или `queued`
- `activity_log` хранит короткие summaries, а не большой бинарный контент
- для доступа из локальной сети запускайте сервер с `--host 0.0.0.0`

## Последние изменения

- для каждого устройства в UI добавлена кнопка `Files`, чтобы открыть последний список файлов без ручного `Refresh`
- `attach` и `detach` теперь имеют приоритет в очереди выше `download_file`, `upload_file`, `refresh_files`
- если устройство ещё в статусе `attached`, SD-задачи не теряются, а ждут своей очереди до появления `usb_status = detached`
- если устройство после включения само присылает последний известный список файлов, страницу `/ui/files/device/{device_name}` можно открывать сразу после подключения устройства

