"""Valida Compose de release (sem iniciar serviços) no runner com Docker disponível."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest


ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI não instalado neste runner")
def test_compose_production_no_public_db_or_api_ports(tmp_path):
    fake={
        "HI_PUBLIC_HOST":"horarios.escolas-teste.org",
        "HI_POSTGRES_OWNER_PASSWORD":"A"*48,
        "HI_POSTGRES_RUNTIME_PASSWORD":"B"*48,
        "HI_DB_OWNER_URL":f"postgresql+psycopg://horario_owner:{'A'*48}@db:5432/horario",
        "HI_DB_RUNTIME_URL":f"postgresql+psycopg://horario_runtime:{'B'*48}@db:5432/horario",
        "HI_SESSION_SECRET":"C"*64,
        "HI_SMTP_HOST":"smtp.escolas-teste.org",
        "HI_SMTP_PORT":"587",
        "HI_SMTP_USER":"smtp-user",
        "HI_SMTP_PASSWORD":"fake-test-smtp-password",
        "HI_SMTP_FROM":"convites@escolas-teste.org",
    }
    path=tmp_path/"production.env"
    path.write_text("\n".join(f"{k}={v}" for k,v in fake.items())+"\n",
                    encoding="utf-8")
    p=subprocess.run([
        "docker","compose","--env-file",str(path),
        "-f",str(ROOT/"docker-compose.production.yml"),
        "--profile","maintenance","config","--format","json",
    ],capture_output=True,text=True,timeout=30)
    assert p.returncode==0, p.stderr[:1000]
    services=json.loads(p.stdout)["services"]
    assert set(services)=={"db","migrate","api","web","edge"}
    for name in ("db","migrate","api","web"):
        assert "ports" not in services[name],name
    edge=services["edge"]
    ports={str(p["published"]) for p in edge["ports"]}
    assert ports=={"80","443"}
    assert services["api"]["environment"]["ENVIRONMENT"]=="production"
    assert services["api"]["environment"]["COOKIE_SECURE"]=="true"
    assert services["api"]["environment"]["DATABASE_URL"].split("://")[1].startswith("horario_runtime:")
    assert services["migrate"]["environment"]["DATABASE_URL"].split("://")[1].startswith("horario_owner:")
    assert set(services["db"]["networks"]) == {"data_net"}
    assert set(services["migrate"]["networks"]) == {"data_net"}
    assert set(services["api"]["networks"]) == {"data_net","service_net"}
    assert set(services["web"]["networks"]) == {"service_net","edge_net"}
    assert set(services["edge"]["networks"]) == {"edge_net"}
    assert not (set(services["edge"]["networks"]) & set(services["db"]["networks"]))
    assert "healthcheck" in services["api"]
    assert "AUTH_RATE_LIMIT_REDIS_URL" not in services["api"]["environment"]
    assert services["web"]["depends_on"]["api"]["condition"]=="service_healthy"
