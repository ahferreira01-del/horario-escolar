"""4I: contrato do CI integrado + limites temporais em UTC.

Os testes deste arquivo rodam sem PostgreSQL/Node, portanto NÃO são uma
certificação da integração. Eles evitam regressões no desenho de homologação.
"""
from datetime import datetime, timezone
from pathlib import Path
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
    assert 'npm run lint:types' in all_commands
    assert 'npm run build' in all_commands
    assert 'node .next/standalone/server.js' in all_commands
    assert 'scripts/smoke_browser_fase4h.py' in all_commands
    assert 'playwright install --with-deps chromium' in all_commands
    assert 'sqlite' not in all_commands.lower(), 'O job integrado não pode cair silenciosamente em SQLite'
    assert 'backend_postgres' in jobs
    assert 'solver_legacy' in jobs


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
