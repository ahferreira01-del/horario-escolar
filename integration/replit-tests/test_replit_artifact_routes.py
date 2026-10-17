"""Read-only checks for the Replit-specific artifact routing contract."""
import json
import os
from pathlib import Path
import tomllib

import pytest


ROOT_VALUE = os.environ.get("HI_REPLIT_TEST_ROOT")
if not ROOT_VALUE:
    pytest.skip("Set HI_REPLIT_TEST_ROOT to the Replit workspace root.", allow_module_level=True)
REPLIT_ROOT = Path(ROOT_VALUE).resolve()


def _toml(path: Path):
    with path.open("rb") as manifest:
        return tomllib.load(manifest)


def test_replit_artifact_routes_and_production_commands():
    horario = _toml(
        REPLIT_ROOT / "artifacts/horario-inteligente/.replit-artifact/artifact.toml"
    )
    api = _toml(REPLIT_ROOT / "artifacts/api-server/.replit-artifact/artifact.toml")

    assert horario["previewPath"] == "/"
    assert horario["router"] == "path"
    assert horario["services"][0]["paths"] == ["/"]
    production = horario["services"][0]["production"]
    assert production["build"]["args"] == ["bash", "horario-escolar/build-production.sh"]
    assert production["run"]["args"] == ["bash", "horario-escolar/start-production.sh"]
    assert production["health"]["startup"]["path"] == "/api/health"

    generic_service = api["services"][0]
    assert api["previewPath"] == "/__workspace-api"
    assert generic_service["paths"] == ["/__workspace-api"]
    assert generic_service["development"]["run"] == (
        "pnpm --filter @workspace/api-server run dev"
    )
    api_package = json.loads(
        (REPLIT_ROOT / "artifacts/api-server/package.json").read_text()
    )
    assert api_package["scripts"]["build"] == "node ./build.mjs"
    assert api_package["scripts"]["start"] == "node --enable-source-maps ./dist/index.mjs"
    assert set(generic_service["paths"]).isdisjoint(horario["services"][0]["paths"])
