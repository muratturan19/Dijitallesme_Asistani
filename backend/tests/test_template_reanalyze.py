from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
import app.routes.template as template_routes


class DummyQuery:
    def __init__(self, result: Any) -> None:
        self._result = result

    def filter(self, *args: Any, **kwargs: Any) -> "DummyQuery":
        return self

    def join(self, *args: Any, **kwargs: Any) -> "DummyQuery":
        return self

    def all(self) -> Any:
        if isinstance(self._result, list):
            return self._result
        if self._result is None:
            return []
        return [self._result]

    def first(self) -> Any:
        return self._result


class DummySession:
    def __init__(self, document: Any, template: Any) -> None:
        self._document = document
        self._template = template

    def query(self, *entities: Any) -> DummyQuery:
        if not entities:
            raise AssertionError("query requires at least one entity")

        model = entities[0]

        if model is template_routes.Document or getattr(model, "__name__", "") == "Document":
            return DummyQuery(self._document)
        if model is template_routes.Template or getattr(model, "__name__", "") == "Template":
            return DummyQuery(self._template)

        # Any other query (e.g. learning hints) returns empty results
        return DummyQuery([])

    def commit(self) -> None:
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    document = SimpleNamespace(id=5, file_path="/tmp/doc.pdf", status="completed")
    template = SimpleNamespace(
        id=9,
        target_fields=[{"field_name": "total", "llm_tier": "standard"}],
        extraction_rules={},
    )

    def override_get_db():
        yield DummySession(document, template)

    app.dependency_overrides[get_db] = override_get_db

    class DummyImageProcessor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def process_file(self, file_path: str, profile: Optional[Dict[str, Any]] = None) -> Any:
            return SimpleNamespace(
                image_path="/tmp/processed.png",
                original_image_path="/tmp/processed.png",
                text="",
            )

    class DummyOCREngine:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def extract_text(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "text": "Toplam 120",
                "average_confidence": 0.6,
                "word_count": 2,
            }

    def fake_field_level_ocr(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"total": {"text": "120", "confidence": 0.55}}

    class DummyInterpreter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def interpret_fields(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "field_mappings": {
                    "total": {
                        "value": "120",
                        "confidence": 0.9,
                        "source": "llm-specialist",
                    }
                },
                "latency_seconds": 1.5,
                "usage": {"prompt_tokens": 128},
                "model_metadata": {"model": "gpt-5.1-handwriting"},
            }

    monkeypatch.setattr(template_routes, "ImageProcessor", DummyImageProcessor)
    monkeypatch.setattr(template_routes, "OCREngine", DummyOCREngine)
    monkeypatch.setattr(template_routes, "run_field_level_ocr", fake_field_level_ocr)
    monkeypatch.setattr(template_routes, "HandwritingInterpreter", DummyInterpreter)

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_reanalyze_endpoint_merges_specialist_results(client: TestClient) -> None:
    response = client.post(
        "/api/template/reanalyze",
        json={
            "document_id": 5,
            "template_id": 9,
            "fields": ["total"],
            "current_mapping": {
                "total": {
                    "value": "100",
                    "confidence": 0.35,
                    "source": "llm-primary",
                }
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["updated_fields"]["total"]["value"] == "120"
    assert payload["updated_fields"]["total"]["confidence"] == 0.9
    assert payload["specialist"]["resolved_fields"] == ["total"]
    assert payload["operation"]["requested_fields"] == ["total"]
    assert payload["operation"]["resolved_fields"] == ["total"]
    assert payload["operation"]["operation"] == "reanalyze"
    assert payload["operation"]["latency_seconds"] == 1.5
    assert payload["specialist"]["latency_seconds"] == 1.5
