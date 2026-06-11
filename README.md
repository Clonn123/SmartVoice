# SmartVoice

SmartVoice — FastAPI + Celery проект для исходящих голосовых звонков с AI-пайплайном и Asterisk ARI.

## Руты

- `POST /api/v1/call-tasks` — создаёт задачу на исходящий звонок и запускает её обработку через Celery.
- `GET /api/v1/call-tasks/{task_id}` — возвращает статус задачи, итог, диалог и ссылку на запись для последней успешной попытки.
- `GET /api/v1/call-tasks/{task_id}/attempts` — показывает историю попыток звонка.
- `GET /api/v1/recordings/{filename}` — скачивает WAV-запись по имени файла; имя можно передать как `task_1_attempt_1` или `task_1_attempt_1.wav`.

## Структура проекта

- `backend/` — основной сервис.
  - `backend/app/main.py` — старт FastAPI.
  - `backend/app/api/routes/process.py` — маршруты для звонков и загрузки записей.
  - `backend/app/modules/calls/` — логика задач, попыток и сохранения результатов.
  - `backend/app/modules/telephony/` — Asterisk/ARI и RTP интеграция.
  - `backend/app/modules/ai/` — TTS, STT, VAD и LLM-пайплайн.
  - `backend/app/repository/` — SQLAlchemy модели и репозитории.
  - `backend/app/core/config.py` — загрузка `.env` и переменных окружения.

- `backend/data/call_recordings/` — WAV-записи звонков.
- `backend/data/call_results/` — JSON-результаты задач.

## Docker и сервисы

Проект использует `docker-compose.yml` для следующих сервисов:

- `asterisk` — Asterisk ARI и RTP.
- `smartvoice` — FastAPI приложение.
- `celery-worker` — Celery worker для выполнения звонков.
- `redis` — брокер очередей.
- `postgres` — база данных.

Запуск всех контейнеров:

```powershell
docker compose up -d
```

## Подключение к базе данных

Postgres проксируется на порт `5433`.

DBeaver / другой клиент:

- Host: `localhost`
- Port: `5433`
- Database: `smartvoice`
- User: `smartvoice_admin`
- Password: `1qp21qp2`

Если нужен только контейнер Postgres:

```powershell
docker compose up -d postgres
```

## Конфигурация

Основные переменные задаются в `backend/.env`.

Пример ключевых значений:

```env
PG_USER=smartvoice_admin
PG_PASS=1qp21qp2
PG_HOST=postgres
PG_PORT=5432
PG_DB=smartvoice

ARI_USER=python
ARI_PASS=supersecret
ARI_HOST=asterisk
ARI_PORT=8088
ARI_APP=python

RTP_HOST=celery-worker
RTP_PORT=6000

CALL_RUNTIME_PROVIDER=vosk
VOSK_MODEL_PATH=/smartvoice/modules/vosk-model-small-ru-0.22
VOSK_SAMPLE_RATE=16000
VOSK_FALLBACK_TEXT=да
```

`backend/app/core/config.py` читает `.env` из каталога `backend/`.

## Работа с записями

Запись создаётся как WAV-файл в `backend/data/call_recordings/task_{task_id}_attempt_{attempt_number}.wav`.

В ответе API `recording_url` возвращается без расширения `.wav`, например:

```json
"recording_url": "task_9_attempt_1"
```

Скачать файл можно через:

```text
GET /api/v1/recordings/task_9_attempt_1
```

## Текущий статус аудио

- В текущей реализации сохраняется только входящий RTP-поток — голос клиента/входящий канал.
- Голос бота пока не смешивается в WAV-файл.

## Локальный запуск без Docker

```powershell
cd backend
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Полезные модули

- `backend/app/modules/llm/` — переключаемый провайдер LLM, включая OpenRouter.
- `backend/app/modules/ai/tts.py` — генерация речи и отправка RTP в Asterisk.
- `backend/app/modules/ai/pipeline.py` — realtime-пайплайн и логика завершения звонка.
- `backend/app/repository/unitofwork.py` — SQLAlchemy unit-of-work для звонков и попыток.

## Ссылки

- Swagger: `http://127.0.0.1:8000/docs`
- `GET /api/v1/call-tasks/{task_id}`
- `GET /api/v1/call-tasks/{task_id}/attempts`
- `GET /api/v1/recordings/{filename}`
