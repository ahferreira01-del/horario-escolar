#!/usr/bin/env python3
"""Preflight local de release; nunca imprime senhas ou URLs autenticadas.

Executar: python ops/preflight_production.py --env-file ops/production.env
Não conecta ao servidor e NÃO constitui homologação de implantação.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import re
import sys

REQUIRED = (
    "HI_PUBLIC_HOST",
    "HI_POSTGRES_OWNER_PASSWORD", "HI_POSTGRES_RUNTIME_PASSWORD",
    "HI_DB_OWNER_URL", "HI_DB_RUNTIME_URL", "HI_SESSION_SECRET",
    "HI_SMTP_HOST", "HI_SMTP_FROM", "HI_REDIS_PASSWORD", "HI_AUTH_REDIS_URL",
)
PLACEHOLDER_MARKERS = ("REPLACE", "SUBSTITUA", "CHANGE_ME", "EXAMPLE", "DEV_ONLY")


def load_simple_env(path: Path) -> dict[str, str]:
    result = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError(f"Linha de configuração inválida: {number}")
        key = key.strip()
        if key in result:
            raise ValueError(f"Variável duplicada: {key}")
        result[key] = value.strip().strip('"').strip("'")
    return result


def validate_config(values: dict[str, str]) -> list[str]:
    errors = []
    for key in REQUIRED:
        value = values.get(key, "")
        if not value or any(tag in value.upper() for tag in PLACEHOLDER_MARKERS):
            errors.append(f"{key}: ausente ou exemplo não substituído")
    host = values.get("HI_PUBLIC_HOST", "")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}", host)
            or host.lower().endswith(".example.org")
            or host.lower().endswith(".example.com")):
        errors.append("HI_PUBLIC_HOST: informe domínio público válido, sem protocolo")
    try:
        ipaddress.ip_address(host)
        errors.append("HI_PUBLIC_HOST: use um hostname, não endereço IP")
    except ValueError:
        pass

    for key in ("HI_POSTGRES_OWNER_PASSWORD", "HI_POSTGRES_RUNTIME_PASSWORD",
                "HI_SESSION_SECRET", "HI_REDIS_PASSWORD"):
        val = values.get(key, "")
        if val and len(val) < 40:
            errors.append(f"{key}: mínimo 40 caracteres")
        if val and not re.fullmatch(r"[A-Za-z0-9_-]+", val):
            errors.append(f"{key}: neste perfil usar somente [A-Za-z0-9_-] (ou adaptar URL encoding)")
    credentials = [values.get(key) for key in (
        "HI_POSTGRES_OWNER_PASSWORD", "HI_POSTGRES_RUNTIME_PASSWORD",
        "HI_REDIS_PASSWORD", "HI_SESSION_SECRET")]
    if any(v and credentials.count(v) > 1 for v in credentials):
        errors.append("Senhas e segredo da sessão devem ser diferentes")
    for field, user, password in [
        ("HI_DB_OWNER_URL", "horario_owner", "HI_POSTGRES_OWNER_PASSWORD"),
        ("HI_DB_RUNTIME_URL", "horario_runtime", "HI_POSTGRES_RUNTIME_PASSWORD"),
    ]:
        try:
            url = urlsplit(values.get(field, ""))
            if (url.scheme != "postgresql+psycopg" or url.hostname != "db"
                    or url.port != 5432 or url.username != user
                    or url.password != values.get(password)
                    or url.path != "/horario"):
                errors.append(f"{field}: credenciais/esquema/host inconsistentes")
        except (ValueError, TypeError):
            errors.append(f"{field}: formato inválido")
    try:
        redis_url = urlsplit(values.get("HI_AUTH_REDIS_URL", ""))
        if (redis_url.scheme != "redis" or redis_url.hostname != "redis"
                or redis_url.port != 6379 or redis_url.username not in (None, "")
                or redis_url.password != values.get("HI_REDIS_PASSWORD")
                or redis_url.path != "/0"):
            errors.append("HI_AUTH_REDIS_URL: senha, host ou porta incompatíveis")
    except (ValueError, TypeError):
        errors.append("HI_AUTH_REDIS_URL: formato inválido")
    try:
        port = int(values.get("HI_SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            errors.append("HI_SMTP_PORT: porta inválida")
    except ValueError:
        errors.append("HI_SMTP_PORT: porta inválida")
    if values.get("HI_SMTP_USER") and not values.get("HI_SMTP_PASSWORD"):
        errors.append("HI_SMTP_PASSWORD: exigida com HI_SMTP_USER")
    if "@" not in values.get("HI_SMTP_FROM", ""):
        errors.append("HI_SMTP_FROM: remetente inválido")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.env_file.is_file():
        parser.error("Arquivo de configuração não encontrado (não use exemplo).")
    try:
        config = load_simple_env(args.env_file)
        errors = validate_config(config)
    except (OSError, ValueError) as exc:
        print("PREFLIGHT_BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print("PREFLIGHT_BLOCKED: " + error, file=sys.stderr)
        return 1
    print("PREFLIGHT_CONFIGURATION_PASS (não valida DNS, TLS, DB, SMTP nem gates 4K/LGPD)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
