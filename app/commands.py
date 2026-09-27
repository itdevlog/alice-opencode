from enum import StrEnum

GREETING_TEXT = "Привет! Я умею отвечать на вопросы через DeepSeek. Спроси что-нибудь."
HELP_TEXT = (
    "Просто задай мне вопрос, и я отвечу. "
    "Команды: «очисти историю» — забыть наш разговор, «выход» — завершить."
)
CLEAR_TEXT = "Хорошо, я забыл историю нашего разговора."
EXIT_TEXT = "До встречи!"
WAIT_TEXT = "Ещё пару секунд, досчитываю ответ."
PENDING_HINT = "Секунду, я подумаю. Скажи «дальше», когда будет готово."
NO_PENDING_TEXT = "Сейчас нечего продолжать. Просто задай вопрос."
ERROR_TEXT = "Не получилось получить ответ от сервиса. Попробуй ещё раз."


class Command(StrEnum):
    HELP = "help"
    CLEAR = "clear"
    EXIT = "exit"
    CONTINUE = "continue"


_HELP = {"помощь", "что ты умеешь", "команды", "твои команды"}
_CLEAR = {"очисти историю", "очистить историю", "забудь всё", "забудь", "сбрось историю", "сброс"}
_EXIT = {"выход", "хватит", "стоп", "пока", "до свидания", "завершить"}
_CONTINUE = {"дальше", "продолжай", "продолжить", "готово", "ну"}


def normalize(text: str) -> str:
    normalized = text.strip().lower()
    if normalized.startswith("алиса"):
        normalized = normalized[len("алиса"):]
    return normalized.strip(" \t.,!?;:")


def detect_command(text: str) -> Command | None:
    normalized = normalize(text)
    if not normalized:
        return None
    if normalized in _HELP:
        return Command.HELP
    if normalized in _CLEAR:
        return Command.CLEAR
    if normalized in _EXIT:
        return Command.EXIT
    if normalized in _CONTINUE:
        return Command.CONTINUE
    return None
