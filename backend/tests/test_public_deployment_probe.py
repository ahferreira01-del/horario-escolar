"""Public release probe must never accept wrong commit, HTTP, or missing RLS."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import json

import pytest


MODULE=Path(__file__).resolve().parents[2]/"scripts"/"verify_public_deployment.py"
spec=spec_from_file_location("verify_public_deployment",MODULE)
probe=module_from_spec(spec)
spec.loader.exec_module(probe)


class Response:
    status=200
    headers={"Content-Type":"application/json"}
    def __init__(self,url,data):
        self.url=url
        self.data=data
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def geturl(self):
        return self.url
    def read(self,n):
        return json.dumps(self.data).encode()


class Opener:
    def __init__(self,api):
        self.api=api
    def open(self,req,timeout):
        return Response(req.full_url,self.api[req.full_url.split("/")[-1]])


def test_probe_checks_sha_health_and_readiness(monkeypatch):
    sha="a"*40
    api={
        "release":{"release_identified":True,"release_sha":sha},
        "health":{"status":"ok"},
        "ready":{"status":"ready"},
    }
    monkeypatch.setattr(probe.request,"build_opener",lambda *x:Opener(api))
    result=probe.check("https://horario-inteligente.replit.app",sha)
    assert result[0].startswith("/api/release: PASS")
    assert all(": PASS" in line for line in result)


def test_probe_blocks_mismatched_or_unknown_release(monkeypatch):
    sha="a"*40
    api={
        "release":{"release_identified":False,"release_sha":None},
        "health":{"status":"ok"},
        "ready":{"status":"ready"},
    }
    monkeypatch.setattr(probe.request,"build_opener",lambda *x:Opener(api))
    assert any(": FAIL" in line for line in probe.check("https://horario-inteligente.replit.app",sha))


@pytest.mark.parametrize("bad_url",[
    "http://horario-inteligente.replit.app",
    "https://user:pass@horario-inteligente.replit.app",
    "https://horario-inteligente.replit.app/api/health",
    "https://horario-inteligente.replit.app?password=1",
])
def test_probe_refuses_unsafe_base_url(bad_url):
    with pytest.raises(ValueError,match="HTTPS"):
        probe.check(bad_url,"a"*40)


def test_probe_refuses_unknown_sha():
    with pytest.raises(ValueError,match="SHA"):
        probe.check("https://horario-inteligente.replit.app","dev")
