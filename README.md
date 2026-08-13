# BSUIR Student Telegram Web App

MVP по ТЗ: Telegram Web App + FastAPI backend + SQLite (схема совместима с переносом на PostgreSQL) + `httpx`-клиент официального API БГУИР.

## Важное ограничение верификации

Публичный API БГУИР не проверяет личный номер студента. Поэтому backend не делает небезопасное предположение «номер = группа». В проекте предусмотрен доверенный источник `backend/data/student_registry.json`: его должен подготовить администратор из официального закрытого API, университетской системы или актуального реестра. В реестре хранятся только хэши личных номеров.

Если университете выдаст закрытый endpoint, замените реализацию `StudentRegistry.verify()` в `backend/app/services/registry.py`, не меняя frontend и API приложения.

## Установка и запуск

```bash
cd outputs/telegram_student_app/backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # PowerShell; на Linux: cp .env.example .env
```

Заполните `BOT_TOKEN`, `WEB_APP_URL` (URL frontend должен быть HTTPS), затем запустите API из каталога `backend`:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Для Telegram-бота:

```bash
python -m app.bot
```

Локальный просмотр frontend через backend: `http://localhost:8000/`. В Telegram Web App backend проверяет подпись `Telegram.WebApp.initData`; frontend не содержит токенов БГУИР или реестра.

## Реальные endpoint БГУИР

Клиент использует документированные методы:

- `GET https://iis.bsuir.by/api/v1/schedule?studentGroup={groupNumber}`;
- `GET https://iis.bsuir.by/api/v1/schedule/current-week`;
- `GET https://iis.bsuir.by/api/v1/last-update-date/student-group?groupNumber={groupNumber}`.

Он учитывает `weekNumber`, `dateLesson`, `startLessonDate`, `endLessonDate`, `numSubgroup`, `announcement`, `note`, аудитории и сотрудников. При ошибке API отдаётся SQLite-кэш с понятным флагом устаревших данных.

## Реестр студентов

Положите актуальный реестр в `backend/data/student_registry.json`. Формат примера — `student_registry.example.json`. Хэш создаётся так:

```bash
python tools/hash_registry.py 123456789 YOUR_PEPPER
```

Результат вставляется в поле `personalNumberHash`. Сам личный номер в файл не записывается.

## Docker

```bash
cd outputs/telegram_student_app
copy backend/.env.example backend/.env
docker compose up --build
```

Для production используйте HTTPS reverse proxy, PostgreSQL, Redis для rate-limit/кэша и отдельный worker уведомлений.
