"""The committed contract must match the code, be valid OpenAPI, and carry valid examples."""

import importlib
import inspect
import pkgutil

import pytest
from openapi_spec_validator import validate
from pydantic import BaseModel

import app.schemas
from app.main import create_app
from app.openapi_export import CONTRACT_PATH, render


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app().openapi()


def test_committed_contract_is_up_to_date() -> None:
    committed = CONTRACT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render(), (
        "api/openapi.yaml is out of date. Run `uv run python -m app.openapi_export` in backend/ "
        "and commit the result."
    )


def test_contract_is_valid_openapi(spec: dict) -> None:
    validate(spec)


def test_every_operation_is_documented(spec: dict) -> None:
    seen: set[str] = set()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            where = f"{method.upper()} {path}"
            assert op.get("operationId"), f"{where} has no operationId"
            assert op["operationId"] not in seen, f"duplicate operationId {op['operationId']}"
            seen.add(op["operationId"])
            assert op.get("summary"), f"{where} has no summary"
            assert op.get("tags"), f"{where} has no tag"


def test_error_responses_use_problem_json(spec: dict) -> None:
    for path, item in spec["paths"].items():
        for method, op in item.items():
            for code, resp in op["responses"].items():
                if code.startswith(("4", "5")):
                    assert list(resp["content"]) == ["application/problem+json"], (
                        f"{method.upper()} {path} {code}"
                    )


def _schema_models() -> list[type[BaseModel]]:
    models = []
    for info in pkgutil.iter_modules(app.schemas.__path__):
        module = importlib.import_module(f"app.schemas.{info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModel) and obj.__module__ == module.__name__:
                models.append(obj)
    return models


@pytest.mark.parametrize("model", _schema_models(), ids=lambda m: m.__name__)
def test_schema_examples_are_valid(model: type[BaseModel]) -> None:
    extra = model.model_config.get("json_schema_extra")
    examples = extra.get("examples", []) if isinstance(extra, dict) else []
    for example in examples:
        model.model_validate(example)
