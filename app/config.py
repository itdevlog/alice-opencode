import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SYSTEM_PROMPT = (
    "Ты голосовой ассистент Алисы. Отвечай по-русски, кратко и по делу. "
    "Пиши простыми предложениями без markdown, списков, ссылок и эмодзи: "
    "твой ответ будет произнесён вслух. Если не знаешь ответа — честно скажи об этом."
)


@dataclass(frozen=True)
class Settings:
    opencode_api_key: str
    opencode_base_url: str
    model: str
    db_path: str
    skill_id: str | None
    request_deadline_seconds: float
    max_tokens: int
    history_limit: int
    system_prompt: str


def load_settings() -> Settings:
    return Settings(
        opencode_api_key=os.getenv("OPENCODE_API_KEY", ""),
        opencode_base_url=os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1"),
        model=os.getenv("MODEL", "deepseek-v4.1-flash"),
        db_path=os.getenv("DB_PATH", "data/alice.db"),
        skill_id=os.getenv("SKILL_ID") or None,
        request_deadline_seconds=float(os.getenv("REQUEST_DEADLINE_SECONDS", "3.5")),
        max_tokens=int(os.getenv("MAX_TOKENS", "400")),
        history_limit=int(os.getenv("HISTORY_LIMIT", "10")),
        system_prompt=os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    )
