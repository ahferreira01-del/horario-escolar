#!/usr/bin/env python3
"""Gate: testes Redis reais/autenticados devem executar sem skip no CI."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED = (
    "test_real_redis_lua_is_atomic_across_concurrent_connections",
    "test_real_redis_password_and_health_fail_closed",
    "test_production_compose_redis_uses_container_password_and_healthcheck",
)


def verify(xml_path: Path) -> None:
    root = ET.parse(xml_path).getroot()
    cases = root.findall(".//testcase")
    for name in REQUIRED:
        matching = [case for case in cases if case.get("name") == name]
        if len(matching) != 1:
            raise RuntimeError(f"Teste Redis obrigatório ausente ou duplicado: {name}")
        if matching[0].find("skipped") is not None:
            raise RuntimeError(f"Teste Redis obrigatório ignorado; CI NÃO homologado: {name}")
        if matching[0].find("failure") is not None or matching[0].find("error") is not None:
            raise RuntimeError(f"Teste Redis obrigatório falhou: {name}")
    print(f"CI_REDIS_GATES_PASS: {len(REQUIRED)} testes Redis reais/autenticados executados")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python scripts/verify_ci_redis_fase4w.py backend_test_results.xml")
    verify(Path(sys.argv[1]))
