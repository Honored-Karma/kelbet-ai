from kelbet.observability import JsonFormatter, redact_mapping


def test_redact_mapping_strips_secrets() -> None:
    data = {
        "prompt": "secret user text",
        "authorization": "Bearer abc.def",
        "provider": "mock",
        "nested": {"access_token": "xyz", "ok": 1},
    }
    redacted = redact_mapping(data)
    assert redacted["prompt"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["provider"] == "mock"
    assert redacted["nested"]["access_token"] == "[REDACTED]"
    assert redacted["nested"]["ok"] == 1


def test_json_formatter_includes_correlation() -> None:
    import logging

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "cid-1"
    record.provider = "mock"
    line = JsonFormatter().format(record)
    assert '"correlation_id": "cid-1"' in line
    assert '"provider": "mock"' in line
    assert '"message": "hello"' in line
