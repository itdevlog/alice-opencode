#!/usr/bin/env bash
# manage.sh — установка, обновление и эксплуатация навыка Алисы
# (вебхук OpenCode Go / DeepSeek). Шаблон itdevlog/manage.
#
# Это ШАБЛОН. Скопируйте его в репозиторий бота и заполните блок BOT CONFIG
# ниже. Движок (всё, что после маркера «ДВИЖОК») одинаков у всех ботов и не
# редактируется — при обновлении шаблона переносится только блок BOT CONFIG.
#
# Использование:
#   ./manage.sh [--instance ИМЯ] [--no-color] <команда>
#
# Быстрая установка с нуля (без ручного клонирования):
#   curl -fsSL <URL_ДО_mange.sh_в_репозитории_бота> | bash -s -- install
#
# Подробности — в README.md шаблона.
set -Eeuo pipefail

# =============================================================================
# >>> BOT CONFIG (правится при копировании) >>>
# =============================================================================
# Блок ниже — единственное, что нужно менять под конкретного бота.
# У каждой переменной есть безопасный дефолт, кроме REPO_URL/INSTALL_DIR_DEFAULT:
# они нужны только для установки через `curl | bash`.

# --- Идентификация и репозиторий ---------------------------------------------
BOT_TITLE="Alice OpenCode Skill"             # Человеческое имя (systemd, справка)
REPO_URL="https://github.com/itdevlog/alice-opencode.git"  # Для curl|bash bootstrap
INSTALL_DIR_DEFAULT="/opt/alice-opencode"    # Куда клонировать при curl|bash
SERVICE_BASE="alice-skill"                   # База имени systemd-юнита
DEFAULT_INSTANCE="alice-opencode"            # Инстанс по умолчанию
MANAGE_INSTANCE_ENV="ALICE_INSTANCE"         # Env-переменная с именем инстанса

# --- Запуск -------------------------------------------------------------------
START_TARGET="run.py"        # Аргумент python: "run.py" поднимает uvicorn
REQUIREMENTS="requirements.txt"
PYTHON_MIN="3.11"
RESTART_POLICY="on-failure"  # on-failure | always
EXTRA_DIRS="data backups"    # Создаются при install; исключаются из git-untracked
LOG_FILE="data/alice.log"    # Лог ручного запуска (относительно каталога проекта)

# --- Конфигурация .env --------------------------------------------------------
ENV_FILE_NAME=".env"
ENV_EXAMPLE_NAME=".env.example"
TOKEN_ENV_KEY="OPENCODE_API_KEY"           # Ключ OpenCode Go
TOKEN_PLACEHOLDER="sk-opencode-your-key-here"  # Подстрока «ключ не задан»
REQUIRED_ENV_KEYS=""                       # Доп. обязательные ключи
DOCTOR_IMPORTS="fastapi uvicorn httpx dotenv"  # Python-модули, проверяемые в doctor

# --- Фича: бэкап БД (SQLite) --------------------------------------------------
USE_DB_BACKUP="true"
DB_ENV_KEY="DB_PATH"
DB_DEFAULT="data/alice.db"
BACKUP_PATHS=""                        # Доп. пути в архив (БД сохраняется отдельно)
DATA_PATHS="data"                      # Что удалять при uninstall

# --- Фича: веб-сервер (webhook) и health-check --------------------------------
USE_WEBAPP_HEALTH="true"
WEBAPP_PORT_KEY="WEBAPP_PORT"
WEBAPP_PORT_DEFAULT="8000"
WEBAPP_HOST_KEY="WEBAPP_HOST"
HEALTH_PATH="/healthz"

# --- Фича: Caddy (HTTPS reverse proxy) ----------------------------------------
USE_CADDY="true"
WEBAPP_URL_KEY="WEBAPP_URL"

# --- Фича: ручной запуск без systemd ------------------------------------------
USE_MANUAL_START="true"

# --- Прочее -------------------------------------------------------------------
BACKUP_KEEP=10
HEALTH_TIMEOUT=30
# =============================================================================
# <<< BOT CONFIG <<<
# =============================================================================

# =============================================================================
# ДВИЖОК — не редактируется. Одинаков у всех ботов.
# При обновлении шаблона скопируйте новый manage.sh и перенесите свой BOT CONFIG.
# =============================================================================

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    SCRIPT_DIR=""   # запущен из пайпа (curl | bash) — репозитория рядом нет
fi

VENV_DIR="${SCRIPT_DIR:-.}/.venv"
ENV_FILE="${SCRIPT_DIR:-.}/${ENV_FILE_NAME}"
ENV_EXAMPLE="${SCRIPT_DIR:-.}/${ENV_EXAMPLE_NAME}"
BACKUP_DIR="${SCRIPT_DIR:-.}/backups"
CADDY_DIR="/etc/caddy"
CADDY_MAIN="${CADDY_DIR}/Caddyfile"

sanitize_instance() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '-' \
        | sed -e 's/^-\+//' -e 's/-\+$//'
}

init_instance() {
    local raw="${1:-}"
    if [[ -z "$raw" && -n "${MANAGE_INSTANCE_ENV:-}" && -n "${!MANAGE_INSTANCE_ENV:-}" ]]; then
        raw="${!MANAGE_INSTANCE_ENV}"
    fi
    [[ -n "$raw" ]] || raw="$(basename "${SCRIPT_DIR:-$DEFAULT_INSTANCE}")"
    INSTANCE="$(sanitize_instance "$raw")"
    [[ -n "$INSTANCE" ]] || INSTANCE="$DEFAULT_INSTANCE"
    SERVICE_NAME="${SERVICE_BASE}-${INSTANCE}"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    PID_FILE="${SCRIPT_DIR:-.}/bot.${INSTANCE}.pid"
    CADDY_SITE="${CADDY_DIR}/conf.d/${INSTANCE}.caddy"
}
init_instance

# Источник интерактивного ввода. При curl | bash stdin занят телом скрипта,
# поэтому вопросы читаем напрямую с терминала. Нет tty — пусто (ответы = дефолт).
INPUT_FD=""
if [[ -t 0 ]]; then
    INPUT_FD="/dev/stdin"
elif { exec 9< /dev/tty; } 2>/dev/null; then
    exec 9<&-
    INPUT_FD="/dev/tty"
fi

is_repo() {
    [[ -n "$SCRIPT_DIR" ]] \
        && [[ -f "${SCRIPT_DIR}/${REQUIREMENTS}" ]] \
        && [[ -f "${SCRIPT_DIR}/${ENV_EXAMPLE_NAME}" ]] \
        && git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

# --- Цветной вывод -----------------------------------------------------------
set_colors() {
    if [[ "$1" == "off" || -n "${NO_COLOR:-}" ]]; then
        C_OK=""; C_ERR=""; C_WARN=""; C_INFO=""; C_DIM=""; C_OFF=""
    else
        C_OK=$'\033[32m'; C_ERR=$'\033[31m'; C_WARN=$'\033[33m'
        C_INFO=$'\033[36m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
    fi
}
set_colors on

ok()   { printf '%s[OK]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
fail() { printf '%s[FAIL]%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; }
warn() { printf '%s[WARN]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
info() { printf '%s[INFO]%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }
die()  { fail "$*"; exit 1; }

# --- .env и производные значения --------------------------------------------
env_get() {
    # env_get <KEY> — значение из .env или пусто
    [[ -f "$ENV_FILE" ]] || return 1
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

set_env_value() {
    # set_env_value <KEY> <VALUE> — заменить или добавить строку в .env
    local key="$1" val="$2"
    local esc
    esc=$(printf '%s' "$val" | sed -e 's/[&|]/\\&/g')
    if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${esc}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
    fi
}

token_configured() {
    local token
    token=$(env_get "$TOKEN_ENV_KEY")
    [[ -n "$token" ]] || return 1
    [[ -n "$TOKEN_PLACEHOLDER" && "$token" == *"$TOKEN_PLACEHOLDER"* ]] && return 1
    [[ "$token" == *"123456789:ABCdef"* ]] && return 1
    return 0
}

get_port() {
    [[ "$USE_WEBAPP_HEALTH" == "true" ]] || { echo "0"; return; }
    local port
    port=$(env_get "$WEBAPP_PORT_KEY")
    if [[ ! -f "$ENV_FILE" ]] || ! grep -qE "^${WEBAPP_PORT_KEY}=" "$ENV_FILE" 2>/dev/null; then
        echo "$WEBAPP_PORT_DEFAULT"
    elif [[ "$port" =~ ^[0-9]+$ ]]; then
        echo "$port"
    else
        echo "0"
    fi
}

get_webapp_url() {
    env_get "$WEBAPP_URL_KEY"
}

get_webapp_domain() {
    local url
    url=$(get_webapp_url)
    url="${url#http://}"
    url="${url#https://}"
    url="${url%%/*}"
    echo "$url"
}

get_db_file() {
    # Абсолютный путь к БД из DB_ENV_KEY или DB_DEFAULT (относительно каталога бота)
    [[ "$USE_DB_BACKUP" == "true" ]] || return 1
    local db
    db=$(env_get "$DB_ENV_KEY")
    db="${db:-$DB_DEFAULT}"
    if [[ "$db" == /* ]]; then
        echo "$db"
    else
        echo "${SCRIPT_DIR:-.}/${db}"
    fi
}

resolve_log_file() {
    case "$LOG_FILE" in
        /*) printf '%s\n' "$LOG_FILE" ;;
        *)  printf '%s\n' "${SCRIPT_DIR:-.}/${LOG_FILE}" ;;
    esac
}

# --- systemd и процессы -------------------------------------------------------
systemd_available() { command -v systemctl >/dev/null 2>&1; }
service_exists() { systemd_available && systemctl list-unit-files "${SERVICE_NAME}.service" --no-legend 2>/dev/null | grep -q .; }
service_active() { service_exists && systemctl is-active --quiet "${SERVICE_NAME}.service"; }

run_root() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        die "Нужны права root (запустите под root или установите sudo)"
    fi
}

system_pm() {
    local pm
    for pm in apt-get dnf yum apk; do
        command -v "$pm" >/dev/null 2>&1 && { echo "$pm"; return 0; }
    done
    return 1
}

install_pkgs() {
    [[ $# -gt 0 ]] || return 0
    local pm
    pm=$(system_pm) || die "Пакетный менеджер не найден — установите вручную: $*"
    case "$pm" in
        apt-get) run_root apt-get update -qq && run_root apt-get install -y -qq "$@" >/dev/null ;;
        dnf)     run_root dnf install -y -q "$@" ;;
        yum)     run_root yum install -y -q "$@" ;;
        apk)     run_root apk add --quiet "$@" ;;
    esac
}

ensure_cmd() {
    local cmd="$1"; shift
    command -v "$cmd" >/dev/null 2>&1 && return 0
    warn "'${cmd}' не найден — потребуется установить: $*"
    confirm "Установить ($*)?" y || die "'${cmd}' обязателен. Установите вручную: $*"
    install_pkgs "$@" || die "Не удалось установить: $*"
    command -v "$cmd" >/dev/null 2>&1 || die "Команда '${cmd}' всё ещё недоступна после установки"
    ok "Установлено: $*"
}

proc_pattern() {
    # Регэксп pgrep для процесса бота: basename точки входа из START_TARGET
    printf 'python.*%s' "${START_TARGET##*/}"
}

external_pid() {
    # PID процесса бота, запущенного без systemd/pid-файла, только из нашего каталога
    local pid cwd
    for pid in $(pgrep -f "$(proc_pattern)" 2>/dev/null || true); do
        cwd=$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)
        if [[ "$cwd" == "$SCRIPT_DIR" ]]; then
            echo "$pid"
            return 0
        fi
    done
    return 1
}

pid_is_bot() {
    # pid_is_bot <pid> — True если это процесс бота из нашего каталога (защита от reuse PID)
    local pid="$1" cmdline cwd
    [[ -n "$pid" && -d "/proc/${pid}" ]] || return 1
    cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    [[ "$cmdline" == *"${START_TARGET##*/}"* ]] || return 1
    cwd=$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)
    [[ "$cwd" == "$SCRIPT_DIR" ]]
}

service_running() {
    service_active && return 0
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
        return 0
    fi
    external_pid >/dev/null
}

health_check() {
    # health_check <port> — успех если бот отвечает HEALTH_PATH; при port=0 — проверка процесса
    local port="$1" waited=0
    if [[ "$port" == "0" ]]; then
        service_running
        return $?
    fi
    while (( waited < HEALTH_TIMEOUT )); do
        if curl -sf "http://localhost:${port}${HEALTH_PATH}" >/dev/null 2>&1; then
            return 0
        fi
        service_running || return 1
        sleep 2; waited=$((waited + 2))
    done
    return 1
}

wait_health() {
    if [[ "$USE_WEBAPP_HEALTH" == "true" ]]; then
        info "Жду ответа ${HEALTH_PATH} (до ${HEALTH_TIMEOUT}с)..."
        if health_check "$(get_port)"; then ok "Бот работает"; else warn "Health-check не прошёл — смотрите логи: ./manage.sh logs"; fi
    elif service_running; then
        ok "Бот работает"
    else
        warn "Бот не запущен"
    fi
    return 0
}

ask() {
    local default="$1"; shift
    local reply=""
    if [[ -n "$INPUT_FD" ]]; then
        read -r -p "$* ${C_DIM}[${default:-пусто}]:${C_OFF} " reply < "$INPUT_FD" || reply=""
    fi
    REPLY="${reply:-$default}"
}

confirm() {
    local prompt="$1" default="${2:-y}" reply=""
    if [[ -n "$INPUT_FD" ]]; then
        read -r -p "${prompt} [${default^^}] " reply < "$INPUT_FD" || reply=""
    fi
    reply="${reply:-$default}"
    [[ "${reply,,}" == "y" || "${reply,,}" == "да" ]]
}

# --- install / service --------------------------------------------------------
migrate_legacy_service() {
    # Установки до мульти-инстанса держали единый юнит <SERVICE_BASE>.service.
    # Если он указывает на наш каталог — заменяем инстансным, иначе не трогаем.
    local legacy_file="/etc/systemd/system/${SERVICE_BASE}.service"
    [[ -f "$legacy_file" ]] || return 0
    local wd
    wd=$(grep -E '^WorkingDirectory=' "$legacy_file" 2>/dev/null | cut -d= -f2- || true)
    [[ "$wd" == "$SCRIPT_DIR" ]] || return 0
    info "Найден старый сервис ${SERVICE_BASE}.service для этого каталога — переношу в ${SERVICE_NAME}.service"
    systemctl stop "${SERVICE_BASE}.service" >/dev/null 2>&1 || true
    systemctl disable "${SERVICE_BASE}.service" >/dev/null 2>&1 || true
    rm -f "$legacy_file"
    systemctl daemon-reload 2>/dev/null || true
}

install_service() {
    migrate_legacy_service
    local svc_user="${USER:-$(id -un)}"
    info "systemd-сервис будет работать от пользователя ${svc_user}"
    if [[ "$svc_user" == "root" && "${EUID:-$(id -u)}" -eq 0 ]]; then
        warn "Сервис ставится от root — при запуске через sudo это ожидаемо. Если нужен другой пользователь, запустите install не под root"
    fi
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=${BOT_TITLE} (${INSTANCE})
After=network.target

[Service]
Type=simple
User=${svc_user}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python ${START_TARGET}
Restart=${RESTART_POLICY}
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload || die "systemctl daemon-reload не сработал"
    if token_configured; then
        systemctl enable --now "${SERVICE_NAME}.service" \
            || die "Не удалось запустить сервис. Проверьте: systemctl status ${SERVICE_NAME}"
        ok "systemd-сервис установлен и запущен (автозапуск включён)"
    else
        systemctl enable "${SERVICE_NAME}.service" >/dev/null \
            || die "Не удалось включить автозапуск сервиса"
        warn "Сервис установлен, но НЕ запущен: токен в .env не задан"
        info "Впишите ${TOKEN_ENV_KEY} в ${ENV_FILE}, затем: ./manage.sh start"
    fi
    dim "Статус: systemctl status ${SERVICE_NAME}.service"
}

cmd_install() {
    if ! is_repo; then
        die "В ${SCRIPT_DIR:-текущем каталоге} нет репозитория бота (${REQUIREMENTS} / ${ENV_EXAMPLE_NAME}).
Клонируйте: git clone ${REPO_URL}
Или используйте быструю установку: curl -fsSL <REPO>/manage.sh | bash -s -- install"
    fi
    info "Установка ${BOT_TITLE} в ${SCRIPT_DIR}"

    ensure_cmd git git
    ensure_cmd curl curl

    local py_bin=""
    for p in python3.13 python3.12 python3.11 python3; do
        if command -v "$p" >/dev/null 2>&1; then
            "$p" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${PYTHON_MIN}'.split('.')) else 1)" 2>/dev/null \
                && { py_bin="$p"; break; }
        fi
    done
    if [[ -z "$py_bin" ]]; then
        fail "Python ${PYTHON_MIN}+ не найден"
        local pm
        pm=$(system_pm) || die "Установите Python ${PYTHON_MIN}+ вручную: https://python.org"
        case "$pm" in
            apt-get) install_pkgs python3 python3-venv python3-pip ;;
            dnf|yum) install_pkgs python3 python3-pip ;;
            apk)     install_pkgs python3 py3-pip ;;
        esac || die "Не удалось установить Python"
        for p in python3.13 python3.12 python3.11 python3; do
            command -v "$p" >/dev/null 2>&1 && { py_bin="$p"; break; }
        done
        [[ -n "$py_bin" ]] || die "Python ${PYTHON_MIN}+ не найден после установки — обновите дистрибутив"
    fi
    ok "Python: $("$py_bin" --version)"

    if ! "$py_bin" -c 'import venv' 2>/dev/null; then
        warn "Модуль venv недоступен — устанавливаю"
        install_pkgs python3-venv || install_pkgs python3 || die "Установите python3-venv вручную"
        "$py_bin" -c 'import venv' 2>/dev/null || die "Модуль venv всё ещё недоступен"
    fi

    if [[ -d "$VENV_DIR" ]]; then
        info "Виртуальное окружение уже существует — обновляю пакеты"
    else
        "$py_bin" -m venv "$VENV_DIR" || die "Не удалось создать venv в ${VENV_DIR}"
    fi
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip \
        || warn "Не удалось обновить pip (не критично)"
    if [[ -f "${SCRIPT_DIR}/${REQUIREMENTS}" ]]; then
        "$VENV_DIR/bin/pip" install --quiet -r "${SCRIPT_DIR}/${REQUIREMENTS}" \
            || die "Не удалось установить зависимости"
        ok "Зависимости установлены ($(grep -cve '^\s*$' "${SCRIPT_DIR}/${REQUIREMENTS}") пакетов)"
    else
        warn "Файл ${REQUIREMENTS} не найден — пропускаю установку зависимостей"
    fi

    local d
    for d in $EXTRA_DIRS; do
        mkdir -p "${SCRIPT_DIR}/${d}"
    done
    [[ -n "$EXTRA_DIRS" ]] && ok "Директории: ${EXTRA_DIRS}"

    if [[ -f "$ENV_FILE" ]]; then
        info "Файл ${ENV_FILE_NAME} уже существует — пропускаю настройку"
    elif [[ -z "$INPUT_FD" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        warn "Скопирован ${ENV_EXAMPLE_NAME} -> ${ENV_FILE_NAME} (терминала нет — интерактив пропущен)"
        warn "Впишите токен бота: nano ${ENV_FILE} и запустите ./manage.sh doctor"
    elif confirm "Настроить ${ENV_FILE_NAME} интерактивно?" y; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"

        local token=""
        while [[ -z "$token" ]]; do
            ask "" "Введите токен бота (у @BotFather)"
            token="$REPLY"
            [[ -n "$token" ]] || warn "Токен не может быть пустым"
        done
        set_env_value "$TOKEN_ENV_KEY" "$token"

        if [[ "$USE_WEBAPP_HEALTH" == "true" && "$WEBAPP_PORT_KEY" != "$TOKEN_ENV_KEY" ]]; then
            ask "$WEBAPP_PORT_DEFAULT" "Порт веб-версии (0 = отключить; 80/443 занимает Caddy)"
            set_env_value "$WEBAPP_PORT_KEY" "$REPLY"
            if [[ "$REPLY" != "0" ]] && port_in_use "$REPLY"; then
                warn "Порт ${REPLY} уже занят — возможно, другим ботом. Смените ${WEBAPP_PORT_KEY} в ${ENV_FILE}"
            fi
        fi

        ok "${ENV_FILE_NAME} создан"
        warn "Проверьте остальные значения в ${ENV_FILE}"
    else
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        warn "Скопирован ${ENV_EXAMPLE_NAME} -> ${ENV_FILE_NAME}. Отредактируйте: nano ${ENV_FILE}"
        info "После настройки запустите: ./manage.sh doctor"
    fi

    if service_exists; then
        info "systemd-сервис уже установлен"
    elif systemd_available; then
        if confirm "Установить systemd-сервис (автозапуск)?" y; then
            install_service
        else
            info "Хорошо. Запуск вручную: ./manage.sh start"
        fi
    else
        info "systemd недоступен — запуск вручную: ./manage.sh start"
    fi

    echo
    ok "Установка завершена!"
    dim "Дальше: ./manage.sh doctor — проверка конфигурации"
    dim "  Запуск: ./manage.sh start"
    dim "  Логи:   ./manage.sh logs"
}

# --- start / stop / restart / status / logs -----------------------------------
do_stop() {
    if service_active; then
        systemctl stop "${SERVICE_NAME}.service" && ok "Сервис остановлен"
    elif [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
        local pid
        pid=$(cat "$PID_FILE")
        if ! pid_is_bot "$pid"; then
            warn "PID ${pid} из ${PID_FILE} не принадлежит боту — удаляю устаревший PID-файл"
            rm -f "$PID_FILE"
        else
            kill "$pid" 2>/dev/null || true
            local waited=0
            while kill -0 "$pid" 2>/dev/null && (( waited < 10 )); do
                sleep 1; waited=$((waited + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                warn "Процесс ${pid} не завершился за 10с — отправляю SIGKILL"
                kill -9 "$pid" 2>/dev/null || true
                sleep 1
            fi
            rm -f "$PID_FILE"
            ok "Процесс остановлен"
        fi
    elif external_pid >/dev/null; then
        local pid
        pid=$(external_pid)
        warn "Найден процесс бота (PID ${pid}), запущенный вне скрипта"
        if confirm "Остановить его?" y; then
            kill "$pid" 2>/dev/null || true
            local waited=0
            while kill -0 "$pid" 2>/dev/null && (( waited < 10 )); do
                sleep 1; waited=$((waited + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                warn "Процесс ${pid} не завершился за 10с — отправляю SIGKILL"
                kill -9 "$pid" 2>/dev/null || true
                sleep 1
            fi
            ok "Процесс остановлен"
        else
            info "Оставляю процесс как есть"
        fi
    else
        info "Бот не запущен"
    fi
}

do_start() {
    if ! token_configured; then
        die "Токен бота не задан в ${ENV_FILE}. Впишите ${TOKEN_ENV_KEY} и повторите"
    fi
    if service_exists; then
        systemctl start "${SERVICE_NAME}.service" && ok "Сервис запущен"
        return 0
    fi
    if [[ "$USE_MANUAL_START" != "true" ]]; then
        die "systemd-сервис не установлен, а ручной запуск выключен (USE_MANUAL_START=false). Запустите: ./manage.sh install"
    fi
    if external_pid >/dev/null; then
        warn "Бот уже запущен (PID $(external_pid)) — не запускаю второй"
        return 0
    fi
    local log_file
    log_file=$(resolve_log_file)
    mkdir -p "$(dirname "$log_file")"
    ( cd "$SCRIPT_DIR" && exec nohup "$VENV_DIR/bin/python" $START_TARGET >> "$log_file" 2>&1 ) &
    local bgpid=$!
    echo "$bgpid" > "$PID_FILE"
    sleep 1
    if kill -0 "$bgpid" 2>/dev/null; then
        ok "Бот запущен вручную (PID ${bgpid})"
    else
        rm -f "$PID_FILE"
        fail "Бот не запустился (PID ${bgpid} завершился) — смотрите: ./manage.sh logs"
        return 1
    fi
}

cmd_start() {
    do_start
    wait_health
}

cmd_stop() { do_stop; }

cmd_restart() {
    do_stop || true
    do_start
    wait_health
}

cmd_status() {
    echo "${C_INFO}=== Статус ${BOT_TITLE} (${INSTANCE}) ===${C_OFF}"
    if service_exists; then
        if service_active; then
            ok "systemd: активен"
        else
            fail "systemd: неактивен"
        fi
        systemctl status "${SERVICE_NAME}.service" --no-pager -l | tail -n +1 || true
    elif [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
        ok "Процесс вручную: PID $(cat "$PID_FILE")"
    elif external_pid >/dev/null; then
        ok "Процесс (внешний): PID $(external_pid)"
    else
        warn "Бот не запущен"
    fi

    if [[ "$USE_WEBAPP_HEALTH" == "true" ]]; then
        local port
        port=$(get_port)
        if [[ "$port" == "0" ]]; then
            dim "Веб-сервер отключён (${WEBAPP_PORT_KEY}=0)"
        elif curl -sf "http://localhost:${port}${HEALTH_PATH}" >/dev/null 2>&1; then
            ok "Веб ${HEALTH_PATH}: отвечает (порт ${port})"
        else
            warn "Веб ${HEALTH_PATH}: нет ответа (порт ${port})"
        fi
    fi
}

cmd_logs() {
    local log_file
    log_file=$(resolve_log_file)
    if service_exists && service_active; then
        journalctl -u "${SERVICE_NAME}.service" -f --no-pager -n 50
    elif [[ -f "$log_file" ]]; then
        tail -f "$log_file"
    else
        die "Логов ещё нет"
    fi
}

# --- update -------------------------------------------------------------------
cmd_update() {
    info "Обновление ${BOT_TITLE} из GitHub"

    if ! git -C "$SCRIPT_DIR" diff --quiet 2>/dev/null || ! git -C "$SCRIPT_DIR" diff --cached --quiet 2>/dev/null; then
        die "Локальные изменения в git — закоммитьте или сделайте git stash перед обновлением"
    fi
    local untracked exclude_re="" d
    for d in $EXTRA_DIRS; do
        exclude_re="${exclude_re:+$exclude_re|}^${d}/"
    done
    if [[ -n "$exclude_re" ]]; then
        untracked=$(git -C "$SCRIPT_DIR" ls-files --others --exclude-standard | grep -vE "(${exclude_re})" || true)
    else
        untracked=$(git -C "$SCRIPT_DIR" ls-files --others --exclude-standard || true)
    fi
    if [[ -n "$untracked" ]]; then
        warn "Незакоммиченные файлы (обновятся только отслеживаемые):"
        dim "$untracked"
        confirm "Продолжить?" n || exit 1
    fi

    info "Получаю изменения..."
    git -C "$SCRIPT_DIR" fetch origin || die "git fetch не удался — проверьте сеть"
    local current ahead remote_branch
    current=$(git -C "$SCRIPT_DIR" rev-parse HEAD)
    remote_branch=$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || echo "origin/main")
    ahead=$(git -C "$SCRIPT_DIR" rev-list --count "${current}..${remote_branch}" 2>/dev/null || echo "?")
    if [[ "$ahead" == "0" ]]; then
        ok "Уже актуальная версия"
        return 0
    fi
    dim "Доступно новых коммитов: ${ahead}"

    cmd_backup

    local deps_snapshot="${SCRIPT_DIR}/.requirements.before"
    local have_snapshot=false
    if [[ -x "$VENV_DIR/bin/pip" ]]; then
        if "$VENV_DIR/bin/pip" freeze > "$deps_snapshot" 2>/dev/null; then
            have_snapshot=true
            dim "Снимок зависимостей: ${deps_snapshot}"
        else
            warn "Не удалось сохранить снимок зависимостей — откат затронет только код"
        fi
    fi

    info "Загружаю новую версию..."
    git -C "$SCRIPT_DIR" pull --ff-only origin || die "git pull не удался. Бэкап в ${BACKUP_DIR}"
    if [[ -d "$VENV_DIR" && -f "${SCRIPT_DIR}/${REQUIREMENTS}" ]]; then
        "$VENV_DIR/bin/pip" install --quiet -r "${SCRIPT_DIR}/${REQUIREMENTS}" \
            || warn "Не удалось обновить зависимости — проверьте вручную"
    fi

    local was_running=false
    service_running && was_running=true
    if [[ "$was_running" != "true" ]]; then
        info "Бот не был запущен — только обновляю код, без запуска"
        git -C "$SCRIPT_DIR" log --oneline "${current}..HEAD" | head -20
        rm -f "$deps_snapshot"
        ok "Обновление завершено"
        return 0
    fi
    do_stop || true
    do_start || true

    if [[ "$USE_WEBAPP_HEALTH" == "true" ]]; then
        info "Жду ответа ${HEALTH_PATH} (до ${HEALTH_TIMEOUT}с)..."
    fi
    if health_check "$(get_port)"; then
        echo
        ok "Обновление успешно! Новые коммиты:"
        git -C "$SCRIPT_DIR" log --oneline "${current}..HEAD" | head -20
        rm -f "$deps_snapshot"
        return 0
    fi

    echo
    fail "Бот не поднялся после обновления — откатываюсь"
    do_stop || true
    git -C "$SCRIPT_DIR" reset --hard "$current" || die "Не удалось откатить git!"
    warn "Откат к коммиту $(git -C "$SCRIPT_DIR" rev-parse --short "$current")"
    if [[ "$have_snapshot" == "true" && -f "$deps_snapshot" ]]; then
        if "$VENV_DIR/bin/pip" install --quiet -r "$deps_snapshot" 2>/dev/null; then
            warn "Зависимости восстановлены из снимка"
            rm -f "$deps_snapshot"
        else
            warn "Не удалось восстановить зависимости из снимка — проверьте вручную: pip install -r ${deps_snapshot}"
        fi
    fi
    info "Данные можно восстановить из бэкапа: ./manage.sh restore (автоматически не трогаю)"
    do_start || true
    if health_check "$(get_port)"; then
        warn "Откат успешен, бот работает на старой версии"
    else
        fail "Бот не поднялся даже после отката — смотрите логи: ./manage.sh logs"
    fi
    exit 1
}

# --- backup / restore ---------------------------------------------------------
create_backup_archive() {
    # create_backup_archive <target.tar.gz>
    # 0 — успех; 2 — нечего бэкапить; 1 — ошибка.
    local target="$1"
    local staging
    staging=$(mktemp -d "${BACKUP_DIR}/.staging-XXXXXX") || { warn "Не удалось создать временный каталог"; return 1; }

    if [[ -f "$ENV_FILE" ]]; then
        cp -f "$ENV_FILE" "${staging}/.env" 2>/dev/null || true
    fi

    if [[ "$USE_DB_BACKUP" == "true" ]]; then
        local db_file=""
        db_file=$(get_db_file 2>/dev/null || true)
        if [[ -n "$db_file" && -f "$db_file" ]]; then
            local db_name have_db=false
            db_name=$(basename "$db_file")
            if command -v sqlite3 >/dev/null 2>&1; then
                if sqlite3 "$db_file" ".backup '${staging}/${db_name}'" 2>/dev/null; then
                    have_db=true
                else
                    warn "sqlite3 .backup не удался — копирую файл напрямую"
                    rm -f "${staging}/${db_name}"
                fi
            fi
            if [[ "$have_db" != "true" ]]; then
                local was_running=false
                service_running && was_running=true
                do_stop || true
                if ! cp -f "$db_file" "${staging}/${db_name}"; then
                    warn "Не удалось скопировать БД"
                    if [[ "$was_running" == "true" ]]; then
                        do_start || true
                    fi
                    rm -rf "$staging"; return 1
                fi
                if [[ -f "${db_file}-wal" ]]; then
                    cp -f "${db_file}-wal" "${staging}/${db_name}-wal" 2>/dev/null || true
                fi
                if [[ -f "${db_file}-shm" ]]; then
                    cp -f "${db_file}-shm" "${staging}/${db_name}-shm" 2>/dev/null || true
                fi
                if [[ "$was_running" == "true" ]]; then
                    do_start || true
                fi
            fi
        fi
    fi

    local p parent
    for p in $BACKUP_PATHS; do
        [[ -e "${SCRIPT_DIR}/${p}" ]] || continue
        parent="$(dirname "$p")"
        [[ "$parent" != "." ]] && mkdir -p "${staging}/${parent}"
        if ! cp -a "${SCRIPT_DIR}/${p}" "${staging}/${p}" 2>/dev/null; then
            warn "Не удалось скопировать ${p} в бэкап"
        fi
    done

    if ! find "$staging" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
        rm -rf "$staging"
        return 2
    fi

    if ! tar -czf "$target" -C "$staging" .; then
        rm -rf "$staging"; rm -f "$target"
        return 1
    fi
    rm -rf "$staging"
    chmod 600 "$target" 2>/dev/null || true
    return 0
}

cmd_backup() {
    mkdir -p "$BACKUP_DIR"
    local target
    target="${BACKUP_DIR}/bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    local rc=0
    create_backup_archive "$target" || rc=$?
    case "$rc" in
        0) ok "Бэкап: ${target} ($(du -h "$target" 2>/dev/null | cut -f1))" ;;
        2) warn "Нет данных для бэкапа (БД, .env, ${BACKUP_PATHS} отсутствуют)"; return 0 ;;
        *) die "Не удалось создать бэкап" ;;
    esac

    local old
    old=$(find "$BACKUP_DIR" -name 'bot-backup-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | tail -n +$((BACKUP_KEEP + 1)) | cut -d' ' -f2- || true)
    if [[ -n "$old" ]]; then
        dim "Удаляю старые бэкапы: $(wc -l <<< "$old") шт."
        while IFS= read -r f; do rm -f "$f"; done <<< "$old"
    fi
}

cmd_restore() {
    local latest
    latest=$(find "$BACKUP_DIR" -name 'bot-backup-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)
    [[ -n "$latest" ]] || die "Бэкапов нет в ${BACKUP_DIR}"

    confirm "Восстановить ${latest}? Бот будет остановлен." n || exit 0
    do_stop || true

    info "Сохраняю текущее состояние перед восстановлением..."
    local safety
    safety="${BACKUP_DIR}/pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz"
    mkdir -p "$BACKUP_DIR" 2>/dev/null || true
    if create_backup_archive "$safety"; then
        ok "Страховочный бэкап: ${safety}"
    else
        rm -f "$safety" 2>/dev/null || true
        warn "Не удалось создать страховочный бэкап — продолжаю восстановление"
    fi

    local tmp
    tmp=$(mktemp -d "${BACKUP_DIR}/.restore-XXXXXX") || die "Не удалось создать временный каталог"
    tar -xzf "$latest" -C "$tmp" || { rm -rf "$tmp"; die "Не удалось распаковать бэкап"; }

    if [[ -f "${tmp}/.env" ]]; then
        cp -f "${tmp}/.env" "$ENV_FILE" 2>/dev/null || true
    fi

    if [[ "$USE_DB_BACKUP" == "true" ]]; then
        local db_file=""
        db_file=$(get_db_file 2>/dev/null || true)
        if [[ -n "$db_file" ]]; then
            local db_name
            db_name=$(basename "$db_file")
            if [[ -f "${tmp}/${db_name}" ]]; then
                mkdir -p "$(dirname "$db_file")"
                rm -f "${db_file}-wal" "${db_file}-shm"
                cp -f "${tmp}/${db_name}" "$db_file" || warn "Не удалось восстановить БД"
                if [[ -f "${tmp}/${db_name}-wal" ]]; then
                    cp -f "${tmp}/${db_name}-wal" "${db_file}-wal" 2>/dev/null || true
                fi
                if [[ -f "${tmp}/${db_name}-shm" ]]; then
                    cp -f "${tmp}/${db_name}-shm" "${db_file}-shm" 2>/dev/null || true
                fi
            fi
        fi
    fi

    local p
    for p in $BACKUP_PATHS; do
        [[ -e "${tmp}/${p}" ]] || continue
        mkdir -p "$(dirname "${SCRIPT_DIR}/${p}")" 2>/dev/null || true
        rm -rf "${SCRIPT_DIR:?}/${p}"
        cp -a "${tmp}/${p}" "${SCRIPT_DIR}/${p}" 2>/dev/null || warn "Не удалось восстановить ${p}"
    done

    rm -rf "$tmp"
    ok "Восстановлено из $(basename "$latest")"
    do_start || return 1
    wait_health
    return 0
}

# --- doctor -------------------------------------------------------------------
cmd_doctor() {
    echo "${C_INFO}=== Диагностика ${BOT_TITLE} (${INSTANCE}) ===${C_OFF}"
    local errors=0

    if [[ -d "$VENV_DIR" ]] && [[ -x "$VENV_DIR/bin/python" ]]; then
        ok "venv: $("$VENV_DIR"/bin/python --version 2>&1)"
    else
        fail "venv не найден — запустите: ./manage.sh install"
        errors=$((errors + 1))
    fi

    if [[ -x "$VENV_DIR/bin/python" && -n "$DOCTOR_IMPORTS" ]]; then
        local missing="" m
        for m in $DOCTOR_IMPORTS; do
            "$VENV_DIR/bin/python" -c "import ${m}" 2>/dev/null || missing="${missing:+$missing }${m}"
        done
        if [[ -z "$missing" ]]; then
            ok "Зависимости: ${DOCTOR_IMPORTS} — установлены"
        else
            fail "Не импортируются модули: ${missing} — запустите: ./manage.sh install"
            errors=$((errors + 1))
        fi
    fi

    if [[ -f "$ENV_FILE" ]]; then
        ok "${ENV_FILE_NAME}: найден"
        local token
        token=$(env_get "$TOKEN_ENV_KEY")
        if [[ -z "$token" ]]; then
            fail "${TOKEN_ENV_KEY}: не задан"
            errors=$((errors + 1))
        elif [[ -n "$TOKEN_PLACEHOLDER" && "$token" == *"$TOKEN_PLACEHOLDER"* ]]; then
            fail "${TOKEN_ENV_KEY}: это заглушка из ${ENV_EXAMPLE_NAME} — вставьте реальный токен"
            errors=$((errors + 1))
        else
            ok "${TOKEN_ENV_KEY}: задан"
        fi
        local key val
        for key in $REQUIRED_ENV_KEYS; do
            val=$(env_get "$key")
            if [[ -z "$val" || "$val" == "0" || "$val" == "0,0" ]]; then
                fail "${key}: не задан"
                errors=$((errors + 1))
            else
                ok "${key}: задан"
            fi
        done
    else
        fail "${ENV_FILE_NAME} не найден — cp ${ENV_EXAMPLE_NAME} ${ENV_FILE_NAME}"
        errors=$((errors + 1))
    fi

    if [[ "$USE_WEBAPP_HEALTH" == "true" && -f "$ENV_FILE" ]]; then
        local wa_host wa_port
        wa_host=$(env_get "$WEBAPP_HOST_KEY")
        wa_port=$(env_get "$WEBAPP_PORT_KEY")
        if [[ "$wa_host" == "0.0.0.0" ]]; then
            warn "${WEBAPP_HOST_KEY}=0.0.0.0 открывает порт бота в интернет; рекомендуется 127.0.0.1 + Caddy"
        fi
        if [[ "$wa_port" == "80" || "$wa_port" == "443" ]]; then
            warn "${WEBAPP_PORT_KEY}=${wa_port} занят Caddy; задайте ${WEBAPP_PORT_DEFAULT} или другой"
        fi
    fi

    local dir
    for dir in $EXTRA_DIRS; do
        if [[ -d "${SCRIPT_DIR}/${dir}" ]]; then
            ok "Директория ${dir}/: есть"
        else
            warn "Директория ${dir}/: нет (создастся при install/запуске)"
        fi
    done

    if service_active; then
        ok "systemd-сервис: активен"
    elif [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
        ok "Процесс: PID $(cat "$PID_FILE")"
    elif external_pid >/dev/null; then
        ok "Процесс (внешний): PID $(external_pid)"
    else
        warn "Бот не запущен — ./manage.sh start"
    fi

    if [[ "$USE_WEBAPP_HEALTH" == "true" ]]; then
        local port
        port=$(get_port)
        if [[ "$port" == "0" ]]; then
            dim "Веб-сервер отключён (${WEBAPP_PORT_KEY}=0)"
        elif curl -sf "http://localhost:${port}${HEALTH_PATH}" >/dev/null 2>&1; then
            ok "Веб ${HEALTH_PATH}: отвечает (порт ${port})"
        else
            warn "Веб ${HEALTH_PATH}: нет ответа (порт ${port})"
        fi

        if [[ "$USE_CADDY" == "true" ]]; then
            local domain
            domain=$(get_webapp_domain)
            if [[ -n "$domain" ]]; then
                if curl -sf "https://${domain}${HEALTH_PATH}" >/dev/null 2>&1; then
                    ok "Mini App HTTPS: https://${domain}${HEALTH_PATH} отвечает"
                elif command -v caddy >/dev/null 2>&1; then
                    warn "Mini App HTTPS: нет ответа — проверьте: ./manage.sh caddy"
                else
                    warn "Mini App HTTPS: Caddy не установлен — запустите: ./manage.sh caddy"
                fi
            fi
        fi
    fi

    echo
    if (( errors > 0 )); then
        fail "Проблем: ${errors}. Исправьте и повторите: ./manage.sh doctor"
        exit 1
    else
        ok "Все проверки пройдены"
    fi
}

# --- caddy (TLS reverse proxy) -------------------------------------------------
install_caddy() {
    command -v caddy >/dev/null 2>&1 && return 0
    info "Устанавливаю Caddy..."
    local pm
    pm=$(system_pm) || die "Пакетный менеджер не найден — установите Caddy вручную: https://caddyserver.com/docs/install"
    case "$pm" in
        apt-get)
            install_pkgs debian-keyring debian-archive-keyring apt-transport-https curl
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
                | run_root gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
                | run_root tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
            run_root apt-get update -qq
            run_root apt-get install -y -qq caddy
            ;;
        dnf)
            run_root dnf install -y -q 'dnf-command(copr)'
            run_root dnf copr enable -y @caddy/caddy
            run_root dnf install -y -q caddy
            ;;
        yum)
            run_root yum install -y -q yum-plugin-copr
            run_root yum copr enable -y @caddy/caddy
            run_root yum install -y -q caddy
            ;;
        apk)
            run_root apk add --quiet caddy
            ;;
    esac
    command -v caddy >/dev/null 2>&1 || die "Caddy не установился — поставьте вручную: https://caddyserver.com/docs/install"
    ok "Caddy установлен: $(caddy version 2>/dev/null | head -1)"
}

port_in_use() {
    # True если TCP-порт уже кем-то слушается (Caddy занимает 80/443 — это норма)
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q . && return 0
    elif command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 && return 0
    fi
    return 1
}

remove_legacy_caddy_dropin() {
    # Старый manage.sh задавал домен/порт через systemd drop-in для Caddy.
    local dropin="/etc/systemd/system/caddy.service.d/webapp.conf"
    [[ -f "$dropin" ]] || return 0
    run_root rm -f "$dropin"
    if systemd_available; then
        run_root systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    dim "Удалён устаревший drop-in ${dropin}"
}

ensure_main_caddyfile() {
    # Базовый /etc/caddy/Caddyfile держит только импорт фрагментов ботов.
    # Создаём, если нет; дописываем import, если отсутствует; чужое не затираем.
    run_root mkdir -p "${CADDY_DIR}/conf.d"

    # shellcheck disable=SC2016  # литеральный паттерн, не раскрытие переменной
    if [[ -f "$CADDY_MAIN" ]] && grep -qF '{$WEBAPP_DOMAIN' "$CADDY_MAIN" 2>/dev/null; then
        info "Мигрирую ${CADDY_MAIN}: убираю vhost с плейсхолдерами -> import conf.d/*.caddy"
        printf '# Управляется manage.sh: базовый конфиг + фрагменты ботов в conf.d/\nimport %s/conf.d/*.caddy\n' "$CADDY_DIR" \
            | run_root tee "$CADDY_MAIN" >/dev/null
        remove_legacy_caddy_dropin
        ok "Обновлён ${CADDY_MAIN}"
    elif [[ ! -f "$CADDY_MAIN" ]]; then
        printf '# Управляется manage.sh: базовый конфиг + фрагменты ботов в conf.d/\nimport %s/conf.d/*.caddy\n' "$CADDY_DIR" \
            | run_root tee "$CADDY_MAIN" >/dev/null
        ok "Создан ${CADDY_MAIN} (импорт conf.d/*.caddy)"
    elif ! grep -qE "^import[[:space:]]+${CADDY_DIR}/conf\.d/\*\.caddy" "$CADDY_MAIN" 2>/dev/null; then
        printf '\n# Добавлено manage.sh: фрагменты ботов\nimport %s/conf.d/*.caddy\n' "$CADDY_DIR" \
            | run_root tee -a "$CADDY_MAIN" >/dev/null
        warn "В ${CADDY_MAIN} добавлен import conf.d/*.caddy (существующий конфиг сохранён)"
    fi
    run_root mkdir -p "$(dirname "$CADDY_SITE")"
}

cmd_caddy() {
    if [[ "$USE_CADDY" != "true" ]]; then
        info "Caddy выключен в BOT CONFIG (USE_CADDY=false) — настраивать нечего"
        return 0
    fi
    local domain port
    domain=$(get_webapp_domain)
    port=$(get_port)

    if [[ -z "$domain" ]]; then
        die "${WEBAPP_URL_KEY} не задан в ${ENV_FILE}. Укажите публичный HTTPS-URL, например:
  ${WEBAPP_URL_KEY}=https://bot.example.com
Затем повторите: ./manage.sh caddy"
    fi
    if [[ "$port" == "0" ]]; then
        die "${WEBAPP_PORT_KEY}=0 — веб-сервер бота отключён, Caddy проксировать некуда"
    fi
    if [[ "$port" == "80" || "$port" == "443" ]]; then
        die "${WEBAPP_PORT_KEY}=${port} — этот порт нужен Caddy для HTTPS и редиректов.
Смените порт бота (например, ${WEBAPP_PORT_DEFAULT}) в ${ENV_FILE} и перезапустите: ./manage.sh restart"
    fi

    info "Настройка Caddy для ${INSTANCE}: ${domain} -> 127.0.0.1:${port}"
    info "Для выпуска сертификата Let's Encrypt нужны открытые порты 80 и 443 и DNS-запись на этот сервер."

    install_caddy
    ensure_main_caddyfile

    printf '%s {\n\treverse_proxy 127.0.0.1:%s\n}\n' "$domain" "$port" \
        | run_root tee "$CADDY_SITE" >/dev/null
    ok "Фрагмент: ${CADDY_SITE} (${domain} -> 127.0.0.1:${port})"

    run_root caddy validate --config "$CADDY_MAIN" --adapter caddyfile \
        || die "Конфиг Caddy некорректен — проверьте ${CADDY_MAIN} и ${CADDY_SITE}"

    if systemd_available; then
        run_root systemctl enable --now caddy >/dev/null 2>&1 || true
        run_root systemctl reload caddy >/dev/null 2>&1 || run_root systemctl restart caddy
        ok "Caddy перезапущен (systemd)"
    else
        warn "systemd не найден — запустите Caddy вручную: caddy run --config ${CADDY_MAIN}"
    fi

    info "Жду ответа https://${domain}${HEALTH_PATH} (до ${HEALTH_TIMEOUT}с)..."
    local waited=0
    while (( waited < HEALTH_TIMEOUT )); do
        if curl -sf "https://${domain}${HEALTH_PATH}" >/dev/null 2>&1; then
            echo
            ok "HTTPS работает: https://${domain}${HEALTH_PATH}"
            dim "Проверьте ${WEBAPP_URL_KEY} в ${ENV_FILE}: должен быть https://${domain}"
            return 0
        fi
        sleep 2; waited=$((waited + 2))
    done
    echo
    warn "HTTPS не ответил за ${HEALTH_TIMEOUT}с. Проверьте:"
    dim "  • DNS ${domain} указывает на IP этого сервера"
    dim "  • порты 80/443 открыты (firewall)"
    dim "  • фрагмент бота: ${CADDY_SITE}"
    dim "  • логи Caddy: journalctl -u caddy -n 50 --no-pager"
    return 1
}

# --- uninstall -----------------------------------------------------------------
cmd_uninstall() {
    echo "${C_WARN}Внимание: это остановит бота${C_OFF}"
    confirm "Продолжить удаление?" n || exit 0

    do_stop || true
    if service_exists; then
        systemctl disable "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
        rm -f "$SERVICE_FILE" && systemctl daemon-reload
        ok "systemd-сервис удалён"
    fi

    if [[ -f "$CADDY_SITE" ]]; then
        if confirm "Удалить Caddy-фрагмент ${CADDY_SITE} для ${INSTANCE}?" y; then
            run_root rm -f "$CADDY_SITE"
            if systemd_available && command -v caddy >/dev/null 2>&1; then
                run_root systemctl reload caddy >/dev/null 2>&1 || true
            fi
            ok "Caddy-фрагмент удалён (${INSTANCE})"
        else
            info "Caddy-фрагмент оставлен: ${CADDY_SITE}"
        fi
    fi

    if confirm "Удалить виртуальное окружение (.venv)?" n; then
        rm -rf "$VENV_DIR" && ok ".venv удалён"
    fi

    if confirm "Удалить данные и бэкапы (${DATA_PATHS} ${ENV_FILE_NAME})?" n; then
        local p
        for p in $DATA_PATHS; do
            rm -rf "${SCRIPT_DIR:?}/${p}"
        done
        if [[ "$USE_DB_BACKUP" == "true" ]]; then
            local db_file=""
            db_file=$(get_db_file 2>/dev/null || true)
            if [[ -n "$db_file" ]]; then
                rm -f "$db_file" "${db_file}-wal" "${db_file}-shm"
            fi
        fi
        rm -f "$ENV_FILE"
        rm -rf "$BACKUP_DIR"
        ok "Данные удалены"
    else
        info "Данные сохранены"
    fi
    ok "Удаление завершено. Код бота в ${SCRIPT_DIR} не тронут."
}

# --- usage ---------------------------------------------------------------------
cmd_help() {
    cat <<EOF
${BOT_TITLE} — управление ботом

Использование: ./manage.sh [--instance ИМЯ] [--no-color] <команда>

Быстрая установка с нуля (клонирует в ${INSTALL_DIR_DEFAULT}):
  curl -fsSL <URL_С_ЭТИМ_manage.sh> | bash -s -- install

Несколько ботов на одном сервере:
  Каждый бот — отдельный каталог со своим ${ENV_FILE_NAME}. Имя инстанса берётся
  из имени каталога (или флагами --instance / ${MANAGE_INSTANCE_ENV}) и разводит
  systemd-юнит (${SERVICE_BASE}-<instance>), PID-файл и фрагмент Caddy
  (/etc/caddy/conf.d/<instance>.caddy). Caddy ставится один, слушает 80/443,
  а боты — на уникальных портах и ${WEBAPP_HOST_KEY}=127.0.0.1.

Команды:
  install     Полная установка: venv, зависимости, .env, systemd (интерактивно).
              Без репозитория рядом (curl|bash) — клонирует в ${INSTALL_DIR_DEFAULT}
  update      Обновление с GitHub + бэкап + откат при сбое
  start       Запуск бота
  stop        Остановка
  restart     Перезапуск
  status      Статус сервиса + health-check
  logs        Логи в реальном времени (Ctrl+C для выхода)
  backup      Бэкап данных и ${ENV_FILE_NAME} в backups/ (хранит последние ${BACKUP_KEEP})
  restore     Восстановление из последнего бэкапа
  doctor      Диагностика: venv, зависимости, .env, сервис, ${HEALTH_PATH}
  caddy       HTTPS для Mini App: ставит Caddy, берёт домен из ${WEBAPP_URL_KEY}
  uninstall   Остановка + удаление сервиса и Caddy-фрагмента (с вопросами)
  help        Эта справка

Флаги и переменные:
  --instance ИМЯ          Имя инстанса (по умолчанию — имя каталога)
  ${MANAGE_INSTANCE_ENV}  То же через переменную окружения
  --no-color              Отключить цвета
EOF
}

# --- bootstrap (curl | bash) ----------------------------------------------------
cmd_bootstrap_install() {
    info "Скрипт запущен вне репозитория — устанавливаю с GitHub"

    local install_dir="$INSTALL_DIR_DEFAULT"
    local reply=""
    if [[ -n "$INPUT_FD" ]]; then
        read -r -p "Каталог установки [${INSTALL_DIR_DEFAULT}]: " reply < "$INPUT_FD" || reply=""
    fi
    reply="${reply:-$INSTALL_DIR_DEFAULT}"
    install_dir="$reply"

    if [[ -d "$install_dir/.git" ]]; then
        info "Каталог ${install_dir} уже содержит репозиторий — обновляю код"
        ensure_cmd git git
        git -C "$install_dir" fetch origin 2>/dev/null || die "Не удалось обновить ${install_dir} из GitHub"
        git -C "$install_dir" reset --hard "$(git -C "$install_dir" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || echo origin/main)" >/dev/null
    elif [[ -e "$install_dir" ]]; then
        die "Каталог ${install_dir} занят — выберите другой путь установки"
    else
        info "Клонирую ${REPO_URL} -> ${install_dir}"
        ensure_cmd git git
        mkdir -p "$(dirname "$install_dir")"
        git clone "$REPO_URL" "$install_dir" || die "Не удалось клонировать репозиторий"
    fi

    if [[ -n "${NO_COLOR:-}" ]]; then
        exec bash "$install_dir/manage.sh" --no-color install
    else
        exec bash "$install_dir/manage.sh" install
    fi
}

# --- main ----------------------------------------------------------------------
main() {
    local args=() no_color=false instance="" arg
    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --no-color)   no_color=true; shift ;;
            --instance)   [[ -n "${2:-}" ]] || die "--instance требует имя"; instance="$2"; shift 2 ;;
            --instance=*) instance="${arg#*=}"; shift ;;
            *)            args+=("$arg"); shift ;;
        esac
    done
    if [[ "$no_color" == "true" ]]; then
        set_colors off
        export NO_COLOR=1
    fi
    [[ -n "$instance" ]] && init_instance "$instance"
    if [[ ${#args[@]} -gt 0 ]]; then
        set -- "${args[@]}"
    else
        set --
    fi
    local cmd="${1:-help}"
    shift 2>/dev/null || true

    if ! is_repo; then
        case "$cmd" in
            install) cmd_bootstrap_install ;;
            help|-h|--help|"") cmd_help ;;
            *) die "Эта команда работает только внутри установленного репозитория.
Быстрая установка с нуля: curl -fsSL <URL_С_ЭТИМ_manage.sh> | bash -s -- install" ;;
        esac
        return
    fi

    case "$cmd" in
        install)   cmd_install ;;
        update)    cmd_update ;;
        start)     cmd_start ;;
        stop)      cmd_stop ;;
        restart)   cmd_restart ;;
        status)    cmd_status ;;
        logs)      cmd_logs ;;
        backup)    cmd_backup ;;
        restore)   cmd_restore ;;
        doctor)    cmd_doctor ;;
        caddy)     cmd_caddy ;;
        uninstall) cmd_uninstall ;;
        help|-h|--help|"") cmd_help ;;
        *) die "Неизвестная команда: '${cmd}'. Смотрите: ./manage.sh help" ;;
    esac
}

main "$@"
