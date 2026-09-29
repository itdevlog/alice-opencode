import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.commands import ERROR_TEXT
from app.config import Settings
from app.storage import Storage

logger = logging.getLogger(__name__)

# OpenCode Go требует идентифицировать клиента собственным User-Agent (не именем
# HTTP-библиотеки) и передавать стабильный ID диалога в x-opencode-session.
USER_AGENT = "alice-opencode-skill/1.0"

PARTIAL_MAX_CHARS = 200
PARTIAL_MIN_CHARS = 40


@dataclass
class AnswerResult:
    text: str | None
    is_pending: bool = False


def extract_delta(line: str) -> str | None:
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:"):].strip()
    if not data or data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = payload.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if not content:
        return None
    return content


def usable_partial(text: str) -> bool:
    if len(text) >= PARTIAL_MAX_CHARS:
        return True
    return len(text) >= PARTIAL_MIN_CHARS and text[-1] in ".!?…"


def chat_completions_url(base: str) -> str:
    base = base.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError(
            "OPENCODE_BASE_URL должен начинаться с http:// или https://, "
            f"сейчас: {base!r}"
        )
    if base.endswith("/chat/completions"):
        return base
    lowered = base.lower()
    if lowered in ("https://opencode.ai", "http://opencode.ai"):
        return f"{base}/zen/go/v1/chat/completions"
    if lowered.endswith("/zen/go"):
        return f"{base}/v1/chat/completions"
    return f"{base}/chat/completions"


class ChatTransport(Protocol):
    def stream(
        self, messages: list[dict[str, str]], session_id: str
    ) -> AsyncIterator[str]: ...


class OpenCodeGoTransport:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))

    def _url(self) -> str:
        return chat_completions_url(self._settings.opencode_base_url)

    async def stream(
        self, messages: list[dict[str, str]], session_id: str
    ) -> AsyncIterator[str]:
        url = self._url()
        payload = {
            "model": self._settings.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._settings.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.opencode_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": USER_AGENT,
            "x-opencode-session": session_id,
        }
        async with self._client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                raise RuntimeError(
                    f"OpenCode Go HTTP {response.status_code} for {url}: {body[:2000]}"
                )
            async for line in response.aiter_lines():
                delta = extract_delta(line)
                if delta is not None:
                    yield delta

    async def aclose(self) -> None:
        await self._client.aclose()


class LlmService:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        transport: ChatTransport | None = None,
    ):
        self._settings = settings
        self._storage = storage
        self._transport = transport or OpenCodeGoTransport(settings)
        self._tasks: set[asyncio.Task] = set()

    async def answer(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        deadline: float | None = None,
    ) -> AnswerResult:
        timeout = self._settings.request_deadline_seconds if deadline is None else deadline
        parts: list[str] = []
        task: asyncio.Task = asyncio.create_task(self._collect(messages, user_id, parts))
        self._register(task)
        try:
            text = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            snapshot = "".join(parts)
            partial = snapshot.strip()
            question = messages[-1]["content"] if messages else ""
            self._storage.save_pending(user_id, question)
            if usable_partial(partial):
                self._spawn_remainder(user_id, task, len(snapshot))
                return AnswerResult(text=partial, is_pending=False)
            self._spawn_background(user_id, task)
            return AnswerResult(text=None, is_pending=True)
        except Exception:
            logger.exception("LLM request failed")
            return AnswerResult(text=ERROR_TEXT)
        text = text.strip()
        if not text:
            return AnswerResult(text=ERROR_TEXT)
        return AnswerResult(text=text)

    async def _collect(
        self, messages: list[dict[str, str]], session_id: str, parts: list[str]
    ) -> str:
        async for delta in self._transport.stream(messages, session_id):
            parts.append(delta)
        return "".join(parts)

    def _spawn_background(self, user_id: str, task: asyncio.Task) -> None:
        async def finish() -> None:
            try:
                text = (await task).strip() or ERROR_TEXT
            except Exception:
                logger.exception("Background LLM request failed")
                text = ERROR_TEXT
            self._storage.set_pending_answer(user_id, text)

        self._register(asyncio.create_task(finish()))

    def _spawn_remainder(self, user_id: str, task: asyncio.Task, prefix_len: int) -> None:
        async def finish() -> None:
            try:
                full = await task
            except Exception:
                logger.exception("Background LLM request failed")
                self._storage.pop_pending(user_id)
                return
            remainder = full[prefix_len:].strip()
            if remainder:
                self._storage.set_pending_answer(user_id, remainder)
            else:
                self._storage.pop_pending(user_id)

        self._register(asyncio.create_task(finish()))

    def _register(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_background(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        aclose = getattr(self._transport, "aclose", None)
        if aclose is not None:
            await aclose()
