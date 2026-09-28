import pytest

from app.commands import Command, detect_command


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("помощь", Command.HELP),
        ("Алиса, что ты умеешь?", Command.HELP),
        ("очисти историю", Command.CLEAR),
        ("Забудь всё!", Command.CLEAR),
        ("выход", Command.EXIT),
        ("Пока.", Command.EXIT),
        ("дальше", Command.CONTINUE),
        ("продолжай", Command.CONTINUE),
        ("повтори", Command.REPEAT),
        ("повтори это", Command.REPEAT),
        ("короче", Command.SHORT),
        ("отвечай кратко", Command.SHORT),
        ("подробнее", Command.DETAILED),
        ("отвечай подробно", Command.DETAILED),
        ("обычно", Command.NORMAL),
        ("расскажи анекдот", None),
        ("", None),
    ],
)
def test_detect_command(text, expected):
    assert detect_command(text) is expected
