"""Safety guard for every test that can connect to the PostgreSQL integration DB."""
import os

from postgres_test_safety import validate_postgres_test_urls


def pytest_sessionstart(session):
    validate_postgres_test_urls(
        os.environ.get("HI_TEST_PG_OWNER_URL"),
        os.environ.get("HI_TEST_PG_RUNTIME_URL"),
    )
