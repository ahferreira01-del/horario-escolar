"""Fase 4V: autenticação limita força bruta em Redis compartilhado.

A fixture SQLite é exclusiva de teste. A rate limit recebe backend falso
na mesma interface Redis, provando HTTP, normalização, reset e fail-closed
sem depender de serviço externo nem alterar a regra RLS.
"""
import pytest
from redis import exceptions as redis_errors

from test_app import context
from app import login_throttle
from app.main import settings
from app.security import hash_password


class FakeRedis:
    def __init__(self):
        self.attempts = {}
        self.blocked = False

    def eval(self, script, nkeys, key, seconds):
        if self.blocked:
            raise redis_errors.ConnectionError("redis fake credentials not configured")
        assert nkeys == 1 and seconds == login_throttle.WINDOW_SECONDS
        attempts = self.attempts.get(key, 0) + 1
        self.attempts[key] = attempts
        return [attempts, seconds]

    def delete(self, key):
        if self.blocked:
            raise redis_errors.TimeoutError("cache unavailable")
        self.attempts.pop(key, None)

    def ping(self):
        if self.blocked:
            raise redis_errors.ConnectionError("cache unavailable")
        return True


@pytest.fixture
def login_cache(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "auth_rate_limit_redis_url",
                        "redis://:fixture-password@redis:6379/0")
    monkeypatch.setattr(login_throttle, "_redis_client", lambda url: client)
    return client


def test_failed_logins_are_rate_limited_by_identity_not_raw_email(context,login_cache):
    client,_=context
    attempts = []
    for i in range(login_throttle.MAX_ATTEMPTS):
        email="ROOT@EXAMPLE.COM" if i%2 else "root@example.com"
        r=client.post("/api/auth/login",json={"email":email,"password":"invalid-password"})
        attempts.append(r.status_code)
    assert attempts == [401]*login_throttle.MAX_ATTEMPTS
    denied=client.post("/api/auth/login",json={
        "email":"root@example.com","password":"Senha-muito-forte-123"})
    assert denied.status_code == 429
    assert int(denied.headers["Retry-After"]) >= 1
    assert "root@example.com" not in repr(login_cache.attempts)
    assert all(key.startswith("horario:auth:v1:") for key in login_cache.attempts)


def test_successful_login_resets_account_limit(context,login_cache):
    client,_=context
    login={"email":"root@example.com","password":"Senha-muito-forte-123"}
    for _ in range(3):
        assert client.post("/api/auth/login",json={
            **login,"password":"invalid-password"}).status_code==401
    accepted=client.post("/api/auth/login",json=login)
    assert accepted.status_code==200
    assert not login_cache.attempts
    assert client.post("/api/auth/login",json=login).status_code==200


def test_unknown_account_has_same_response_as_wrong_password(context,login_cache):
    client,_=context
    unknown=client.post("/api/auth/login",json={
        "email":"unknown@example.org","password":"wrong-password"})
    known=client.post("/api/auth/login",json={
        "email":"root@example.com","password":"wrong-password"})
    assert unknown.status_code==known.status_code==401
    assert unknown.json()==known.json()


def test_login_fails_closed_when_redis_outage(context,login_cache):
    client,_=context
    login_cache.blocked=True
    r=client.post("/api/auth/login",json={
        "email":"root@example.com","password":"Senha-muito-forte-123"})
    assert r.status_code==503
    assert "credentials" not in str(r.json())


def test_authenticated_login_fails_closed_if_counter_cannot_be_cleared(context,login_cache):
    client,_=context
    def outage(_key):
        raise redis_errors.TimeoutError("cache lost")
    login_cache.delete=outage
    r=client.post("/api/auth/login",json={
        "email":"root@example.com","password":"Senha-muito-forte-123"})
    assert r.status_code==503


def test_dev_login_is_not_rate_limited(context,monkeypatch):
    monkeypatch.setattr(settings,"environment","development")
    client,_=context
    for _ in range(9):
        r=client.post("/api/auth/login",json={
            "email":"root@example.com","password":"wrong-password"})
        assert r.status_code==401


def test_hmac_identity_never_uses_plain_email():
    key=login_throttle._identity_key(" Student@Example.Org ")
    assert key==login_throttle._identity_key("student@example.org")
    assert "student" not in key and "@" not in key
    assert len(key.split(":")[-1])==64
