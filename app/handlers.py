from app import commands, personalization
from app.clock import datetime_note
from app.commands import Command, detect_command, normalize
from app.config import Settings
from app.llm import LlmService
from app.personalization import (
    FactCommand,
    FactKind,
    format_facts_prompt,
    parse_fact_command,
)
from app.protocol import AliceRequest, build_response
from app.storage import Storage
from app.tts import clean_for_speech


class SkillHandler:
    def __init__(self, settings: Settings, storage: Storage, llm: LlmService):
        self._settings = settings
        self._storage = storage
        self._llm = llm

    async def handle(self, request: AliceRequest) -> dict:
        user_id = request.user_id
        raw = request.text.strip()
        command = detect_command(raw)

        if not normalize(raw):
            text = commands.GREETING_TEXT if request.is_new_session else commands.HELP_TEXT
            return self._reply(request, text)

        if command is Command.HELP:
            return self._reply(request, commands.HELP_TEXT)
        if command is Command.CLEAR:
            self._storage.clear_history(user_id)
            return self._reply(request, commands.CLEAR_TEXT)
        if command is Command.EXIT:
            return self._reply(request, commands.EXIT_TEXT, end_session=True)
        if command is Command.REPEAT:
            last = self._storage.get_last_assistant(user_id)
            return self._reply(request, last or commands.NOTHING_TO_REPEAT_TEXT)

        style = {
            Command.SHORT: "short",
            Command.DETAILED: "detailed",
            Command.NORMAL: "normal",
        }.get(command)
        if style is not None:
            self._storage.set_fact(user_id, "style", style)
            return self._reply(request, commands.STYLE_SET_TEXT[style])

        fact_command = parse_fact_command(raw)
        if fact_command is not None:
            return self._handle_fact(request, user_id, fact_command)

        pending = self._storage.get_pending(user_id)
        if pending is not None:
            if pending.is_ready:
                answer = self._storage.pop_pending(user_id).answer
                self._storage.add_message(user_id, "assistant", answer)
                return self._reply(request, answer)
            return self._reply(request, commands.WAIT_TEXT)

        if command is Command.CONTINUE:
            return self._reply(request, commands.NO_PENDING_TEXT)

        timezone_name = (request.raw.get("meta") or {}).get("timezone")
        facts_prompt = format_facts_prompt(self._storage.get_facts(user_id))
        style_hint = personalization.style_hint(self._storage.get_fact(user_id, "style"))
        system_content = " ".join(
            part
            for part in (
                datetime_note(timezone_name),
                facts_prompt,
                style_hint,
                self._settings.system_prompt,
            )
            if part
        )
        history = self._storage.get_history(user_id, self._settings.history_limit)
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": raw})
        self._storage.add_message(user_id, "user", raw)

        result = await self._llm.answer(user_id, messages)
        if result.is_pending:
            return self._reply(request, commands.PENDING_HINT, tts=self._pending_tts())
        self._storage.add_message(user_id, "assistant", result.text)
        return self._reply(request, result.text)

    def _pending_tts(self) -> str:
        sound = self._settings.wait_sound
        lead = f'<speaker audio="{sound}">' if sound else "sil <[500]>"
        return f"Секунду. {lead} Я подумаю. Скажи «дальше», когда будет готово."

    def _handle_fact(
        self, request: AliceRequest, user_id: str, command: FactCommand
    ) -> dict:
        storage = self._storage
        if command.kind is FactKind.NAME:
            storage.set_fact(user_id, "name", command.value)
            return self._reply(request, personalization.NAME_SAVED.format(name=command.value))
        if command.kind is FactKind.CITY:
            storage.set_fact(user_id, "city", command.value)
            return self._reply(request, personalization.CITY_SAVED.format(city=command.value))
        if command.kind is FactKind.NOTE:
            storage.set_fact(user_id, "notes", command.value)
            return self._reply(request, personalization.NOTE_SAVED)
        if command.kind is FactKind.SHOW:
            return self._reply(request, personalization.facts_reply(storage.get_facts(user_id)))
        storage.delete_facts(user_id)
        return self._reply(request, personalization.FORGET_FACTS_TEXT)

    def _reply(
        self,
        request: AliceRequest,
        text: str,
        end_session: bool = False,
        tts: str | None = None,
    ) -> dict:
        speech = clean_for_speech(text)
        return build_response(
            request, speech, tts=tts if tts is not None else speech, end_session=end_session
        )
