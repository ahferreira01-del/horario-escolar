#!/usr/bin/env python3
"""Gate: testes PostgreSQL críticos não podem ser ignorados no CI."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED = (
    'test_postgres_rls_no_cross_tenant',
    'test_postgres_guard_rejects_extra_permissive_policy',
    'test_real_postgres_atomic_publish_no_duplicate_competing_requests',
    'test_postgres_complete_publish_exports_and_cross_tenant_denial',
    'test_postgres_runtime_membership_must_fail_closed',
)


def verify(xml_path: Path) -> None:
    root = ET.parse(xml_path).getroot()
    cases = root.findall('.//testcase')
    for name in REQUIRED:
        matching = [c for c in cases if c.get('name') == name]
        if len(matching) != 1:
            raise RuntimeError(f'Teste PostgreSQL ausente ou duplicado: {name}')
        if matching[0].find('skipped') is not None:
            raise RuntimeError(f'Teste PostgreSQL ignorado; CI NÃO homologado: {name}')
        if matching[0].find('failure') is not None or matching[0].find('error') is not None:
            raise RuntimeError(f'Teste PostgreSQL falhou: {name}')
    print(f'CI_POSTGRES_GATES_PASS: {len(REQUIRED)} testes PostgreSQL críticos executados')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python scripts/verify_ci_pg_fase4h.py backend_test_results.xml')
    verify(Path(sys.argv[1]))
