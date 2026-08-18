# BSUIR Student Telegram Web App

MVP по ТЗ: Telegram Web App + FastAPI backend + SQLite (схема совместима с переносом на PostgreSQL) + `httpx`-клиент официального API БГУИР.

## Тестовые пользователи

В локальный development-реестр добавлены три профиля:

- личный номер: `123456789`;
- ФИО: Тестовый Студент;
- группа: `624401`;
- факультет, специальность и курс уточняются по данным этой группы из API БГУИР при входе;
- подгруппа: `1`.

Дополнительные профили для проверки друзей:

- `123456790` — Тестовый Друг 1, группа `053503`, подгруппа `2`;
- `123456791` — Тестовый Друг 2, группа `053503`, подгруппа `1`.

Пароль задаётся самостоятельно при регистрации и должен содержать минимум 10 символов. Эти номера являются только локальными тестовыми данными и не должны использоваться в production.

Файл `backend/data/student_registry.json` исключён из Git. После чистого клона восстановите эти development-записи из каталога `backend`:

```powershell
python tools/seed_test_registry.py
```

Для локального запуска уже включён `DEV_AUTH_ENABLED=true` в локальном `.env`. В production оставьте `DEV_AUTH_ENABLED=false` и удалите тестовый реестр. Development-сессия принимает только значения `dev-test-init-data`, `dev-test-init-data-2` и `dev-test-init-data-3` и не работает при выключенном флаге.

### Проверка трёх пользователей в браузере

В dev-режиме можно открыть один backend в трёх отдельных вкладках:

```text
http://127.0.0.1:8000/?testUser=1
http://127.0.0.1:8000/?testUser=2
http://127.0.0.1:8000/?testUser=3
```

В первой вкладке зарегистрируйте `123456789`, во второй — `123456790`, в третьей — `123456791`. Затем в разделе «Друзья» первой вкладки найдите два других профиля по номеру или ФИО и отправьте заявки. Входящие заявки можно принять во второй или третьей вкладке. Суффиксы `testUser` работают только на `localhost`/`127.0.0.1` при включённом `DEV_AUTH_ENABLED`.

Если frontend опубликован отдельно, укажите настоящий HTTPS-адрес backend в `frontend/runtime-config.js`. Временные адреса `trycloudflare.com` перестают работать после остановки туннеля. При запуске frontend через FastAPI оставьте значение пустым: запросы пойдут на тот же origin.

## Регистрация и вход

После открытия Web App выберите «Регистрация», введите `123456789` и пароль длиной не менее 10 символов. Backend покажет найденные данные студента; после подтверждения аккаунт и профиль сохраняются в SQLite. При следующем запуске выберите «Войти» и используйте тот же личный номер и пароль.

В профиле доступны выход с текущего или всех устройств. Пароли хранятся только как Argon2id-хэши, личный номер — только как хэш с серверным `STUDENT_REGISTRY_PEPPER`; постоянные сессии передаются в HttpOnly cookie.

## Друзья

Нажмите на плашку `BSUIR STUDENT` в левом верхнем углу Web App и откройте раздел «Друзья». В нём доступны список друзей, входящие и отправленные заявки, удаление друга и поиск по ФИО или личному номеру. Поиск по номеру сверяет номер с доверенным реестром и показывает только студента, у которого уже есть подтверждённый аккаунт; сам номер в API и базе друзей не сохраняется.

Для друзей добавлена SQLite-таблица `friendships`. Она создаётся автоматически при запуске backend, поэтому отдельной миграции для локального запуска не требуется.

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

После изменения `backend/.env` или кода перезапустите backend и бота: в каждом окне PowerShell нажмите `Ctrl+C`, затем повторите команды запуска. После изменения только `student_registry.json` достаточно перезапустить backend, чтобы гарантированно подхватить обновление.

Локальный просмотр frontend через backend: `http://localhost:8000/`. В Telegram Web App backend проверяет подпись `Telegram.WebApp.initData`; frontend не содержит токенов БГУИР или реестра.

### Запуск через Telegram

Telegram не открывает `localhost`, поэтому для тестирования из Telegram frontend и backend должны быть доступны по одному актуальному HTTPS-адресу. Запустите API:

```powershell
cd outputs/telegram_student_app/backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

В отдельном окне PowerShell создайте HTTPS-туннель:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Скопируйте выданный туннелем адрес вида `https://<имя>.trycloudflare.com` в `WEB_APP_URL` файла `backend/.env`. Остановите и снова запустите бота:

```powershell
python -m app.bot
```

`frontend/runtime-config.js` при таком запуске оставляется пустым: Web App и API находятся на одном origin, поэтому запросы идут на `/api/...` без CORS и без отдельного адреса backend. Каждый новый Quick Tunnel выдаёт новый URL, его необходимо заново указать в `WEB_APP_URL` и перезапустить бота.

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
