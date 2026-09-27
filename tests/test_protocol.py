from app.protocol import build_response, parse_request


def make_payload(**overrides):
    payload = {
        "meta": {"locale": "ru-RU", "timezone": "Europe/Moscow", "interfaces": {}},
        "request": {"command": "привет", "original_utterance": "привет", "type": "SimpleUtterance"},
        "session": {
            "new": True,
            "message_id": 4,
            "session_id": "sess-1",
            "skill_id": "skill-42",
            "user": {"user_id": "user-abc"},
            "application": {"application_id": "app-xyz"},
        },
        "version": "1.0",
    }
    for key, value in overrides.items():
        payload[key] = value
    return payload


def test_parse_extracts_basic_fields():
    req = parse_request(make_payload())
    assert req.text == "привет"
    assert req.version == "1.0"
    assert req.session_id == "sess-1"
    assert req.is_new_session is True
    assert req.request_type == "SimpleUtterance"
    assert req.skill_id == "skill-42"


def test_user_id_prefers_authorized_user():
    req = parse_request(make_payload())
    assert req.user_id == "user-abc"


def test_user_id_falls_back_to_application_id():
    payload = make_payload()
    del payload["session"]["user"]
    req = parse_request(payload)
    assert req.user_id == "app-xyz"


def test_user_id_falls_back_to_legacy_session_user_id():
    payload = make_payload()
    del payload["session"]["user"]
    del payload["session"]["application"]
    payload["session"]["user_id"] = "legacy-1"
    req = parse_request(payload)
    assert req.user_id == "legacy-1"


def test_parse_falls_back_to_command_when_no_utterance():
    payload = make_payload()
    del payload["request"]["original_utterance"]
    req = parse_request(payload)
    assert req.text == "привет"


def test_build_response_echoes_version_and_session_and_sets_fields():
    req = parse_request(make_payload())
    result = build_response(req, text="Ответ", tts="Ответ", end_session=True)
    assert result["version"] == "1.0"
    assert result["session"] == req.raw["session"]
    assert result["response"] == {"text": "Ответ", "tts": "Ответ", "end_session": True}


def test_build_response_defaults_tts_to_text():
    req = parse_request(make_payload())
    result = build_response(req, text="Ответ")
    assert result["response"]["tts"] == "Ответ"
    assert result["response"]["end_session"] is False
