import re

MAX_SPEECH_CHARS = 1024

_CODE_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_HEADER = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_BOLD_ITALIC = re.compile(r"(\*\*|__)")
_EMPHASIS = re.compile(r"[*_~]")
_TTS_TAG = re.compile(r"<[^>]*>")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2190-\u21FF\u2B00-\u2BFF\uFE0F\u200D]"
)
_WHITESPACE = re.compile(r"\s+")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.strip()


def clean_for_speech(text: str, max_chars: int = MAX_SPEECH_CHARS) -> str:
    if not text:
        return ""

    text = _CODE_FENCE.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _BARE_URL.sub("", text)
    text = _HEADER.sub("", text)
    text = _BULLET.sub("", text)
    text = _BOLD_ITALIC.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = _TTS_TAG.sub("", text)
    text = _EMOJI.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return _truncate(text, max_chars)
