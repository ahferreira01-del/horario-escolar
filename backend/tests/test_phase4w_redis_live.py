"""Fase 4W: Redis REAL efêmero via Docker, sem segredos/dados de escolas.

O teste não cria servidor público: expõe apenas 127.0.0.1 do runner e
remove o contêiner ao terminar. Verifica Lua atômico, TTL e HTTP 429/503.
Quando Docker não existe, deixa a limitação explícita como skip.
"""
from concurrent.futures import ThreadPoolExecutor
import shutil
import socket
import subprocess
import time
import uuid

import pytest
from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError

from app import login_throttle
from app.config import settings


@pytest.fixture(scope="module")
def live_redis():
    if not shutil.which("docker"):
        pytest.skip("Docker indisponível: não executou integração Redis real")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port=sock.getsockname()[1]
    name="hi-ci-redis-"+uuid.uuid4().hex[:12]
    password="ci-ephemeral-redis-password-not-production"
    command=[
        "docker","run","--detach","--rm","--name",name,
        "--publish",f"127.0.0.1:{port}:6379",
        "--env",f"REDIS_PASSWORD={password}",
        "redis:7-alpine","sh","-ec",
        'exec redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"',
    ]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    if result.returncode:
        pytest.fail("O teste Redis real não iniciou o contêiner: "+result.stderr[-400:])
    url=f"redis://:{password}@127.0.0.1:{port}/0"
    client=Redis.from_url(url,decode_responses=True,
                          socket_connect_timeout=1,socket_timeout=1)
    try:
        for attempt in range(40):
            try:
                if client.ping():
                    break
            except RedisError:
                time.sleep(0.25)
        else:
            pytest.fail("Servidor Redis real não respondeu a PING autenticado")
        yield client,url
    finally:
        client.close()
        subprocess.run(["docker","rm","-f",name],capture_output=True,
                       text=True,timeout=20)


def test_real_redis_lua_is_atomic_across_concurrent_connections(live_redis,monkeypatch):
    redis_client,url=live_redis
    monkeypatch.setattr(settings,"environment","production")
    monkeypatch.setattr(settings,"auth_rate_limit_redis_url",url)
    redis_client.flushdb()
    email="synthetic-teacher-ci@example.invalid"
    key=login_throttle._identity_key(email)

    def attempt(number):
        try:
            login_throttle.check_login_attempt(
                email.upper() if number%2 else email)
            return 200
        except HTTPException as exc:
            assert exc.status_code==429
            assert int(exc.headers["Retry-After"])>0
            return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses=list(pool.map(attempt,range(16)))
    assert statuses.count(200)==login_throttle.MAX_ATTEMPTS
    assert statuses.count(429)==8
    assert int(redis_client.get(key))==16
    ttl=redis_client.ttl(key)
    assert 0<ttl<=login_throttle.WINDOW_SECONDS

    # Redis TCP clients represent separate API workers sharing a single
    # atomic counter, rather than a local Python in-memory dictionary.
    second_client=Redis.from_url(url,decode_responses=True)
    try:
        assert second_client.get(key)=="16"
    finally:
        second_client.close()
    login_throttle.clear_successful_login(email)
    assert redis_client.get(key) is None
    login_throttle.check_login_attempt(email)


def test_real_redis_password_and_health_fail_closed(live_redis,monkeypatch):
    client,url=live_redis
    monkeypatch.setattr(settings,"environment","production")
    monkeypatch.setattr(settings,"auth_rate_limit_redis_url",url)
    login_throttle.check_auth_backend()
    broken=url.replace("ci-ephemeral-redis-password-not-production","incorrect-password")
    monkeypatch.setattr(settings,"auth_rate_limit_redis_url",broken)
    with pytest.raises(HTTPException) as exc:
        login_throttle.check_auth_backend()
    assert exc.value.status_code==503
    with pytest.raises(HTTPException) as exc2:
        login_throttle.check_login_attempt("account@example.invalid")
    assert exc2.value.status_code==503
