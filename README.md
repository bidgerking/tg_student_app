# BSUIR Student Telegram Web App

MVP по ТЗ: Telegram Web App + FastAPI backend + SQLite (схема совместима с переносом на PostgreSQL) + `httpx`-клиент официального API БГУИР.

## Быстрый тестовый пользователь

В проект добавлен development-профиль:

- личный номер: `123456789`;
- ФИО: Тестовый Студент;
- факультет: ФКСиС;
- специальность: Информатика и технологии программирования;
- группа: `053503`;
- подгруппа: `1`.

Для локального запуска уже включён `DEV_AUTH_ENABLED=true` в локальном `.env`. В production оставьте `DEV_AUTH_ENABLED=false` и удалите тестовый реестр. Development-сессия принимает только специальное значение `dev-test-init-data` и не работает при выключенном флаге.

Если frontend опубликован отдельно, укажите настоящий HTTPS-адрес backend в `frontend/runtime-config.js`. Временные адреса `trycloudflare.com` перестают работать после остановки туннеля. При запуске frontend через FastAPI оставьте значение пустым: запросы пойдут на тот же origin.

## Регистрация и вход

После открытия Web App выберите «Регистрация», введите `123456789` и пароль длиной не менее 10 символов. Backend покажет найденные данные студента; после подтверждения аккаунт и профиль сохраняются в SQLite. При следующем запуске выберите «Войти» и используйте тот же личный номер и пароль.

В профиле доступны смена пароля, выход с текущего или всех устройств и удаление аккаунта. Пароли хранятся только как Argon2id-хэши, личный номер — только как хэш с серверным `STUDENT_REGISTRY_PEPPER`; постоянные сессии передаются в HttpOnly cookie.

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
