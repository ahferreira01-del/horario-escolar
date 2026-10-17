"""Syntax-only checks for backup/restore operators, never touch real DB."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash não disponível")
@pytest.mark.parametrize("path",[
    ROOT/"ops"/"backup_encrypted.sh",
    ROOT/"ops"/"restore_drill.sh",
])
def test_recovery_scripts_have_valid_bash_syntax(path):
    p=subprocess.run(["bash","-n",str(path)],capture_output=True,text=True,timeout=10)
    assert p.returncode==0,p.stderr


def test_restore_drill_only_targets_fixed_scratch_database():
    script=(ROOT/"ops"/"restore_drill.sh").read_text(encoding="utf-8")
    assert "ISOLATED_HOST_ONLY" in script
    assert "horario_restore_drill" in script
    assert 'DROP DATABASE horario_restore_drill' in script
    assert 'DROP DATABASE horario WITH' not in script
    assert 'DROP DATABASE horario"' not in script


def test_backup_requires_age_encryption_and_pipefail():
    script=(ROOT/"ops"/"backup_encrypted.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "age -r " in script
    assert "pg_dump" in script
    assert 'HI_BACKUP_DIR' in script
    assert "umask 077" in script
    assert "--no-acl" not in script


def test_restore_preserves_and_checks_acl_and_runtime_rls():
    script=(ROOT/"ops"/"restore_drill.sh").read_text(encoding="utf-8")
    assert "--no-acl" not in script
    assert "version_num" in script and "0005" in script
    assert "has_table_privilege" in script
    assert "horario_runtime" in script
