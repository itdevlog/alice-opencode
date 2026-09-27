# Навык Алисы → OpenCode Go (DeepSeek)

Приватный навык для Яндекс.Алисы: принимает реплики по webhook, получает ответ у
OpenAI-совместимого API [OpenCode Go](https://opencode.ai/docs/go/) и озвучивает его.

## Как это работает

```
Алиса → HTTPS → Caddy → Uvicorn (FastAPI) → OpenCode Go API → ответ Алисы
```

- **Лимит Алисы — 4,5 секунды** на весь ответ. Навык работает по гибридной схеме:
  - стримит ответ модели и возвращает его, если успел за внутренний дедлайн (по умолчанию 3,5 с);
  - если не успел — отвечает «Секунду, я подумаю. Скажи „дальше“» и **досчитывает ответ в фоне**;
  - на следующей реплике готовый ответ отдаётся из очереди.
- **Память:** последние реплики диалога хранятся в SQLite и подаются модели как контекст.
  Долгая история сохраняется между запусками навыка.
- **Речь:** ответ очищается от markdown, ссылок, эмодзи и служебных тегов, обрезается до 1024 символов.

## Команды

| Фраза | Действие |
|---|---|
| любой вопрос | ответ модели |
| «помощь» | краткая справка |
| «очисти историю» / «забудь всё» | стереть историю диалога |
| «дальше» | отдать отложенный ответ |
| «выход» / «хватит» | завершить сессию |

## Структура

```
app/
  main.py        FastAPI: POST /alice, GET /healthz
  config.py      настройки из переменных окружения
  protocol.py    формат запроса/ответа Яндекс.Диалогов
  handlers.py    маршрутизация: команды, память, вызов модели
  llm.py         стриминг OpenCode Go, дедлайн, фоновый досчёт
  storage.py     SQLite: история и очередь отложенных ответов
  tts.py         очистка текста для озвучки
  commands.py    распознавание служебных команд
tests/           pytest (57 тестов)
deploy/          Caddyfile и systemd-юнит
```

## Переменные окружения

Скопируйте `.env.example` в `.env` и заполните:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENCODE_API_KEY` | — | ключ OpenCode Go (обязателен) |
| `OPENCODE_BASE_URL` | `https://opencode.ai/zen/go/v1` | OpenAI-совместимый эндпоинт |
| `MODEL` | `deepseek-v4.1-flash` | модель |
| `DB_PATH` | `data/alice.db` | файл SQLite |
| `SKILL_ID` | пусто | ID навыка; если задан, чужие запросы отклоняются (403) |
| `REQUEST_DEADLINE_SECONDS` | `3.5` | внутренний дедлайн ответа |
| `MAX_TOKENS` | `400` | лимит токенов ответа (меньше = быстрее) |
| `HISTORY_LIMIT` | `10` | сколько последних реплик подавать в контекст |

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # впишите OPENCODE_API_KEY
.venv/bin/uvicorn app.main:create_app --factory --reload
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/alice \
  -H 'Content-Type: application/json' \
  -d '{"version":"1.0","request":{"original_utterance":"привет","type":"SimpleUtterance"},"session":{"new":true,"session_id":"s","user":{"user_id":"u1"}}}'
```

## Тесты

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
```

## Деплой на Debian 12

### 1. Пользователь и код

```bash
sudo useradd --system --home /opt/alice-skill --shell /usr/sbin/nologin alice
sudo mkdir -p /opt/alice-skill
sudo chown alice:alice /opt/alice-skill
# скопируйте файлы проекта в /opt/alice-skill (git clone / rsync / scp)
```

### 2. Окружение

```bash
cd /opt/alice-skill
sudo -u alice python3 -m venv .venv
sudo -u alice .venv/bin/pip install -r requirements.txt
sudo -u alice cp .env.example .env
sudo -u alice nano .env               # впишите OPENCODE_API_KEY
sudo chmod 600 .env
```

### 3. systemd

```bash
sudo cp deploy/alice-skill.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alice-skill
systemctl status alice-skill
curl -s http://127.0.0.1:8000/healthz
```

### 4. HTTPS через Caddy

```bash
# установите Caddy по официальной инструкции caddyserver.com/docs/install
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # при необходимости замените домен
sudo systemctl reload caddy
```

DNS: A-запись домена (например, `alice.example.com`) должна указывать на IP сервера,
порты 80 и 443 — открыты. Caddy сам получит сертификат Let's Encrypt.
Проверка: `curl -s https://alice.example.com/healthz`.

### 5. Подключение навыка

1. Откройте консоль [dialogs.yandex.ru/developer](https://dialogs.yandex.ru/developer).
2. Создайте **Навык → Диалог**.
3. Backend → **Webhook URL**: `https://alice.example.com/alice`.
4. Тип доступа → **Приватный**.
5. Опубликуйте и проверьте во вкладке **Тестирование**.
6. По желанию скопируйте ID навыка в `SKILL_ID` и перезапустите сервис.

## Диагностика

- **«Навык не отвечает»** — сервис не уложился в 4,5 с. Уменьшите `MAX_TOKENS`,
  проверьте сетевую задержку до `opencode.ai`, увеличьте `REQUEST_DEADLINE_SECONDS`
  (но не выше ~4 с).
- **403 от `/alice`** — не совпал `SKILL_ID`.
- **Ошибки TLS** — нужен полный chain-сертификат; с Caddy это решается автоматически.
- **Нет доступа к API** — проверьте, что с сервера открывается `https://opencode.ai`.
