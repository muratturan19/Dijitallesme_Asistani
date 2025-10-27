"""Tests for smart OpenAI helper utilities."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.utils.smart_openai import (
    _normalize_messages_for_responses,
    call_reasoning_model,
)


def test_normalize_messages_with_plain_text():
    messages = [
        {"role": "system", "content": "hello"},
        {"role": "user", "content": "world"},
    ]

    normalized = _normalize_messages_for_responses(messages)

    assert normalized == [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "hello"},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "world"},
            ],
        },
    ]


def test_normalize_messages_with_mixed_content():
    messages = [
        {
            "role": "user",
            "content": [
                "first",
                {"type": "text", "text": "second"},
                {"text": "third"},
                {"type": "input_text", "text": "fourth"},
                {"value": 5},
                None,
            ],
            "metadata": {"foo": "bar"},
        }
    ]

    normalized = _normalize_messages_for_responses(messages)

    assert normalized == [
        {
            "role": "user",
            "metadata": {"foo": "bar"},
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
                {"type": "text", "text": "third"},
                {"type": "input_text", "text": "fourth"},
                {"type": "text", "text": "5"},
            ],
        }
    ]


def test_call_reasoning_model_uses_normalized_messages():
    class DummyResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": "ok"}

    class DummyClient:
        def __init__(self):
            self.responses = DummyResponses()

    client = DummyClient()

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]

    call_reasoning_model(
        client,
        model="gpt-test",
        messages=messages,
        reasoning_effort="medium",
    )

    assert len(client.responses.calls) == 1
    call_kwargs = client.responses.calls[0]
    assert call_kwargs["model"] == "gpt-test"
    assert call_kwargs["input"] == [
        {"role": "system", "content": [{"type": "text", "text": "sys"}]},
        {"role": "user", "content": [{"type": "text", "text": "usr"}]},
    ]

