"""Production artifact routing and combined Next/API startup smoke tests."""
import json
import os
import shutil
import socket
import subprocess
import textwrap
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
HORARIO_ROOT = REPO_ROOT / "horario-escolar"
FRONTEND_STANDALONE = (
    HORARIO_ROOT
    / "frontend/.next-production/standalone/horario-escolar/frontend/server.js"
)


def read_toml(path: Path):
    with path.open("rb") as manifest:
        return tomllib.load(manifest)


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_artifact_routes_and_production_commands():
    horario = read_toml(
        REPO_ROOT / "artifacts/horario-inteligente/.replit-artifact/artifact.toml"
    )
    api = read_toml(REPO_ROOT / "artifacts/api-server/.replit-artifact/artifact.toml")

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
        (REPO_ROOT / "artifacts/api-server/package.json").read_text()
    )
    assert api_package["scripts"]["build"] == "node ./build.mjs"
    assert api_package["scripts"]["start"] == "node --enable-source-maps ./dist/index.mjs"
    assert set(generic_service["paths"]).isdisjoint(horario["services"][0]["paths"])


@pytest.fixture(scope="module")
def production_build():
    api_port = unused_port()
    result = subprocess.run(
        ["bash", str(HORARIO_ROOT / "build-production.sh")],
        cwd=REPO_ROOT,
        env={**os.environ, "API_PORT": str(api_port)},
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        "Production build failed:\n" + result.stdout + "\n" + result.stderr
    )
    assert FRONTEND_STANDALONE.is_file()

    routes = json.loads(
        (
            HORARIO_ROOT
            / "frontend/.next-production/standalone/horario-escolar/frontend/.next-production/routes-manifest.json"
        ).read_text()
    )
    assert any(
        f"127.0.0.1:{api_port}" in rewrite["destination"]
        and rewrite["source"] == "/api/:path*"
        for group in routes["rewrites"].values()
        for rewrite in group
    )
    return api_port


def create_python_shim(tmp_path: Path) -> Path:
    real_python = shutil.which("python") or shutil.which("python3")
    assert real_python, "Python executable required for the production startup smoke test"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "python"
    shim.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            if [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then
              if [ "${HI_TEST_API_MODE:-healthy}" = "unavailable" ]; then
                exit 23
              fi
              exec "$HI_TEST_REAL_PYTHON" "$HI_TEST_API_SERVER"
            fi
            exec "$HI_TEST_REAL_PYTHON" "$@"
            """
        )
    )
    shim.chmod(0o755)

    api_server = tmp_path / "api_server.py"
    api_server.write_text(
        textwrap.dedent(
            """\
            import json
            import os
            from http.server import BaseHTTPRequestHandler, HTTPServer

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != "/api/health":
                        self.send_error(404)
                        return
                    body = json.dumps({
                        "status": "ok",
                        "service": "horario-inteligente-api",
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    pass

            HTTPServer(("127.0.0.1", int(os.environ["API_PORT"])), Handler).serve_forever()
            """
        )
    )
    return shim_dir


def startup_environment(tmp_path: Path, api_port: int, web_port: int, mode="healthy"):
    shim_dir = create_python_shim(tmp_path)
    real_python = shutil.which("python") or shutil.which("python3")
    return {
        **os.environ,
        "PATH": str(shim_dir) + os.pathsep + os.environ["PATH"],
        "HI_TEST_REAL_PYTHON": real_python,
        "HI_TEST_API_SERVER": str(tmp_path / "api_server.py"),
        "HI_TEST_API_MODE": mode,
        "API_PORT": str(api_port),
        "PORT": str(web_port),
        "SESSION_SECRET": "production-smoke-test-session-secret-0123456789",
        "HI_RUNTIME_DATABASE_URL": "postgresql://startup-smoke-test.invalid/database",
        "PUBLIC_APP_URL": "http://127.0.0.1",
        "NODE_ENV": "production",
    }


def wait_for_http(url: str, process: subprocess.Popen, timeout: float = 30):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f"Production startup exited early ({process.returncode}): "
                f"{process.stdout.read() if process.stdout else ''}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status, response.read()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


def stop_process_group(process: subprocess.Popen):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, 15)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def test_production_root_and_health_smoke(production_build, tmp_path):
    api_port = production_build
    web_port = unused_port()
    process = subprocess.Popen(
        ["bash", str(HORARIO_ROOT / "start-production.sh")],
        cwd=REPO_ROOT,
        env=startup_environment(tmp_path, api_port, web_port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        root_status, root_body = wait_for_http(
            f"http://127.0.0.1:{web_port}/", process
        )
        health_status, health_body = wait_for_http(
            f"http://127.0.0.1:{web_port}/api/health", process
        )
        assert root_status == 200
        assert "Horário Inteligente".encode() in root_body
        assert health_status == 200
        assert json.loads(health_body)["service"] == "horario-inteligente-api"
    finally:
        stop_process_group(process)
        if process.stdout:
            process.stdout.close()


def test_unavailable_api_prevents_production_start(production_build, tmp_path):
    api_port = production_build
    result = subprocess.run(
        ["bash", str(HORARIO_ROOT / "start-production.sh")],
        cwd=REPO_ROOT,
        env=startup_environment(tmp_path, api_port, unused_port(), mode="unavailable"),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Production API stopped before becoming healthy." in result.stderr
