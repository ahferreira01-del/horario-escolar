"""O provedor divulga somente a identidade do commit, nunca segredos."""
from app.main import release_identity, app


def test_release_metadata_is_unidentified_without_deployment_sha(monkeypatch):
    monkeypatch.delenv("HI_RELEASE_SHA",raising=False)
    meta=release_identity()
    assert meta["release_sha"] is None
    assert meta["release_identified"] is False
    assert meta["api_version"]==app.version


def test_release_identifies_explicit_valid_commit(monkeypatch):
    sha="A"*40
    monkeypatch.setenv("HI_RELEASE_SHA",sha)
    meta=release_identity()
    assert meta["release_sha"]=="a"*40
    assert meta["release_identified"] is True


def test_release_does_not_echo_arbitrary_environment_secrets(monkeypatch):
    for value in ("replit-deployed", "password=private", "not-a-commit", "b"*41):
        monkeypatch.setenv("HI_RELEASE_SHA",value)
        meta=release_identity()
        assert meta["release_identified"] is False
        assert meta["release_sha"] is None
