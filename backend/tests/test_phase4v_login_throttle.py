"""Unit checks for account-key privacy; stateful behavior is tested on PostgreSQL."""
from app import login_throttle
from app.config import settings


def test_identity_key_is_opaque_and_case_normalized(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", "synthetic-test-session-secret")
    first = login_throttle._identity_key(" Admin@Example.org ")
    second = login_throttle._identity_key("admin@example.org")
    assert first == second
    assert len(first) == 64
    assert "admin" not in first
    assert "example.org" not in first


def test_nonproduction_does_not_require_rate_limit_database(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    login_throttle.check_login_attempt("admin@example.org", None)
    login_throttle.clear_successful_login("admin@example.org", None)
