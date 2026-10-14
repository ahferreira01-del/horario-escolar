"""Reject PostgreSQL integration URLs that could target a non-disposable DB."""
from sqlalchemy.engine import make_url


_EXPECTED = {
    "owner": ("postgres", "test_owner_password"),
    "runtime": ("horario_runtime", "test_runtime_password"),
}


def validate_postgres_test_urls(owner_url: str | None, runtime_url: str | None) -> None:
    """Allow only the fixed, loopback-only credentials used by disposable CI."""
    if not owner_url and not runtime_url:
        return
    if not owner_url or not runtime_url:
        raise RuntimeError("Os dois URLs do PostgreSQL efêmero precisam ser informados.")

    parsed = {}
    for label, value in (("owner", owner_url), ("runtime", runtime_url)):
        try:
            url = make_url(value)
        except Exception:
            raise RuntimeError("URL PostgreSQL de teste inválida.") from None
        expected_user, expected_password = _EXPECTED[label]
        if (
            url.drivername != "postgresql+psycopg"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or url.port != 5432
            or url.database != "horario"
            or url.username != expected_user
            or url.password != expected_password
        ):
            raise RuntimeError(
                "Testes PostgreSQL aceitam somente a instância descartável local "
                "com credenciais fixas de CI; URLs remotos ou credenciais externas são proibidos."
            )
        parsed[label] = url

    owner, runtime = parsed["owner"], parsed["runtime"]
    if (owner.host, owner.port, owner.database) != (
        runtime.host,
        runtime.port,
        runtime.database,
    ):
        raise RuntimeError(
            "As URLs owner e runtime precisam apontar para o mesmo PostgreSQL descartável."
        )
