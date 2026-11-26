"""OpenAPI schema-аас web-ийн client үүсдэг: тогтвортой, давхардаагүй байх ёстой."""

from angel.core.config import Settings
from angel.main import create_app


def test_every_operation_has_its_own_id() -> None:
    schema = create_app(Settings(app_env="test")).openapi()

    ids = [
        operation["operationId"] for path in schema["paths"].values() for operation in path.values()
    ]

    assert sorted({i for i in ids if ids.count(i) > 1}) == []
