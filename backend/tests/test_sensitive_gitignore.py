"""Keep operational credentials and database exports out of Git."""
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def _is_ignored(path: str) -> bool:
    git_dir = os.environ.get("HI_TEST_GIT_DIR")
    if git_dir:
        command = [
            "git",
            f"--git-dir={git_dir}",
            f"--work-tree={REPO_ROOT}",
            "check-ignore",
            "--no-index",
            "-q",
            path,
        ]
    else:
        command = [
            "git",
            "-C",
            str(REPO_ROOT),
            "check-ignore",
            "--no-index",
            "-q",
            path,
        ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"git check-ignore failed for {path}: {result.stderr.decode(errors='replace')}"
        )
    return result.returncode == 0


def test_operational_environment_and_backup_files_are_ignored():
    for path in (
        "ops/production.env",
        "ops/production.env.local",
        "ops/backup.backup",
        "ops/snapshot.dump",
        "ops/export.sql.gz",
        "ops/run.tmp",
        "ops/cache.temp",
    ):
        assert _is_ignored(path), f"Sensitive or temporary path is not ignored: {path}"


def test_environment_example_template_remains_trackable():
    assert not _is_ignored("ops/production.env.example")
