"""Limitador de login compartilhado e atômico no PostgreSQL.

Somente um HMAC do e-mail normalizado é persistido. A tabela é acessível ao
runtime por uma role própria e tem RLS forçado. Cada operação é confirmada
antes da verificação de credenciais para que tentativas falhas sobrevivam à
resposta HTTP e a reinícios de instância.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .config import settings
from .models import AuthLoginLimit

WINDOW_SECONDS = 300
MAX_ATTEMPTS = 8
CLEANUP_BATCH_SIZE = 50


def _identity_key(email: str) -> str:
    normalized = email.strip().lower()
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _unavailable() -> HTTPException:
    return HTTPException(503, "Autenticação temporariamente indisponível.")


def check_login_attempt(email: str, db) -> None:
    if settings.environment != "production":
        return
    try:
        if db.get_bind().dialect.name != "postgresql":
            raise RuntimeError("O limitador de produção exige PostgreSQL.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=WINDOW_SECONDS)

        # A limpeza é limitada e oportunista; não afeta os contadores ativos.
        expired = (
            select(AuthLoginLimit.identity_hash)
            .where(AuthLoginLimit.expires_at <= now)
            .order_by(AuthLoginLimit.expires_at)
            .limit(CLEANUP_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        db.execute(
            delete(AuthLoginLimit).where(AuthLoginLimit.identity_hash.in_(expired))
        )

        statement = (
            pg_insert(AuthLoginLimit)
            .values(
                identity_hash=_identity_key(email),
                attempts=1,
                window_started_at=now,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[AuthLoginLimit.identity_hash],
                set_={
                    "attempts": case(
                        (AuthLoginLimit.expires_at <= now, 1),
                        else_=AuthLoginLimit.attempts + 1,
                    ),
                    "window_started_at": case(
                        (AuthLoginLimit.expires_at <= now, now),
                        else_=AuthLoginLimit.window_started_at,
                    ),
                    "expires_at": case(
                        (AuthLoginLimit.expires_at <= now, expires_at),
                        else_=AuthLoginLimit.expires_at,
                    ),
                },
            )
            .returning(AuthLoginLimit.attempts, AuthLoginLimit.expires_at)
        )
        attempts, expiry = db.execute(statement).one()
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise _unavailable() from exc

    if attempts > MAX_ATTEMPTS:
        seconds_left = max(
            1, int((expiry - datetime.now(timezone.utc)).total_seconds())
        )
        raise HTTPException(
            429,
            "Muitas tentativas. Aguarde alguns minutos.",
            headers={"Retry-After": str(seconds_left)},
        )


def clear_successful_login(email: str, db) -> None:
    if settings.environment != "production":
        return
    try:
        if db.get_bind().dialect.name != "postgresql":
            raise RuntimeError("O limitador de produção exige PostgreSQL.")
        db.execute(
            delete(AuthLoginLimit).where(
                AuthLoginLimit.identity_hash == _identity_key(email)
            )
        )
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise _unavailable() from exc


def check_auth_backend() -> None:
    """Readiness fails closed if the shared PostgreSQL counter table is unusable."""
    if settings.environment != "production":
        return
    try:
        from .database import engine

        if engine.dialect.name != "postgresql":
            raise RuntimeError("O limitador de produção exige PostgreSQL.")
        with engine.connect() as connection:
            connection.execute(select(AuthLoginLimit.identity_hash).limit(0))
    except Exception as exc:
        raise _unavailable() from exc
