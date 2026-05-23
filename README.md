# SmartVoice

База MVP на FastAPI для универсального сервиса исходящего ИИ-обзвона.

## Идея

Снаружи у сервиса один основной бизнес-роут: `POST /api/v1/calls`.
Он принимает промпт, сценарий и список клиентов до 500 записей. Дальше сервер последовательно обрабатывает список: готовит LLM-контекст, вызывает mock-интеграцию звонка, получает mock-ответ клиента, формирует транскрибацию, summary, итоговый статус и JSON результата.

MVP-сценарий сейчас — напоминание или уточнение информации по договору. При этом схема не зашита только под договоры: специфичные поля сценария лежат в `payload`, а общие поля вынесены в отдельные поля ответа.

Сейчас результаты запросов сохраняются в JSON-файлы через файловый репозиторий.
Позже этот слой заменим на PostgreSQL + SQLAlchemy.

## Структура проекта

- `backend/` — основной FastAPI сервис (LLM, сценарии, оркестрация звонков).
- `frontend/` — будущий фронт.

Ключевые файлы внутри `backend/`:

- `backend/app/modules/calls/` — основная логика обзвона: схемы API, обработка списка клиентов и runtime-контракт.
- `backend/app/modules/calls/runtime.py` — минимальный контракт для будущей интеграции со звонками. Реальной телефонии тут нет.
- `backend/app/modules/calls/mock_runtime.py` — mock-реализация звонка для локальной проверки пайплайна.
- `backend/app/modules/telephony/` — Asterisk-конфиги и локальный тестовый скрипт для телефонии.
- `backend/app/repository/` — файловый репозиторий результатов звонков и задел под PostgreSQL + SQLAlchemy.
- `backend/app/modules/llm/` — LLM-интерфейс и реализация модели.

## Что сохраняется в JSON

- входящий пакет обзвона: сценарий, metadata, общий статус;
- один результат на целевой звонок: телефон, клиент, договорные поля, статус, итог;
- попытки дозвона: номер попытки, статус, время, ошибка;
- диалог: кто говорил (`bot`, `client`, `system`) и текст;
- транскрибация, summary, recording URL и технические payload-данные.

## Локальный запуск

```powershell
cd backend
py -3.10 -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Важно: окружение создаём именно на Python 3.10. Если у вас несколько версий Python, используйте `py -3.10`, а не `python`, чтобы не получить случайно другое окружение.

### Точка входа

Центральная точка входа в приложение — `backend/app/main.py`.
Именно там создаётся объект FastAPI `app`, подключаются маршруты и настраивается логирование.

Маршрутизация API собирается в `backend/app/api/router.py`, а основная оркестрация обзвона находится в `backend/app/modules/calls/service.py`.
То есть при запуске через `uvicorn app.main:app --reload` стартует приложение из `main.py`, а дальше запросы проходят через роутер в сервис обзвона.

Адреса:

- Swagger: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health`

## Пример запроса

`POST /api/v1/calls`

```json
{
  "scenario": "contract_reminder",
  "prompt": "Позвони клиенту, обратись по имени, уточни информацию по договору и зафиксируй итог.",
  "max_attempts": 2,
  "clients": [
    {
      "phone": "+79990000000",
      "client_name": "Алексей",
      "contract_id": "C-1001",
      "contract_type": "service",
      "contract_status": "overdue",
      "call_type": "contract_reminder",
      "payload": {
        "payment_due_date": "2026-05-20",
        "manager": "Иван"
      }
    }
  ],
  "metadata": {
    "source": "external-system"
  }
}
```

## Пример ответа

```json
{
  "job_id": "generated-job-uuid",
  "status": "completed",
  "scenario": "contract_reminder",
  "calls_count": 1,
  "processed_at": "2026-05-17T12:00:00Z",
  "metadata": {
    "source": "external-system",
    "max_attempts": 2
  },
  "results": [
    {
      "call_id": "generated-call-uuid",
      "external_id": null,
      "contract_id": "C-1001",
      "phone": "+79990000000",
      "client_name": "Алексей",
      "call_status": "completed",
      "result": "client_confirmed",
      "attempts": [
        {
          "attempt_number": 1,
          "status": "answered",
          "started_at": "2026-05-17T12:00:00Z",
          "finished_at": "2026-05-17T12:00:15Z",
          "duration_seconds": 15,
          "error_message": null
        }
      ],
      "dialog": [
        {
          "speaker": "bot",
          "text": "Здравствуйте, Алексей..."
        },
        {
          "speaker": "client",
          "text": "Да, подтверждаю."
        }
      ],
      "transcription": "bot: ...\nclient: ...",
      "summary": "Клиент подтвердил информацию по звонку.",
      "recording_url": "mock://recordings/example.wav",
      "payload": {
        "payment_due_date": "2026-05-20",
        "manager": "Иван"
      },
      "result_payload": {},
      "error_message": null
    }
  ]
}
```


## Логи и результаты

При запуске через `uvicorn` процесс обработки пишется в консоль через стандартный `logging`.
Уровень логов можно поменять в `backend/.env`:

```env
LOG_LEVEL=INFO
```

Результаты mock-запросов сохраняются в `backend/data/call_results/<job_id>.json`.

Текущая реализация записи результатов находится в `backend/app/repository/file_repository.py`.

### Локальный STT через Vosk

Можно включить локальный runtime с Vosk:

```env
CALL_RUNTIME_PROVIDER=vosk
VOSK_MODEL_PATH=C:/models/vosk-model-ru-0.42
VOSK_SAMPLE_RATE=16000
VOSK_FALLBACK_TEXT=да
# опционально для локальной проверки без Asterisk
VOSK_TEST_AUDIO_PATH=C:/temp/test.wav
```

Если `VOSK_TEST_AUDIO_PATH` не задан, runtime вернет fallback-текст, чтобы пайплайн оставался рабочим.