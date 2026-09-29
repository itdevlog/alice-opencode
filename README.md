# Навык Алисы → OpenCode Go (DeepSeek)

Навык для Яндекс.Алисы: принимает реплики по webhook, получает ответ у
OpenAI-совместимого API [OpenCode Go](https://opencode.ai/docs/go/) и озвучивает его.

> **Статус:** экспериментальный проект, развитие приостановлено. Разворачивается
> самостоятельно на своём сервере; автор не даёт гарантий и не оказывает поддержку.

Все секреты и персональные значения (API-ключ, домен, ID навыка) задаются **только
через `.env`**; в репозитории — плейсхолдеры.

## Как это работает

```
Алиса → HTTPS → Caddy → Uvicorn (FastAPI) → OpenCode Go API → ответ Алисы
```

- **Лимит Алисы — 4,5 секунды** на весь ответ. Навык работает по гибридной схеме
  (streaming-first):
  - стримит ответ модели и возвращает его, если успел за внутренний дедлайн (по умолчанию 3,5 с);
  - если модель не закончила, но уже есть осмысленное начало — отдаёт его сразу,
    а **остаток досчитывается в фоне** и выдаётся на «дальше»;
  - если ничего осмысленного не успело — отвечает «Секунду, я подумаю…» и досчитывает
    полный ответ в фоне.
- **Память:** история диалога и факты о пользователе (имя, город, заметки, стиль) хранятся
  в SQLite, подаются модели как контекст и сохраняются между запусками.
- **Погода:** запросы вида «погода в Москве» обслуживаются через Open-Meteo (без ключа).
- **Дата/время:** текущие дата и время из `meta.timezone` Алисы добавляются в контекст.
- **Речь:** ответ очищается от markdown, ссылок, эмодзи и служебных тегов, обрезается до 1024 символов.

## Команды

| Фраза | Действие |
|---|---|
| любой вопрос | ответ модели |
| «погода» / «погода в Москве» | погода (город запоминается) |
| «повтори» | повторить последний ответ |
| «короче» / «подробнее» / «обычно» | длина ответов |
| «меня зовут …» / «мой город …» / «запомни: …» | запомнить факт |
| «что ты обо мне знаешь» / «забудь обо мне» | показать / стереть факты |
| «помощь» | краткая справка |
| «очисти историю» / «забудь всё» | стереть историю диалога |
| «дальше» | отдать отложенный ответ/остаток |
| «выход» / «хватит» | завершить сессию |

## Структура

```
app/
  main.py        FastAPI: POST /alice, GET /healthz
  config.py      настройки из переменных окружения
  protocol.py    формат запроса/ответа Яндекс.Диалогов
  handlers.py    маршрутизация: команды, погода, память, вызов модели
  llm.py         стриминг OpenCode Go, дедлайн, частичный ответ и фоновый досчёт
  storage.py     SQLite: история, факты, очередь отложенных ответов
  personalization.py  факты о пользователе и стиль ответов
  weather.py     погода через Open-Meteo
  clock.py       текущая дата/время по таймзоне Алисы
  tts.py         очистка текста для озвучки
  commands.py    распознавание служебных команд
tests/           pytest
run.py           запуск uvicorn (читает WEBAPP_HOST/WEBAPP_PORT)
manage.sh        install/update/backup/restore/doctor/caddy (itdevlog/manage)
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
| `MAX_TOKENS` | `600` | лимит токенов ответа (меньше = быстрее) |
| `HISTORY_LIMIT` | `10` | сколько последних реплик подавать в контекст |
| `WAIT_SOUND` | пусто | звук ожидания (ID ресурса из консоли Диалогов) |
| `WEATHER_ENABLED` | `true` | включить погоду через Open-Meteo |
| `WEATHER_TIMEOUT` | `4.0` | таймаут запроса погоды, сек |
| `WEBAPP_HOST` | `127.0.0.1` | адрес веб-сервера (наружу отдаёт Caddy) |
| `WEBAPP_PORT` | `8000` | порт веб-сервера |
| `WEBAPP_URL` | `https://alice.example.com` | публичный HTTPS-URL (для `./manage.sh caddy`) |

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # впишите OPENCODE_API_KEY
.venv/bin/uvicorn app.main:create_app --factory --reload
# либо через точку входа (читает WEBAPP_HOST/WEBAPP_PORT):
.venv/bin/python run.py
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

## Эксплуатация на Debian 12 (manage.sh)

Проект включает `manage.sh` из шаблона [itdevlog/manage](https://github.com/itdevlog/manage):
установка, обновление, бэкапы, диагностика и HTTPS в одном скрипте.

### Быстрый старт

```bash
cd /opt/alice-opencode      # каталог с проектом
./manage.sh install         # venv, зависимости, .env, systemd-сервис
nano .env                   # впишите OPENCODE_API_KEY
./manage.sh doctor          # проверка конфигурации
./manage.sh caddy           # HTTPS по WEBAPP_URL (нужны DNS + порты 80/443)
```

Быстрая установка с нуля (клонирует репозиторий в `/opt/alice-opencode`):

```bash
curl -fsSL https://raw.githubusercontent.com/itdevlog/alice-opencode/master/manage.sh | bash -s -- install
```

Либо обычный `git clone` и `./manage.sh install`.

### Команды

| Команда | Действие |
|---|---|
| `install` | venv, зависимости, `.env`, systemd |
| `update` | обновление из GitHub + бэкап + автoоткат при сбое |
| `start` / `stop` / `restart` | управление сервисом |
| `status` / `logs` | статус и логи |
| `backup` / `restore` | бэкап и восстановление `.env` и SQLite |
| `doctor` | диагностика окружения |
| `caddy` | HTTPS reverse proxy для `WEBAPP_URL` |
| `uninstall` | остановка и удаление сервиса |
| `help` | справка |

Несколько инстансов на одном сервере: `./manage.sh --instance ИМЯ <команда>`.

### DNS и HTTPS

A-запись вашего домена (например, `alice.example.com`) должна указывать на IP
сервера, порты 80 и 443 — открыты. `./manage.sh caddy` сам установит Caddy,
выпустит сертификат Let's Encrypt и настроит проксирование на `127.0.0.1:8000`.
Проверка: `curl -s https://alice.example.com/healthz`.

### Подключение навыка

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

## Лицензия

MIT — см. [LICENSE](LICENSE).
