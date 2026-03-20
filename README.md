# WiMill Server MVP

Это backend для MVP-сервера WiMill на `FastAPI` и `SQLite`.

Сервер принимает запросы от устройств и пользователя, хранит состояние устройств, очередь заданий, список файлов на устройстве и журнал активности. Основная идея текущей версии: устройство не регистрируется автоматически, а сначала должно быть добавлено в white list разрешенных устройств.

## Что умеет сервер

Сервер умеет:

- хранить список разрешенных устройств
- принимать только разрешенные устройства
- принимать `hello` и `poll` от устройства
- хранить текущее состояние устройства
- хранить список файлов, который устройство сообщает серверу
- принимать загрузку файлов на сервер
- создавать задания для устройства
- держать очередь заданий `pending/running/queued/done/error`
- принимать результаты действий устройства
- вести activity log для анализа запросов и ответов
- отдавать activity log через API

## Стек

- `Python 3.12`
- `FastAPI`
- `Uvicorn`
- `SQLite`
- `Pydantic`

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
│  └─ files.py
├─ storage/
│  ├─ uploads/
│  └─ devices/
├─ requirements.txt
├─ README.md
└─ wimill.db
```

Назначение файлов:

- `app/main.py` - создание FastAPI-приложения и подключение роутов.
- `app/database.py` - инициализация SQLite, создание таблиц и мягкая миграция старой схемы.
- `app/models.py` - Pydantic-модели запросов и ответов.
- `app/devices.py` - `hello`, `poll`, загрузка списка файлов устройством, `action-result`, расширенный список устройств.
- `app/jobs.py` - загрузка файлов на сервер, создание jobs, завершение jobs.
- `app/activity.py` - helper для activity log и endpoint `/activity`.
- `app/allowed_devices.py` - white list устройств.
- `app/files.py` - список файлов на сервере и файлов, которые сообщил device.

## Установка зависимостей

```bash
pip install -r requirements.txt
```

Что делает команда:

- `pip` - менеджер пакетов Python
- `install` - установить зависимости
- `-r requirements.txt` - взять список пакетов из файла `requirements.txt`

## Запуск сервера

Локальный запуск:

```bash
uvicorn app.main:app --reload
```

Что это значит:

- `uvicorn` - ASGI-сервер для запуска FastAPI
- `app.main:app` - взять объект `app` из файла `app/main.py`
- `--reload` - перезапускать сервер при изменении кода

После запуска документация доступна по адресу:

- `http://127.0.0.1:8000/docs`

### Запуск для локальной сети

Если нужен доступ с другого устройства в LAN:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Что добавляется:

- `--host 0.0.0.0` - слушать все сетевые интерфейсы, а не только `localhost`
- `--port 8000` - использовать порт `8000`

Пример адреса в локальной сети:

- `http://192.168.1.48:8000/docs`

## White list логика

Главная идея этой версии backend: устройство не может начать работу только потому, что знает IP сервера.

Порядок такой:

1. Пользователь вручную добавляет устройство в `allowed_devices`.
2. Устройство отправляет `POST /device/hello`.
3. Сервер проверяет, есть ли `device_name` в white list и включено ли устройство.
4. Если устройство разрешено, сервер обновляет `device_state` и разрешает дальнейшую работу.
5. Если устройство не разрешено, сервер возвращает отказ и записывает событие в `activity_log`.

## База данных

Сервер использует SQLite. Файл базы по умолчанию:

- `wimill.db`

При старте сервер автоматически создает таблицы и при необходимости добавляет новые поля в существующую таблицу `jobs`.

### Таблица `allowed_devices`

Список разрешенных устройств:

- `id`
- `device_name` - уникальное имя устройства
- `description` - описание
- `is_enabled` - устройство включено или выключено
- `created_at`
- `updated_at`

### Таблица `device_state`

Текущее состояние устройства:

- `id`
- `device_name`
- `firmware_version`
- `last_seen`
- `is_online`
- `connection_status` - `online` или `offline`
- `usb_status` - `attached`, `detached`, `switching`, `unknown`
- `busy_status` - `idle`, `busy`, `error`, `unknown`
- `free_space`
- `total_space`
- `ip_address`
- `last_error`
- `updated_at`

### Таблица `device_files`

Файлы, которые устройство сообщило серверу:

- `id`
- `device_name`
- `file_name`
- `file_size`
- `modified_at`
- `synced_at`

### Таблица `jobs`

Очередь заданий для устройства:

- `id`
- `device_name`
- `job_type`
- `file_name`
- `status`
- `created_at`
- `updated_at`
- `error_message`
- `progress`
- `source`
- `note`

Возможные `status`:

- `pending`
- `running`
- `done`
- `error`
- `queued`

Возможные `job_type`:

- `download_file`
- `upload_file`
- `attach`
- `detach`

Возможные `source`:

- `user`
- `server`
- `device`

### Таблица `activity_log`

Живой журнал активности:

- `id`
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

`activity_log` нужен, чтобы видеть, что реально происходит между устройством, сервером и пользователем.

Что туда пишется:

- входящие запросы от устройств
- ответы сервера устройствам
- действия пользователя
- отказы неразрешенным устройствам
- создание jobs
- отправка jobs устройству
- загрузка файла
- обновление списка файлов устройства
- результаты действий устройства

Посмотреть лог можно через:

```text
GET /activity
```

По умолчанию возвращаются последние 100 событий. Можно передать `limit`.

Пример:

```bash
curl "http://127.0.0.1:8000/activity?limit=20"
```

## Очередь заданий

В этой версии сервер работает как диспетчер.

Что это значит:

- пользователь создает job
- сервер кладет job в очередь
- устройство получает job только через `poll`
- сервер сам не дергает физическое устройство

Логика очереди:

- если у устройства нет активной job, новая job создается как `pending`
- если уже есть `pending` или `running`, новая job создается как `queued`
- когда текущая job завершается, следующая `queued` переводится в `pending`
- если устройство занято (`busy_status = busy`), новые jobs не теряются и остаются в очереди

## Endpoint'ы

## Allowed devices

### `GET /allowed-devices`

Возвращает список разрешенных устройств.

### `POST /allowed-devices`

Добавляет или обновляет устройство в white list.

Пример запроса:

```json
{
  "device_name": "mill-01",
  "description": "RichAuto test stand"
}
```

Пример `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/allowed-devices" ^
  -H "Content-Type: application/json" ^
  -d "{\"device_name\":\"mill-01\",\"description\":\"RichAuto test stand\"}"
```

### `POST /allowed-devices/enable`

Включает устройство.

### `POST /allowed-devices/disable`

Выключает устройство.

Пример запроса для выключения:

```json
{
  "device_name": "mill-01"
}
```

## Устройства

### `POST /device/hello`

Первый запрос устройства после старта.

Пример запроса:

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

Ответ для неразрешенного устройства:

```json
{
  "status": "rejected",
  "authorized": false,
  "reason": "device_not_allowed"
}
```

### `POST /device/poll`

Устройство сообщает текущее состояние и получает job, если она есть.

Пример запроса:

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
  "job": "none",
  "file_name": null,
  "status": null,
  "authorized": null,
  "reason": null,
  "note": null
}
```

Ответ с job:

```json
{
  "job": "download_file",
  "file_name": "test.nc",
  "note": null
}
```

### `POST /device/files`

Устройство отправляет серверу актуальный список файлов.

Пример запроса:

```json
{
  "device_name": "mill-01",
  "files": [
    {
      "file_name": "part1.nc",
      "file_size": 123456,
      "modified_at": "2026-03-20T10:11:00"
    },
    {
      "file_name": "part2.nc",
      "file_size": 654321,
      "modified_at": "2026-03-20T10:12:00"
    }
  ]
}
```

Ответ:

```json
{
  "status": "ok",
  "files_received": 2
}
```

### `POST /device/action-result`

Устройство сообщает результат действия.

Пример успешного attach:

```json
{
  "device_name": "mill-01",
  "action": "attach",
  "status": "done",
  "message": "usb attached successfully"
}
```

Пример ошибки при скачивании файла:

```json
{
  "device_name": "mill-01",
  "action": "download_file",
  "status": "error",
  "message": "not enough free space"
}
```

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

`is_online` вычисляется backend'ом. Если устройство давно не обращалось, значение будет `false`.

## Файлы

### `POST /upload`

Загружает файл на сервер в `storage/uploads`.

Текущая реализация принимает файл как raw body, а имя файла передается в query string.

Пример:

```bash
curl -X POST "http://127.0.0.1:8000/upload?file_name=test.nc" ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "@test.nc"
```

Ответ:

```json
{
  "status": "ok",
  "file_name": "test.nc"
}
```

### `GET /files/server`

Возвращает список файлов, которые лежат на сервере в `storage/uploads`.

### `GET /files/device/{device_name}`

Возвращает список файлов, о которых серверу сообщил конкретный device.

Пример:

```bash
curl "http://127.0.0.1:8000/files/device/mill-01"
```

## Jobs

### `GET /jobs`

?????????? ?????? jobs ?? ??????? ????? API.

?????????????? query-?????????:

- `device_name` - ?????? ?? ????? ??????????
- `status` - ?????? ?? ??????? job
- `limit` - ??????? ??????? ???????

???????????? ????:

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

???????:

```bash
curl "http://127.0.0.1:8000/jobs"
```

```bash
curl "http://127.0.0.1:8000/jobs?device_name=mill-01&status=pending&limit=20"
```

?????? ??????:

```json
[
  {
    "id": 1,
    "device_name": "mill-01",
    "job_type": "download_file",
    "file_name": "test.nc",
    "status": "pending",
    "progress": 0,
    "created_at": "2026-03-20T11:00:43.749533+00:00",
    "updated_at": "2026-03-20T11:00:43.749533+00:00",
    "error_message": null,
    "source": "user",
    "note": null
  }
]
```

### `POST /jobs`

Создает job для устройства.

Можно создавать:

- `download_file`
- `upload_file`
- `attach`
- `detach`

Пример job на скачивание файла:

```json
{
  "device_name": "mill-01",
  "file_name": "test.nc",
  "job_type": "download_file",
  "source": "user"
}
```

Пример ручной команды attach:

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

Пример:

```json
{
  "device_name": "mill-01",
  "file_name": "test.nc",
  "status": "done",
  "message": "download complete"
}
```

## Как проверить backend вручную через `/docs`

После запуска откройте:

- `http://127.0.0.1:8000/docs`

Рекомендуемый порядок ручной проверки:

1. Вызвать `POST /allowed-devices` и добавить `mill-01`.
2. Вызвать `POST /device/hello` для `mill-01`.
3. Вызвать `POST /device/poll` и убедиться, что приходит `job = none`.
4. Вызвать `POST /upload` и загрузить `test.nc`.
5. Вызвать `POST /jobs` и создать `download_file`.
6. Еще раз вызвать `POST /device/poll` и получить job.
7. Вызвать `POST /device/action-result` и завершить `download_file`.
8. Вызвать `POST /jobs` и создать `attach` или `detach`.
9. Вызвать `POST /device/poll` и получить следующую job.
10. Вызвать `POST /device/files` и отправить список файлов устройства.
11. Проверить `GET /devices`.
12. Проверить `GET /files/server`.
13. Проверить `GET /files/device/mill-01`.
14. Проверить `GET /activity` и убедиться, что события попали в журнал.
15. Проверить отказ для неизвестного устройства через `POST /device/hello` с другим именем.

## Что было проверено локально после доработки

Локально был прогнан сценарий на временной базе и временном storage:

- добавление разрешенного устройства
- `device/hello`
- `device/poll`
- `upload`
- создание `download_file`
- создание `attach` в очередь
- получение jobs устройством
- `device/action-result`
- `device/files`
- отказ неизвестному устройству
- чтение `/activity`
- чтение `/devices`
- чтение `/files/server` и `/files/device/{device_name}`

## Важные замечания

- устройство должно быть добавлено в white list до `hello/poll`
- jobs не отправляются устройству, если оно сообщает `busy_status = busy`
- сервер не управляет устройством напрямую, а только ставит задачи в очередь
- `activity_log` хранит компактные summaries, а не полный бинарный контент
- для доступа из локальной сети сервер нужно запускать с `--host 0.0.0.0`
