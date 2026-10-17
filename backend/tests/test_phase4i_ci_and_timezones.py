"""4I: contrato do CI integrado + limites temporais em UTC.

Os testes deste arquivo rodam sem PostgreSQL/Node, portanto NÃO são uma
certificação da integração. Eles evitam regressões no desenho de homologação.
"""
from datetime import datetime, timezone
from pathlib import Path
import re
from types import SimpleNamespace
import yaml
import pytest
from fastapi import HTTPException
from app.publication import _check_published_conflicts

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'


def test_ci_browser_requires_postgres_rls_and_runtime_role():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))
    jobs = workflow['jobs']
    assert 'frontend_browser_postgres' in jobs
    job = jobs['frontend_browser_postgres']
    assert job['services']['postgres']['image'].startswith('postgres:16')
    steps = job['steps']
    all_commands = '\n'.join(str(s.get('run', '')) for s in steps)
    assert 'alembic upgrade head' in all_commands
    assert 'CREATE ROLE horario_runtime' in all_commands
    assert 'NOBYPASSRLS' in all_commands
    assert 'DATABASE_URL=postgresql+psycopg://postgres:' in all_commands  # migração/bootstrap owner
    runtime_steps = [step for step in steps if 'Iniciar API' in step.get('name', '') or 'iniciar API' in step.get('name', '')]
    assert len(runtime_steps) == 1
    assert runtime_steps[0]['env']['DATABASE_URL'].startswith('postgresql+psycopg://horario_runtime:')
    backend_steps = jobs['backend_postgres']['steps']
    integration_steps = [
        step for step in backend_steps
        if 'Testar isolamento real' in step.get('name', '')
    ]
    assert len(integration_steps) == 1
    assert integration_steps[0]['env']['DATABASE_URL'].startswith(
        'postgresql+psycopg://horario_runtime:'
    )
    # Validar o comando de build mesmo quando executado via script portátil.
    build_steps = [step for step in steps if step.get('name') == 'Build Next.js e checagem TypeScript']
    assert len(build_steps) == 1
    assert build_steps[0].get('working-directory') == 'frontend'
    build_commands = [line.strip() for line in build_steps[0]['run'].splitlines()]
    assert 'pnpm run lint:types' in build_commands
    assert 'bash ../build-production.sh' in build_commands
    assert 'python ../scripts/verify_next_standalone.py .next-production/standalone' in build_commands
    production_build = (ROOT / 'build-production.sh').read_text(encoding='utf-8')
    assert any(
        re.search(r'\bpnpm run build\b', line)
        for line in production_build.splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    )

    # Validar a inicialização dinâmica para os layouts GitHub e Replit.
    runtime_commands = runtime_steps[0]['run']
    assert 'standalone_server=.next-production/standalone/horario-escolar/frontend/server.js' in runtime_commands
    assert 'standalone_server=.next-production/standalone/frontend/server.js' in runtime_commands
    assert 'standalone_server=.next-production/standalone/server.js' in runtime_commands
    assert 'node "$standalone_server"' in runtime_commands
    assert re.search(r'(?m)^\s*exit 1\s*$', runtime_commands)
    assert 'scripts/smoke_browser_fase4h.py' in all_commands
    assert 'playwright install --with-deps chromium' in all_commands
    e2e_order = [
        all_commands.index('scripts/smoke_browser_fase4h.py'),
        all_commands.index('scripts/smoke_browser_school_fase4j.py'),
        all_commands.index('scripts/smoke_browser_publication_fase4k.py'),
    ]
    assert e2e_order == sorted(e2e_order)
    assert "grep -q '^BROWSER_PASSED:'" in all_commands
    assert "grep -q '^SCHOOL_BROWSER_PASSED:'" in all_commands
    assert "grep -q '^OFFICIAL_BROWSER_PASSED:'" in all_commands
    assert 'echo OFFICIAL_BROWSER_PASSED' in all_commands
    assert 'sqlite' not in all_commands.lower(), 'O job integrado não pode cair silenciosamente em SQLite'
    assert 'backend_postgres' in jobs
    assert 'solver_legacy' in jobs
    assert 'production_startup' in jobs
    assert 'smoke_production_startup_layouts.py' in '\n'.join(
        str(step.get('run', '')) for step in jobs['production_startup']['steps']
    )


def test_ci_dispatch_actions_and_container_images_are_immutable():
    workflow_text = WORKFLOW.read_text(encoding='utf-8')
    assert re.search(r'(?m)^  workflow_dispatch:\s*$', workflow_text)
    uses = re.findall(r'(?m)^\s*-\s*uses:\s*([^\s#]+)', workflow_text)
    source_check = WORKFLOW.with_name('source-check.yml').read_text(encoding='utf-8')
    uses.extend(re.findall(r'(?m)^\s*uses:\s*([^\s#]+)', source_check))
    assert uses
    assert all(re.fullmatch(r'[^@]+@[0-9a-f]{40}', action) for action in uses), uses
    assert yaml.safe_load(workflow_text)['permissions'] == {'contents': 'read'}
    assert 'secrets.' not in workflow_text

    production = yaml.safe_load(
        (ROOT / 'docker-compose.production.yml').read_text(encoding='utf-8')
    )
    development = yaml.safe_load(
        (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    )
    expected = {
        'postgres_ci': (
            'postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d'
        ),
        'postgres_alpine': (
            'postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea'
        ),
    }
    ci_postgres = yaml.safe_load(workflow_text)['jobs']['backend_postgres']['services']['postgres']['image']
    assert ci_postgres == expected['postgres_ci']
    assert development['services']['db']['image'] == expected['postgres_alpine']
    assert production['services']['db']['image'] == expected['postgres_alpine']
    assert 'redis' not in production['services']
    postgres_throttle_test = (
        ROOT / 'backend/tests/test_phase4x_postgres_login_throttle.py'
    ).read_text(encoding='utf-8')
    assert 'HI_TEST_PG_RUNTIME_URL' in postgres_throttle_test


def _lesson(start, end, school, cls):
    return {
        'start_utc': start, 'end_utc': end, 'teacher_id': 'teacher-shared',
        'class_id': cls, 'school_id': school, 'resource_id': None, 'students': 20,
    }


def test_travel_time_checked_even_when_local_date_changes():
    """Deslocamento cadastrado não pode ser ignorado às 00:00 UTC/local."""
    a = _lesson(datetime(2027, 2, 1, 23, 15, tzinfo=timezone.utc),
                datetime(2027, 2, 1, 23, 55, tzinfo=timezone.utc), 'centro', 'a')
    b = _lesson(datetime(2027, 2, 2, 0, 5, tzinfo=timezone.utc),
                datetime(2027, 2, 2, 0, 55, tzinfo=timezone.utc), 'norte', 'b')
    schools = {'centro': SimpleNamespace(timezone='UTC'),
               'norte': SimpleNamespace(timezone='UTC')}
    with pytest.raises(HTTPException, match='Conflito de deslocamento'):
        _check_published_conflicts([a, b], [], schools, {('centro', 'norte'): 20})
    _check_published_conflicts([a, b], [], schools, {('centro', 'norte'): 10})


def test_overlap_is_detected_across_different_local_timezones():
    a = _lesson(datetime(2027, 2, 2, 1, 45, tzinfo=timezone.utc),
                datetime(2027, 2, 2, 2, 15, tzinfo=timezone.utc), 'centro', 'a')
    b = _lesson(datetime(2027, 2, 2, 2, 0, tzinfo=timezone.utc),
                datetime(2027, 2, 2, 2, 40, tzinfo=timezone.utc), 'norte', 'b')
    schools = {'centro': SimpleNamespace(timezone='America/Sao_Paulo'),
               'norte': SimpleNamespace(timezone='Europe/Lisbon')}
    with pytest.raises(HTTPException, match='Conflito de professor'):
        _check_published_conflicts([a, b], [], schools, {})


def test_missing_travel_time_is_not_assumed_zero_across_midnight():
    a = _lesson(datetime(2027, 2, 1, 23, 10, tzinfo=timezone.utc),
                datetime(2027, 2, 1, 23, 55, tzinfo=timezone.utc), 'centro', 'a')
    b = _lesson(datetime(2027, 2, 2, 0, 5, tzinfo=timezone.utc),
                datetime(2027, 2, 2, 0, 55, tzinfo=timezone.utc), 'norte', 'b')
    schools = {'centro': SimpleNamespace(timezone='UTC'),
               'norte': SimpleNamespace(timezone='UTC')}
    with pytest.raises(HTTPException, match='Tempo de deslocamento'):
        _check_published_conflicts([a, b], [], schools, {})
