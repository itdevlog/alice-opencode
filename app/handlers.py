from app import commands
from app.commands import Command, detect_command, normalize
from app.config import Settings
from app.llm import LlmService
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

        pending = self._storage.get_pending(user_id)
        if pending is not None:
            if pending.is_ready:
                answer = self._storage.pop_pending(user_id).answer
                self._storage.add_message(user_id, "assistant", answer)
                return self._reply(request, answer)
            return self._reply(request, commands.WAIT_TEXT)

        if command is Command.CONTINUE:
            return self._reply(request, commands.NO_PENDING_TEXT)

        history = self._storage.get_history(user_id, self._settings.history_limit)
        messages = [{"role": "system", "content": self._settings.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": raw})
        self._storage.add_message(user_id, "user", raw)

        result = await self._llm.answer(user_id, messages)
        if result.is_pending:
            return self._reply(request, commands.PENDING_HINT)
        self._storage.add_message(user_id, "assistant", result.text)
        return self._reply(request, result.text)

    def _reply(self, request: AliceRequest, text: str, end_session: bool = False) -> dict:
        speech = clean_for_speech(text)
        return build_response(request, speech, tts=speech, end_session=end_session)
