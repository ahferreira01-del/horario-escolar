"""Limitador de login compartilhado por Redis, sem usar IP/headers falsificáveis.

Em produção, toda tentativa de autenticação é contabilizada atomicamente
por e-mail normalizado e HMAC com segredo do servidor. Um cliente ou proxy
pode alterar cabeçalhos X-Forwarded-For; por isso NÃO são usados como chave.
O bloqueio por conta também pode ser explorado para negação de acesso,
por isso o tempo é curto e erros jamais revelam existência de usuário.
"""
from functools import lru_cache
import hashlib
import hmac

from fastapi import HTTPException
from redis import Redis, exceptions as redis_errors
from .config import settings

WINDOW_SECONDS = 300
MAX_ATTEMPTS = 8
LUA_RECORD_ATTEMPT = """
local attempts = redis.call('INCR', KEYS[1])
if attempts == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local seconds_left = redis.call('TTL', KEYS[1])
return {attempts, seconds_left}
"""


@lru_cache(maxsize=4)
def _redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, socket_connect_timeout=1,
                          socket_timeout=1, decode_responses=True)


def _identity_key(email: str) -> str:
    normalized = email.strip().lower()
    digest = hmac.new(settings.session_secret.encode("utf-8"),
                      normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return "horario:auth:v1:" + digest


def _client() -> Redis:
    if not settings.auth_rate_limit_redis_url:
        # Mesmo se o validador de config foi contornado, negar acesso.
        raise HTTPException(503, "Autenticação temporariamente indisponível.")
    return _redis_client(settings.auth_rate_limit_redis_url)


def _unavailable() -> HTTPException:
    return HTTPException(503, "Autenticação temporariamente indisponível.")


def check_login_attempt(email: str) -> None:
    if settings.environment != "production":
        return
    try:
        attempts, ttl = _client().eval(
            LUA_RECORD_ATTEMPT, 1, _identity_key(email), WINDOW_SECONDS)
    except (redis_errors.RedisError, ConnectionError, TimeoutError, ValueError) as exc:
        raise _unavailable() from exc
    if int(attempts) > MAX_ATTEMPTS:
        retry_after = max(1, int(ttl))
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.",
                            headers={"Retry-After": str(retry_after)})


def clear_successful_login(email: str) -> None:
    if settings.environment != "production":
        return
    try:
        _client().delete(_identity_key(email))
    except (redis_errors.RedisError, ConnectionError, TimeoutError) as exc:
        raise _unavailable() from exc


def check_auth_backend() -> None:
    """Readiness de produção: login não fica disponível se Redis falhar."""
    if settings.environment != "production":
        return
    try:
        if not _client().ping():
            raise _unavailable()
    except (redis_errors.RedisError, ConnectionError, TimeoutError) as exc:
        raise _unavailable() from exc
