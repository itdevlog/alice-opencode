from enum import StrEnum

GREETING_TEXT = "Привет! Я умею отвечать на вопросы через DeepSeek. Спроси что-нибудь."
HELP_TEXT = (
    "Просто задай вопрос — отвечу, а ещё расскажу погоду: спроси «погода в Москве». "
    "Команды: «повтори» — повторить ответ; «короче» или «подробнее» — длина ответов; "
    "«меня зовут …», «мой город …», «запомни: …» — запомнить о тебе; "
    "«что ты обо мне знаешь»; «очисти историю»; «выход»."
)
CLEAR_TEXT = "Хорошо, я забыл историю нашего разговора."
EXIT_TEXT = "До встречи!"
WAIT_TEXT = "Ещё пару секунд, досчитываю ответ."
PENDING_HINT = "Секунду, я подумаю. Скажи «дальше», когда будет готово."
NO_PENDING_TEXT = "Сейчас нечего продолжать. Просто задай вопрос."
NOTHING_TO_REPEAT_TEXT = "Мне нечего повторять — я ещё ничего не отвечал."
ERROR_TEXT = "Не получилось получить ответ от сервиса. Попробуй ещё раз."

STYLE_SET_TEXT = {
    "short": "Хорошо, буду отвечать кратко.",
    "detailed": "Хорошо, буду отвечать подробнее.",
    "normal": "Хорошо, вернусь к обычной длине ответов.",
}


class Command(StrEnum):
    HELP = "help"
    CLEAR = "clear"
    EXIT = "exit"
    CONTINUE = "continue"
    REPEAT = "repeat"
    SHORT = "short"
    DETAILED = "detailed"
    NORMAL = "normal"


_HELP = {"помощь", "что ты умеешь", "команды", "твои команды"}
_CLEAR = {"очисти историю", "очистить историю", "забудь всё", "забудь", "сбрось историю", "сброс"}
_EXIT = {"выход", "хватит", "стоп", "пока", "до свидания", "завершить"}
_CONTINUE = {"дальше", "продолжай", "продолжить", "готово", "ну"}
_REPEAT = {"повтори", "повтори это", "повтори пожалуйста", "скажи ещё раз", "скажи еще раз"}
_SHORT = {"короче", "покороче", "кратко", "отвечай кратко", "отвечай короче"}
_DETAILED = {"подробнее", "поподробнее", "подробно", "отвечай подробно", "отвечай подробнее"}
_NORMAL = {"обычно", "нормально", "отвечай обычно", "обычный ответ"}


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
    if normalized in _REPEAT:
        return Command.REPEAT
    if normalized in _SHORT:
        return Command.SHORT
    if normalized in _DETAILED:
        return Command.DETAILED
    if normalized in _NORMAL:
        return Command.NORMAL
    return None
