#!/usr/bin/env python3
"""Build and smoke-test production startup in flat and nested temporary trees."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = ".next-production"


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def copy_project(workspace: Path, layout: str) -> Path:
    if layout == "flat":
        project_root = workspace
        package_glob = "frontend"
    elif layout == "replit":
        project_root = workspace / "horario-escolar"
        package_glob = "horario-escolar/frontend"
    else:
        raise ValueError(layout)

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "backend").mkdir()
    shutil.copytree(
        FRONTEND,
        project_root / "frontend",
        ignore=shutil.ignore_patterns(
            "node_modules", ".next", ".next-production", ".turbo", "tsconfig.tsbuildinfo"
        ),
    )
    installed_modules = FRONTEND / "node_modules"
    if not installed_modules.is_dir():
        raise RuntimeError("Frontend dependencies are not installed in this isolated checkout.")
    (project_root / "frontend" / "node_modules").symlink_to(
        installed_modules, target_is_directory=True
    )
    for script in ("build-production.sh", "start-production.sh"):
        shutil.copy2(ROOT / script, project_root / script)
    shutil.copy2(ROOT / ".npmrc", project_root / ".npmrc")
    (workspace / "pnpm-workspace.yaml").write_text(
        f"packages:\n  - {package_glob}\n", encoding="utf-8"
    )
    return project_root


def api_stub_files(temp_root: Path) -> tuple[Path, Path]:
    real_python = shutil.which("python") or shutil.which("python3")
    if not real_python:
        raise RuntimeError("Python executable is required for the API health stub.")
    shim_dir = temp_root / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
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
        ),
        encoding="utf-8",
    )
    shim.chmod(0o755)
    server = temp_root / "api_server.py"
    server.write_text(
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
        ),
        encoding="utf-8",
    )
    return shim_dir, server


def wait_for_http(url: str, process: subprocess.Popen[str], timeout: float = 45):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise AssertionError(f"Production startup exited early: {output[-4000:]}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status, response.read()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


def stop_process_group(process: subprocess.Popen[str]) -> None:
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


def run_layout(layout: str, work_root: Path) -> None:
    project_root = copy_project(work_root / layout, layout)
    api_port = unused_port()
    build = subprocess.run(
        ["bash", str(project_root / "build-production.sh")],
        cwd=project_root,
        env={
            **os.environ,
            "API_PORT": str(api_port),
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
            "NPM_CONFIG_STRICT_SSL": "true",
        },
        text=True,
        capture_output=True,
        timeout=600,
    )
    if build.returncode:
        raise AssertionError(
            f"{layout} production build failed:\n{build.stdout[-4000:]}\n{build.stderr[-4000:]}"
        )

    standalone_root = project_root / "frontend" / DIST / "standalone"
    standalone_app = (
        standalone_root / "horario-escolar" / "frontend"
        if (standalone_root / "horario-escolar" / "frontend" / "server.js").is_file()
        else standalone_root
    )
    if not (standalone_app / "server.js").is_file():
        raise AssertionError(f"{layout} standalone server not found below {standalone_root}")

    manifest_candidates = [
        project_root / "frontend" / DIST / "routes-manifest.json",
        standalone_app / DIST / "routes-manifest.json",
        standalone_app / ".next" / "routes-manifest.json",
    ]
    manifest_path = next((path for path in manifest_candidates if path.is_file()), None)
    if manifest_path is None:
        raise AssertionError(f"{layout} routes-manifest.json missing")
    routes = json.loads(manifest_path.read_text(encoding="utf-8"))
    rewrites = [rewrite for group in routes["rewrites"].values() for rewrite in group]
    expected_destination = f"127.0.0.1:{api_port}"
    if not any(
        rewrite["source"] == "/api/:path*" and expected_destination in rewrite["destination"]
        for rewrite in rewrites
    ):
        raise AssertionError(f"{layout} API rewrite does not target the local stub.")

    shim_dir, api_server = api_stub_files(work_root / f"{layout}-runtime")
    web_port = unused_port()
    runtime_env = {
        **os.environ,
        "PATH": str(shim_dir) + os.pathsep + os.environ.get("PATH", ""),
        "HI_TEST_REAL_PYTHON": shutil.which("python") or shutil.which("python3") or sys.executable,
        "HI_TEST_API_SERVER": str(api_server),
        "HI_TEST_API_MODE": "healthy",
        "API_PORT": str(api_port),
        "PORT": str(web_port),
        "HI_BIND_HOST": "127.0.0.1",
        "SESSION_SECRET": "synthetic-startup-test-session-secret-only-0123456789",
        "HI_RUNTIME_DATABASE_URL": "postgresql://startup-smoke.invalid/horario",
        "PUBLIC_APP_URL": "http://127.0.0.1",
        "NODE_ENV": "production",
    }
    process = subprocess.Popen(
        ["bash", str(project_root / "start-production.sh")],
        cwd=project_root,
        env=runtime_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        root_status, root_body = wait_for_http(f"http://127.0.0.1:{web_port}/", process)
        health_status, health_body = wait_for_http(
            f"http://127.0.0.1:{web_port}/api/health", process
        )
        if root_status != 200 or b"Hor\xc3\xa1rio Inteligente" not in root_body:
            raise AssertionError(f"{layout} frontend root failed ({root_status}).")
        if health_status != 200 or json.loads(health_body)["service"] != "horario-inteligente-api":
            raise AssertionError(f"{layout} API health route failed ({health_status}).")
    finally:
        stop_process_group(process)
        if process.stdout:
            process.stdout.close()

    unavailable = subprocess.run(
        ["bash", str(project_root / "start-production.sh")],
        cwd=project_root,
        env={**runtime_env, "HI_TEST_API_MODE": "unavailable", "PORT": str(unused_port())},
        text=True,
        capture_output=True,
        timeout=15,
    )
    if unavailable.returncode == 0 or "stopped before becoming healthy" not in unavailable.stderr:
        raise AssertionError(f"{layout} startup did not fail closed when API was unavailable.")
    print(f"PRODUCTION_STARTUP_{layout.upper()}_PASSED")


def main() -> None:
    if not (FRONTEND / "node_modules").is_dir():
        raise SystemExit("Run pnpm install --frozen-lockfile before this startup smoke test.")
    with tempfile.TemporaryDirectory(prefix="hi-production-startup-") as temp:
        root = Path(temp)
        for layout in ("flat", "replit"):
            run_layout(layout, root)
    print("PRODUCTION_STARTUP_LAYOUTS_PASSED")


if __name__ == "__main__":
    main()
