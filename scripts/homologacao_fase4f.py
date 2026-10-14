#!/usr/bin/env python3
"""Homologação local/CI da Fase 4F. Não instala pacotes nem modifica banco.

Uso:
    python scripts/homologacao_fase4f.py
    python scripts/homologacao_fase4f.py --strict

--strict só tem sucesso após backend, solver, PostgreSQL e frontend passarem.
Todos os testes PostgreSQL exigem credenciais de uma base DESCARTÁVEL migrada,
HI_TEST_PG_OWNER_URL e HI_TEST_PG_RUNTIME_URL. Nunca aponte produção aqui.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(command, path, env=None, timeout=300):
    try:
        result = subprocess.run(command, cwd=path, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        return result.returncode, result.stdout[-8000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def main():
    parser = argparse.ArgumentParser(description='Validação Fase 4F')
    parser.add_argument('--strict', action='store_true', help='exigir todos os gates, sem exceções')
    parser.add_argument('--out', help='caminho do relatório JSON')
    args = parser.parse_args()

    gates = {}
    has_pg = bool(os.environ.get('HI_TEST_PG_OWNER_URL') and os.environ.get('HI_TEST_PG_RUNTIME_URL'))
    rc, output = run([sys.executable, '-m', 'pytest', '-q'], ROOT / 'backend')
    m = re.search(r'(\d+) passed', output)
    skip = re.search(r'(\d+) skipped', output)
    gates['backend'] = {'status': 'PASS' if rc == 0 else 'FAIL',
                        'passed': int(m.group(1)) if m else None,
                        'skipped': int(skip.group(1)) if skip else 0,
                        'log': output[-1800:]}
    gates['postgresql_rls_e_concorrencia'] = {
        'status': ('PASS' if rc == 0 and gates['backend']['skipped'] == 0 else 'FAIL') if has_pg else 'NOT_RUN',
        'detail': ('Credenciais de teste fornecidas; conferir resultado do pytest.' if has_pg
                   else 'HI_TEST_PG_OWNER_URL e HI_TEST_PG_RUNTIME_URL ausentes. Não usar dados de produção.')}

    rc, output = run([sys.executable, '-m', 'pytest', '-q'], ROOT / 'solver_poc_v0_2')
    m = re.search(r'(\d+) passed', output)
    gates['solver_experimental'] = {'status': 'PASS' if rc == 0 else 'FAIL',
                                   'passed': int(m.group(1)) if m else None,
                                   'log': output[-1800:]}

    if shutil.which('npm') and (ROOT / 'frontend/node_modules/next').exists():
        rc, output = run(['npm', 'run', 'lint:types'], ROOT / 'frontend')
        gates['frontend_typecheck'] = {'status': 'PASS' if rc == 0 else 'FAIL', 'log': output[-1800:]}
        rc, output = run(['npm', 'run', 'build'], ROOT / 'frontend', timeout=360)
        gates['frontend_build'] = {'status': 'PASS' if rc == 0 else 'FAIL', 'log': output[-1800:]}
    else:
        for gate in ('frontend_typecheck', 'frontend_build'):
            gates[gate] = {'status': 'NOT_RUN', 'detail': 'Next.js e dependências locais não instaladas; sem build comprovado.'}

    gates['ortools_cp_sat'] = {'status': 'NOT_RUN',
                               'detail': 'Migração do solver experimental para OR-Tools ainda não implementada.'}
    ready = all(g['status'] == 'PASS' for k, g in gates.items() if k != 'ortools_cp_sat')
    report = {'document': 'Homologação Fase 4F',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'production_certified': False,
              'integration_gates_ready': ready,
              'gates': gates}
    if args.out:
        target = pathlib.Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    has_fail = any(g['status'] == 'FAIL' for g in gates.values())
    return 1 if has_fail or (args.strict and not ready) else 0


if __name__ == '__main__':
    raise SystemExit(main())
