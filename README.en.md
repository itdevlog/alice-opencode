# Yandex Alice Skill → OpenCode Go (DeepSeek)

**🇬🇧 English** · **🇷🇺 [Русский](README.md)**

A [Yandex Alice](https://dialogs.yandex.ru/developer) skill: it receives utterances over a
webhook, gets a response from the OpenAI-compatible [OpenCode Go](https://opencode.ai/docs/go/)
API, and speaks it back.

> **Status:** experimental project, development paused. It is self-hosted on your own
> server; the author provides no guarantees and no support.

All secrets and personal values (API key, domain, skill ID) are set **only via `.env`**;
the repository contains placeholders.

## How it works

```
Alice → HTTPS → Caddy → Uvicorn (FastAPI) → OpenCode Go API → Alice's reply
```

- **Alice's limit is 4.5 seconds** for the whole reply. The skill uses a hybrid
  (streaming-first) scheme:
  - it streams the model's response and returns it if it finishes before an internal
    deadline (3.5 s by default);
  - if the model has not finished but already produced a meaningful opening, it returns
    that immediately and **computes the remainder in the background**, delivering it on
    "дальше" (next);
  - if nothing meaningful arrived in time, it replies "Секунду, я подумаю…" and computes
    the full answer in the background.
- **Memory:** dialog history and user facts (name, city, notes, style) are stored in
  SQLite, fed to the model as context, and preserved across restarts.
- **Weather:** queries like "погода в Москве" are served via Open-Meteo (no API key).
- **Date/time:** the current date and time from Alice's `meta.timezone` are added to context.
- **Speech:** the reply is stripped of markdown, links, emoji, and service tags, and
  truncated to 1024 characters.

## Commands

| Phrase | Action |
|---|---|
| any question | model answer |
| «погода» / «погода в Москве» | weather (the city is remembered) |
| «повтори» | repeat the last reply |
| «короче» / «подробнее» / «обычно» | answer length |
| «меня зовут …» / «мой город …» / «запомни: …» | remember a fact |
| «что ты обо мне знаешь» / «забудь обо мне» | show / erase facts |
| «помощь» | short help |
| «очисти историю» / «забудь всё» | erase dialog history |
| «дальше» | deliver the deferred reply/remainder |
| «выход» / «хватит» | end the session |

## Structure

```
app/
  main.py        FastAPI: POST /alice, GET /healthz
  config.py      settings from environment variables
  protocol.py    Yandex.Dialogs request/response format
  handlers.py    routing: commands, weather, memory, model call
  llm.py         OpenCode Go streaming, deadline, partial answer, background completion
  storage.py     SQLite: history, facts, deferred-answer queue
  personalization.py  user facts and answer style
  weather.py     weather via Open-Meteo
  clock.py       current date/time by Alice's timezone
  tts.py         text cleanup for speech
  commands.py    service-command recognition
tests/           pytest
run.py           uvicorn launcher (reads WEBAPP_HOST/WEBAPP_PORT)
manage.sh        install/update/backup/restore/doctor/caddy (itdevlog/manage)
```

## Environment variables

Copy `.env.example` to `.env` and fill it in:

| Variable | Default | Description |
|---|---|---|
| `OPENCODE_API_KEY` | — | OpenCode Go key (required) |
| `OPENCODE_BASE_URL` | `https://opencode.ai/zen/go/v1` | OpenAI-compatible endpoint |
| `MODEL` | `deepseek-v4.1-flash` | model |
| `DB_PATH` | `data/alice.db` | SQLite file |
| `SKILL_ID` | empty | skill ID; if set, foreign requests are rejected (403) |
| `REQUEST_DEADLINE_SECONDS` | `3.5` | internal response deadline |
| `MAX_TOKENS` | `600` | answer token limit (lower = faster) |
| `HISTORY_LIMIT` | `10` | how many recent turns to feed into context |
| `WAIT_SOUND` | empty | waiting sound (resource ID from the Dialogs console) |
| `WEATHER_ENABLED` | `true` | enable weather via Open-Meteo |
| `WEATHER_TIMEOUT` | `4.0` | weather request timeout, s |
| `WEBAPP_HOST` | `127.0.0.1` | web server address (Caddy exposes it) |
| `WEBAPP_PORT` | `8000` | web server port |
| `WEBAPP_URL` | `https://alice.example.com` | public HTTPS URL (for `./manage.sh caddy`) |

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in OPENCODE_API_KEY
.venv/bin/uvicorn app.main:create_app --factory --reload
# or via the entry point (reads WEBAPP_HOST/WEBAPP_PORT):
.venv/bin/python run.py
```

Check:

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/alice \
  -H 'Content-Type: application/json' \
  -d '{"version":"1.0","request":{"original_utterance":"привет","type":"SimpleUtterance"},"session":{"new":true,"session_id":"s","user":{"user_id":"u1"}}}'
```

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
```

## Operating on Debian 12 (manage.sh)

The project ships `manage.sh` from the [itdevlog/manage](https://github.com/itdevlog/manage)
template: install, update, backups, diagnostics, and HTTPS in a single script.

### Quick start

```bash
cd /opt/alice-opencode      # project directory
./manage.sh install         # venv, dependencies, .env, systemd service
nano .env                   # fill in OPENCODE_API_KEY
./manage.sh doctor          # configuration check
./manage.sh caddy           # HTTPS via WEBAPP_URL (needs DNS + ports 80/443)
```

Fresh install (clones the repository into `/opt/alice-opencode`):

```bash
curl -fsSL https://raw.githubusercontent.com/itdevlog/alice-opencode/master/manage.sh | bash -s -- install
```

Or a regular `git clone` followed by `./manage.sh install`.

### Commands

| Command | Action |
|---|---|
| `install` | venv, dependencies, `.env`, systemd |
| `update` | update from GitHub + backup + rollback on failure |
| `start` / `stop` / `restart` | service control |
| `status` / `logs` | status and logs |
| `backup` / `restore` | back up and restore `.env` and SQLite |
| `doctor` | environment diagnostics |
| `caddy` | HTTPS reverse proxy for `WEBAPP_URL` |
| `uninstall` | stop and remove the service |
| `help` | help |

Multiple instances on one server: `./manage.sh --instance NAME <command>`.

### DNS and HTTPS

The A record of your domain (e.g. `alice.example.com`) must point to the server IP, with
ports 80 and 443 open. `./manage.sh caddy` installs Caddy, obtains a Let's Encrypt
certificate, and proxies to `127.0.0.1:8000`. Check: `curl -s https://alice.example.com/healthz`.

### Connecting the skill

1. Open the [dialogs.yandex.ru/developer](https://dialogs.yandex.ru/developer) console.
2. Create **Skill → Dialog**.
3. Backend → **Webhook URL**: `https://alice.example.com/alice`.
4. Access type → **Private**.
5. Publish and test in the **Testing** tab.
6. Optionally copy the skill ID into `SKILL_ID` and restart the service.

## Troubleshooting

- **"Skill does not respond"** — the service did not finish within 4.5 s. Lower
  `MAX_TOKENS`, check network latency to `opencode.ai`, or raise
  `REQUEST_DEADLINE_SECONDS` (but not above ~4 s).
- **403 from `/alice`** — `SKILL_ID` mismatch.
- **TLS errors** — a full certificate chain is required; Caddy handles this automatically.
- **No API access** — check that `https://opencode.ai` is reachable from the server.

## ⚠️ Limitations

- Experimental, development paused; no support and no guarantees.
- Replies are limited by Alice's 4.5 s timeout and capped at 1024 characters of speech.
- Requires your own server, a public HTTPS domain, and an OpenCode Go API key.

## 📄 License

MIT — see [LICENSE](LICENSE).
