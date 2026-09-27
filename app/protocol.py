from dataclasses import dataclass
from typing import Any


@dataclass
class AliceRequest:
    version: str
    text: str
    is_new_session: bool
    user_id: str
    session_id: str
    skill_id: str | None
    request_type: str
    raw: dict[str, Any]


def _resolve_user_id(session: dict[str, Any]) -> str:
    user = session.get("user") or {}
    if user.get("user_id"):
        return user["user_id"]
    application = session.get("application") or {}
    if application.get("application_id"):
        return application["application_id"]
    if session.get("user_id"):
        return session["user_id"]
    return "unknown"


def parse_request(payload: dict[str, Any]) -> AliceRequest:
    session = payload.get("session") or {}
    request = payload.get("request") or {}
    text = request.get("original_utterance") or request.get("command") or ""
    return AliceRequest(
        version=payload.get("version", "1.0"),
        text=text,
        is_new_session=bool(session.get("new", False)),
        user_id=_resolve_user_id(session),
        session_id=session.get("session_id", ""),
        skill_id=session.get("skill_id"),
        request_type=request.get("type", "SimpleUtterance"),
        raw=payload,
    )


def build_response(
    request: AliceRequest,
    text: str,
    tts: str | None = None,
    end_session: bool = False,
) -> dict[str, Any]:
    return {
        "version": request.version,
        "session": request.raw.get("session", {}),
        "response": {
            "text": text,
            "tts": tts if tts is not None else text,
            "end_session": end_session,
        },
    }
