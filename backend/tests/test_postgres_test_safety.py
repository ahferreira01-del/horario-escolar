import pytest

from postgres_test_safety import (
    postgres_tests_may_skip,
    validate_postgres_test_urls,
)


OWNER = "postgresql+psycopg://postgres:test_owner_password@127.0.0.1:5432/horario"
RUNTIME = (
    "postgresql+psycopg://horario_runtime:test_runtime_password"
    "@127.0.0.1:5432/horario"
)


def test_allows_only_fixed_local_disposable_database_urls():
    validate_postgres_test_urls(OWNER, RUNTIME)


@pytest.mark.parametrize(
    ("owner_url", "runtime_url"),
    [
        (
            "postgresql+psycopg://owner:production-secret@prod.example/production",
            RUNTIME,
        ),
        (
            OWNER,
            "postgresql+psycopg://horario_runtime:production-secret"
            "@127.0.0.1:5432/horario",
        ),
        (OWNER.replace("127.0.0.1", "db.example"), RUNTIME),
        (OWNER, None),
    ],
)
def test_rejects_production_or_incomplete_database_urls(owner_url, runtime_url):
    with pytest.raises(RuntimeError):
        validate_postgres_test_urls(owner_url, runtime_url)


def test_no_postgres_configuration_is_safe_for_non_integration_tests():
    validate_postgres_test_urls(None, None)


def test_required_postgres_gate_rejects_missing_urls():
    with pytest.raises(RuntimeError, match="obrigatório"):
        validate_postgres_test_urls(None, None, required=True)


def test_required_postgres_tests_cannot_be_skipped_without_urls(monkeypatch):
    monkeypatch.setenv("HI_REQUIRE_TEST_POSTGRES", "1")
    assert not postgres_tests_may_skip(None, None)
