"""Verifica inicialização REAL do serviço Redis definido no Compose de produção.

Testa apenas Redis em projeto Docker temporário, com senhas fictícias.
Não publica portas nem inicia API, Caddy, PostgreSQL ou dados reais.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest


ROOT=Path(__file__).resolve().parents[2]


def test_production_compose_redis_uses_container_password_and_healthcheck(tmp_path):
    if shutil.which("docker") is None:
        if os.environ.get("HI_REQUIRE_REDIS_E2E") == "1":
            pytest.fail("Gate Redis obrigatório: CLI Docker indisponível para Compose")
        pytest.skip("Docker Compose indisponível: teste real do serviço Redis não executado")
    # Valores sintéticos; nunca ler a configuração real de operação.
    creds={
        "HI_PUBLIC_HOST":"hi-qa.example.invalid",
        "HI_POSTGRES_OWNER_PASSWORD":"A"*48,
        "HI_POSTGRES_RUNTIME_PASSWORD":"B"*48,
        "HI_DB_OWNER_URL":"postgresql+psycopg://horario_owner:"+("A"*48)+"@db:5432/horario",
        "HI_DB_RUNTIME_URL":"postgresql+psycopg://horario_runtime:"+("B"*48)+"@db:5432/horario",
        "HI_SESSION_SECRET":"C"*64,
        "HI_REDIS_PASSWORD":"D"*48,
        "HI_AUTH_REDIS_URL":"redis://:"+("D"*48)+"@redis:6379/0",
        "HI_SMTP_HOST":"smtp.invalid",
        "HI_SMTP_FROM":"convites@example.invalid",
    }
    path=tmp_path/"ci-production.env"
    path.write_text("\n".join(f"{k}={v}" for k,v in creds.items()),encoding="utf-8")
    project="hi-redis-qa-"+uuid.uuid4().hex[:8]
    docker=["docker","compose","--project-name",project,
            "--env-file",str(path),
            "--file",str(ROOT/"docker-compose.production.yml")]
    def run(*cmd,timeout=120):
        return subprocess.run([*docker,*cmd],capture_output=True,text=True,
                              timeout=timeout)
    try:
        start=run("up","--detach","--no-deps","--wait","redis",timeout=180)
        assert start.returncode==0, "Redis de produção não ficou healthy: "+start.stderr[-600:]
        ok=run("exec","-T","redis","sh","-ec",
               'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping')
        assert ok.returncode==0 and "PONG" in ok.stdout,ok.stderr[-500:]
        unauthenticated=run("exec","-T","redis","sh","-ec",
                            'unset REDISCLI_AUTH; redis-cli ping')
        assert "NOAUTH" in unauthenticated.stdout+unauthenticated.stderr
        ps=run("ps","--format","json","redis")
        assert ps.returncode==0,ps.stderr[-500:]
        # Docker Compose versions may emit either an array or NDJSON.
        try:
            raw=json.loads(ps.stdout)
            rows=raw if isinstance(raw,list) else [raw]
        except json.JSONDecodeError:
            rows=[json.loads(line) for line in ps.stdout.splitlines()
                  if line.strip()]
        assert len(rows)==1,rows
        assert rows[0]["State"]=="running"
        # A ausência de portas expostas na configuração já tem teste estático.
        # O ambiente é isolado em projeto aleatório sem depender de Compose prod.
    finally:
        down=run("down","--remove-orphans","--volumes",timeout=60)
        assert down.returncode==0,down.stderr[-500:]
