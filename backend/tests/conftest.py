"""Safety guard for every test that can connect to the PostgreSQL integration DB."""
import os
import shutil
import subprocess

from postgres_test_safety import validate_postgres_test_urls


def pytest_sessionstart(session):
    owner_url = os.environ.get("HI_TEST_PG_OWNER_URL")
    runtime_url = os.environ.get("HI_TEST_PG_RUNTIME_URL")
    postgres_required = os.environ.get("HI_REQUIRE_TEST_POSTGRES") == "1"
    validate_postgres_test_urls(
        owner_url,
        runtime_url,
        required=postgres_required,
    )
    if postgres_required and os.environ.get("DATABASE_URL") not in {
        owner_url,
        runtime_url,
    }:
        raise RuntimeError(
            "No gate CI, DATABASE_URL deve apontar exatamente para o PostgreSQL efêmero owner ou runtime."
        )

    if os.environ.get("HI_REQUIRE_DOCKER_TESTS") == "1":
        if shutil.which("docker") is None:
            raise RuntimeError("Docker é obrigatório para os gates Redis/Compose do CI.")
        for command in (["docker", "info"], ["docker", "compose", "version"]):
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(
                    f"Dependência Docker obrigatória indisponível: {command[-1]}."
                ) from exc
            if result.returncode:
                raise RuntimeError(
                    f"Dependência Docker obrigatória indisponível: {command[-1]}."
                )
