from app.tts import clean_for_speech


def test_removes_bold_and_italic_markers():
    assert clean_for_speech("Это **важно** и _тоже_") == "Это важно и тоже"


def test_removes_headers():
    assert clean_for_speech("## Заголовок\nтекст") == "Заголовок текст"


def test_converts_markdown_link_to_its_text():
    assert clean_for_speech("Смотри [документацию](https://example.com) тут") == (
        "Смотри документацию тут"
    )


def test_removes_bare_urls():
    assert clean_for_speech("Сайт https://example.com/page работает") == "Сайт работает"


def test_removes_code_fences_and_inline_code():
    assert clean_for_speech("Код ```python\nprint(1)\n``` и `переменная`") == (
        "Код print(1) и переменная"
    )


def test_removes_bullet_markers():
    assert clean_for_speech("- первый\n- второй") == "первый второй"


def test_removes_emoji():
    assert clean_for_speech("Привет 👋 мир 🌍") == "Привет мир"


def test_neutralizes_tts_markup_tags():
    assert clean_for_speech('Привет <speaker audio="x.opus"> мир') == "Привет мир"


def test_collapses_whitespace():
    assert clean_for_speech("много   \n\n  пробелов") == "много пробелов"


def test_truncates_to_max_chars_without_exceeding_limit():
    result = clean_for_speech("слово " * 100, max_chars=20)
    assert len(result) <= 20


def test_empty_text_returns_empty_string():
    assert clean_for_speech("") == ""
