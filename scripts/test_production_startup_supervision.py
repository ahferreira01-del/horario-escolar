#!/usr/bin/env python3
"""Fault-injection tests for the real production launcher and disposable services.

Requires Python 3.12, Node 22, Docker, and the backend/frontend locked
dependencies. PostgreSQL and all app data are temporary.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
POSTGRES_IMAGE = (
    "postgres:16@sha256:"
    "ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
)
OWNER_PASSWORD = "e14-ci-owner-test-only"
RUNTIME_PASSWORD = "e14-ci-runtime-test-only"
ADMIN_EMAIL = "startup-admin@example.com"
ADMIN_PASSWORD = "e14-ci-admin-password-test-only"
SYNTHETIC_SESSION_SECRET = "e14-ci-session-key-0123456789-abcdefghijklmnopqrstuvwxyz"
HTTP_TIMEOUT = 5


def emit(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    print(f"[{timestamp}] {message}", flush=True)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def wait_for_port(port: int, *, opened: bool, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tcp_open(port) is opened:
            return
        time.sleep(0.1)
    expected = "open" if opened else "closed"
    raise AssertionError(f"Port {port} did not become {expected} within {timeout}s.")


def request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = HTTP_TIMEOUT,
) -> tuple[int | None, bytes]:
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    req = Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
    except (URLError, TimeoutError, OSError):
        return None, b""


def wait_for_http(
    port: int,
    path: str,
    expected: set[int],
    *,
    timeout: float,
    process: "Launcher | None" = None,
) -> tuple[int, bytes]:
    deadline = time.monotonic() + timeout
    last_status: int | None = None
    while time.monotonic() < deadline:
        last_status, body = request(port, path, timeout=1)
        if last_status in expected:
            return last_status, body
        if process is not None and process.proc.poll() is not None:
            raise AssertionError(
                f"Launcher exited with {process.proc.returncode} while waiting "
                f"for {path}.\n{process.tail()}"
            )
        time.sleep(0.1)
    raise AssertionError(
        f"Timed out waiting for {path}; last HTTP status was {last_status}."
        + (f"\n{process.tail()}" if process else "")
    )


def run_checked(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
    timeout: float = 180,
    input_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_data,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise AssertionError(
            f"Command failed ({result.returncode}): {command[0]}\n"
            f"{sanitize(result.stdout[-5000:])}\n{sanitize(result.stderr[-5000:])}"
        )
    return result


def sanitize(text: str) -> str:
    return re.sub(
        r"(?i)(postgres(?:ql)?(?:\+[^:]+)?://)[^@\s]+@",
        r"\1[redacted]@",
        text,
    )


def pid_running(pid: int) -> bool:
    try:
        if Path(f"/proc/{pid}/stat").exists():
            stat = Path(f"/proc/{pid}/stat").read_text()
            state = stat.rsplit(") ", 1)[1].split(" ", 1)[0]
            return state not in {"Z", "X"}
    except (OSError, IndexError):
        pass
    return False


class DisposableServices:
    """Owns one isolated PostgreSQL container."""

    def __init__(self) -> None:
        self.project = "hi-e14-" + uuid.uuid4().hex[:10]
        self.pg_name = self.project + "-postgres"
        self.pg_port = free_port()
        self.pg_owner_url = ""
        self.pg_runtime_url = ""

    def _docker(self, *args: str, timeout: float = 120) -> str:
        result = subprocess.run(
            ["docker", *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            env=minimal_env(),
        )
        if result.returncode:
            raise RuntimeError(
                f"Docker command failed ({result.returncode}): {args[0]}\n"
                f"{sanitize(result.stderr[-2500:])}"
            )
        return result.stdout.strip()

    def __enter__(self) -> "DisposableServices":
        if sys.version_info[:2] != (3, 12):
            raise RuntimeError(f"Python 3.12 required; found {sys.version.split()[0]}.")
        node_version = subprocess.check_output(
            ["node", "--version"], text=True, env=minimal_env()
        ).strip()
        if not re.fullmatch(r"v22\.\d+\.\d+", node_version):
            raise RuntimeError(f"Node.js 22 required; found {node_version}.")
        pnpm_version = subprocess.check_output(
            ["pnpm", "--version"], text=True, env=minimal_env()
        ).strip()
        if pnpm_version != "10.26.1":
            raise RuntimeError(f"PNPM 10.26.1 required; found {pnpm_version}.")
        if not shutil.which("docker"):
            raise RuntimeError("Docker is required; startup fault tests cannot be skipped.")
        try:
            emit(f"Starting disposable PostgreSQL ({self.project}).")
            self._docker(
                "run", "--detach", "--name", self.pg_name,
                "--publish", f"127.0.0.1:{self.pg_port}:5432",
                "--env", "POSTGRES_DB=horario",
                "--env", "POSTGRES_USER=postgres",
                "--env", f"POSTGRES_PASSWORD={OWNER_PASSWORD}",
                POSTGRES_IMAGE,
            )
            self.pg_owner_url = (
                f"postgresql+psycopg://postgres:{OWNER_PASSWORD}@127.0.0.1:"
                f"{self.pg_port}/horario"
            )
            self.pg_runtime_url = (
                f"postgresql+psycopg://horario_runtime:{RUNTIME_PASSWORD}@127.0.0.1:"
                f"{self.pg_port}/horario"
            )
            self.wait_postgres()
            self.prepare_schema_and_admin()
            emit("Disposable PostgreSQL is migrated with runtime RLS.")
            return self
        except Exception:
            self.close()
            raise

    def wait_postgres(self, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(
                    self.pg_owner_url.replace("postgresql+psycopg://", "postgresql://"),
                    connect_timeout=1,
                ) as conn:
                    conn.execute("SELECT 1")
                return
            except psycopg.Error:
                time.sleep(0.2)
        raise RuntimeError("Disposable PostgreSQL did not become reachable.")

    def prepare_schema_and_admin(self) -> None:
        raw_owner_url = self.pg_owner_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(raw_owner_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL(
                    "CREATE ROLE horario_runtime WITH LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD {}"
                ).format(sql.Literal(RUNTIME_PASSWORD))
            )
        migration_env = minimal_env()
        migration_env.update(
            {
                "DATABASE_URL": self.pg_owner_url,
                "ENVIRONMENT": "development",
                "SESSION_SECRET": SYNTHETIC_SESSION_SECRET,
                "COOKIE_SECURE": "false",
                "PUBLIC_APP_URL": "http://127.0.0.1",
            }
        )
        run_checked(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=migration_env,
            timeout=120,
        )
        run_checked(
            [
                sys.executable, "-m", "app.cli", "bootstrap-platform",
                "--email", ADMIN_EMAIL,
                "--name", "Admin de teste E14",
                "--password-stdin",
            ],
            cwd=BACKEND,
            env=migration_env,
            timeout=60,
            input_data=ADMIN_PASSWORD + "\n",
        )

    def stop_postgres(self) -> None:
        self._docker("stop", "--time", "2", self.pg_name, timeout=20)

    def start_postgres(self) -> None:
        self._docker("start", self.pg_name)
        self.wait_postgres()

    def close(self) -> None:
        for name in (self.pg_name,):
            subprocess.run(
                ["docker", "rm", "--force", name],
                capture_output=True,
                text=True,
                timeout=30,
            )

    def __exit__(self, *_exc: object) -> None:
        self.close()


class Launcher:
    def __init__(self, env: dict[str, str]) -> None:
        self.started_at = time.monotonic()
        self.ready_elapsed_seconds: float | None = None
        self.proc = subprocess.Popen(
            ["bash", str(ROOT / "start-production.sh")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.lines: list[str] = []
        self.reader = threading.Thread(target=self._read_output, daemon=True)
        self.reader.start()

    def _read_output(self) -> None:
        if self.proc.stdout:
            for line in self.proc.stdout:
                self.lines.append(line.rstrip())

    def tail(self) -> str:
        return sanitize("\n".join(self.lines[-50:]))

    def child_pid(self, token: str, timeout: float = 15) -> int:
        label = "API" if token == "uvicorn" else "frontend"
        marker = f"Production {label} process started (pid="
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self.lines:
                if line.startswith(marker) and line.endswith(")."):
                    try:
                        return int(line[len(marker):-2])
                    except ValueError:
                        continue
            if self.proc.poll() is not None:
                break
            time.sleep(0.1)
        raise AssertionError(
            f"Could not find child process matching {token!r}.\n{self.tail()}"
        )

    def wait_ready(self, api_port: int, web_port: int, timeout: float = 45) -> None:
        wait_for_http(api_port, "/api/health", {200}, timeout=timeout, process=self)
        wait_for_http(api_port, "/api/ready", {200}, timeout=timeout, process=self)
        wait_for_http(web_port, "/", {200}, timeout=timeout, process=self)
        wait_for_http(web_port, "/api/health", {200}, timeout=timeout, process=self)
        wait_for_http(web_port, "/api/ready", {200}, timeout=timeout, process=self)
        self.ready_elapsed_seconds = time.monotonic() - self.started_at

    def stop(self, expected_code: int = 143) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        try:
            code = self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = self.proc.wait(timeout=5)
            raise AssertionError(f"Launcher did not stop cleanly.\n{self.tail()}")
        self.reader.join(timeout=2)
        if code != expected_code:
            raise AssertionError(
                f"Expected launcher exit {expected_code}, got {code}.\n{self.tail()}"
            )


def minimal_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "CI": "1",
        "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
        "NPM_CONFIG_STRICT_SSL": "true",
    }
    return env


def launcher_env(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    *,
    runtime_url: str | None = None,
    path: str | None = None,
    startup_timeout: int = 30,
) -> dict[str, str]:
    env = minimal_env()
    env.update(
        {
            "PATH": path or env["PATH"],
            "API_PORT": str(api_port),
            "PORT": str(web_port),
            "NODE_ENV": "production",
            "ENVIRONMENT": "production",
            "HI_NEXT_DIST_DIR": ".next-production",
            "HI_RUNTIME_DATABASE_URL": runtime_url or services.pg_runtime_url,
            "SESSION_SECRET": SYNTHETIC_SESSION_SECRET,
            "COOKIE_SECURE": "true",
            "PUBLIC_APP_URL": "https://e14-homologacao.example.invalid",
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": "2525",
            "SMTP_FROM": "ci-homologacao@example.invalid",
            "HI_RELEASE_SHA": os.environ.get(
                "EXPECTED_RELEASE_SHA", os.environ.get("GITHUB_SHA", "f" * 40)
            ),
            "HI_STARTUP_TIMEOUT_SECONDS": str(startup_timeout),
            "HI_CHILD_SHUTDOWN_SECONDS": "3",
        }
    )
    return env


def launch_ready(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    *,
    path: str | None = None,
) -> Launcher:
    launcher = Launcher(launcher_env(services, api_port, web_port, path=path))
    try:
        launcher.wait_ready(api_port, web_port)
        return launcher
    except Exception:
        if launcher.proc.poll() is None:
            launcher.stop(expected_code=143)
        raise


def assert_root_is_real_app(port: int) -> None:
    status, body = request(port, "/")
    if status != 200 or b"Hor\xc3\xa1rio Inteligente" not in body:
        raise AssertionError(f"GET / did not serve the real application (status {status}).")


def wait_launcher_exit(launcher: Launcher, timeout: float = 20) -> int:
    try:
        code = launcher.proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        launcher.stop()
        raise AssertionError(f"Launcher did not exit after a critical failure.\n{launcher.tail()}") from exc
    launcher.reader.join(timeout=2)
    return code


def wait_for_file(path: Path, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for test synchronization file {path.name}.")


def expect_failed_start(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    *,
    runtime_url: str | None = None,
    path: str | None = None,
) -> None:
    launcher = Launcher(
        launcher_env(
            services,
            api_port,
            web_port,
            runtime_url=runtime_url,
            path=path,
            startup_timeout=15,
        )
    )
    code = wait_launcher_exit(launcher)
    if code == 0:
        raise AssertionError("Launcher accepted a failed critical startup dependency.")
    wait_for_port(web_port, opened=False)
    wait_for_port(api_port, opened=False)
    if not any("stopped before becoming healthy" in line for line in launcher.lines):
        raise AssertionError(f"Startup failure was not diagnosed explicitly.\n{launcher.tail()}")


def login_cookie(api_port: int) -> tuple[str, str]:
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    data = json.dumps(payload).encode()
    req = Request(
        f"http://127.0.0.1:{api_port}/api/auth/login",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://e14-homologacao.example.invalid",
        },
        method="POST",
    )
    with urlopen(req, timeout=HTTP_TIMEOUT) as response:
        body = json.loads(response.read())
        cookies = response.headers.get_all("Set-Cookie") or []
    cookie = "; ".join(item.split(";", 1)[0] for item in cookies)
    if not cookie or not body.get("csrf"):
        raise AssertionError("Synthetic admin login did not create a session and CSRF token.")
    return cookie, body["csrf"]


def auth_me(api_port: int, cookie: str) -> tuple[int | None, bytes]:
    return request(
        api_port,
        "/api/auth/me",
        headers={"Cookie": cookie},
    )


def test_startup_repeated(services: DisposableServices, api_port: int, web_port: int) -> None:
    for index in range(1, 4):
        launcher = launch_ready(services, api_port, web_port)
        assert_root_is_real_app(web_port)
        health, body = request(api_port, "/api/health")
        assert health == 200 and json.loads(body).get("status") == "ok"
        readiness, ready_body = request(api_port, "/api/ready")
        assert readiness == 200 and json.loads(ready_body).get("status") == "ready"
        release, body = request(api_port, "/api/release")
        payload = json.loads(body)
        if release != 200 or payload.get("release_sha") != launcher_env(
            services, api_port, web_port
        )["HI_RELEASE_SHA"]:
            raise AssertionError(f"Release identity endpoint failed: status {release}.")
        emit(
            f"PASS startup repetition {index}/3: GET /={200}, direct health={health}, "
            f"direct ready={readiness}, proxied health/ready=200/200, release={release}; "
            f"ready in {launcher.ready_elapsed_seconds:.2f}s."
        )
        if index == 1:
            emit(f"Startup log evidence: {launcher.tail().replace(chr(10), ' | ')}")
        launcher.stop()
        wait_for_port(web_port, opened=False)
        wait_for_port(api_port, opened=False)


def test_slow_backend(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    temp: Path,
) -> None:
    wrapper_dir = temp / "slow-python"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "python"
    api_started = wrapper_dir / "api-started"
    release_api = wrapper_dir / "release-api"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"uvicorn\" ]; then\n"
        f"  : > {api_started}\n"
        f"  count=0; while [ ! -e {release_api} ] && [ \"$count\" -lt 300 ]; do "
        "sleep 0.1; count=$((count + 1)); done\n"
        "fi\n"
        f"exec {sys.executable!s} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    path = str(wrapper_dir) + os.pathsep + os.environ["PATH"]
    launcher = Launcher(launcher_env(services, api_port, web_port, path=path))
    try:
        wait_for_file(api_started)
        root_before, _ = wait_for_http(web_port, "/", {503}, timeout=20, process=launcher)
        api_before, _ = request(api_port, "/api/health")
        if api_before == 200:
            raise AssertionError("API unexpectedly became live before the test released startup.")
        release_api.touch()
        launcher.wait_ready(api_port, web_port, timeout=30)
        emit(
            f"PASS slow backend: during startup GET /={root_before}, API health={api_before}; "
            f"after release root/health/ready=200, ready in {launcher.ready_elapsed_seconds:.2f}s."
        )
    finally:
        launcher.stop()


def test_slow_frontend(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    temp: Path,
) -> None:
    real_node = shutil.which("node")
    if not real_node:
        raise RuntimeError("Node binary disappeared from PATH.")
    wrapper_dir = temp / "slow-node"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "node"
    frontend_started = wrapper_dir / "frontend-started"
    release_frontend = wrapper_dir / "release-frontend"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"case \"$*\" in *server.js*)\n"
        f"  : > {frontend_started}\n"
        f"  count=0; while [ ! -e {release_frontend} ] && [ \"$count\" -lt 300 ]; do "
        "sleep 0.1; count=$((count + 1)); done\n"
        ";; esac\n"
        f"exec {real_node!s} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    path = str(wrapper_dir) + os.pathsep + os.environ["PATH"]
    launcher = Launcher(launcher_env(services, api_port, web_port, path=path))
    try:
        wait_for_file(frontend_started)
        api_ready, _ = wait_for_http(api_port, "/api/ready", {200}, timeout=20, process=launcher)
        root_before, _ = request(web_port, "/")
        if root_before == 200:
            raise AssertionError("Frontend unexpectedly became live before the test released startup.")
        release_frontend.touch()
        launcher.wait_ready(api_port, web_port, timeout=30)
        emit(
            f"PASS slow frontend: API ready={api_ready}, root before start={root_before}; "
            f"after release root/health/ready=200, ready in {launcher.ready_elapsed_seconds:.2f}s."
        )
    finally:
        launcher.stop()


def test_postgres_unavailable_at_start(
    services: DisposableServices,
    api_port: int,
    web_port: int,
) -> None:
    services.stop_postgres()
    try:
        expect_failed_start(services, api_port, web_port)
        emit("PASS PostgreSQL unavailable at startup: FastAPI fails closed; Next is cleaned up.")
    finally:
        services.start_postgres()


def test_rls_failure_at_start(
    services: DisposableServices,
    api_port: int,
    web_port: int,
) -> None:
    raw_owner_url = services.pg_owner_url.replace(
        "postgresql+psycopg://", "postgresql://"
    )
    with psycopg.connect(raw_owner_url, autocommit=True) as conn:
        conn.execute("ALTER ROLE horario_runtime BYPASSRLS")
    try:
        expect_failed_start(services, api_port, web_port)
        emit("PASS invalid RLS runtime role at startup: FastAPI refuses to start.")
    finally:
        with psycopg.connect(raw_owner_url, autocommit=True) as conn:
            conn.execute("ALTER ROLE horario_runtime NOBYPASSRLS")


def test_postgres_loss_and_recovery(
    services: DisposableServices,
    api_port: int,
    web_port: int,
) -> None:
    launcher = launch_ready(services, api_port, web_port)
    try:
        cookie, _csrf = login_cookie(api_port)
        status, _ = auth_me(api_port, cookie)
        if status != 200:
            raise AssertionError(f"Pre-fault authenticated operation failed: {status}.")
        services.stop_postgres()
        ready, _ = request(api_port, "/api/ready", timeout=10)
        root_status, _ = request(web_port, "/")
        blocked, _ = auth_me(api_port, cookie)
        health, _ = request(api_port, "/api/health")
        if ready != 503 or root_status != 503 or blocked is None \
            or 200 <= blocked < 300 or health != 200:
            raise AssertionError(
                f"PostgreSQL loss contract mismatch: health={health}, "
                f"ready={ready}, root={root_status}, authenticated_operation={blocked}."
            )
        services.start_postgres()
        launcher.wait_ready(api_port, web_port, timeout=30)
        recovered, _ = auth_me(api_port, cookie)
        if recovered != 200:
            raise AssertionError(f"Authenticated operation did not recover after PostgreSQL: {recovered}.")
        emit("PASS PostgreSQL loss/recovery: liveness remains, readiness and DB operation fail then recover.")
    finally:
        launcher.stop()


def test_critical_process_exit(
    services: DisposableServices,
    api_port: int,
    web_port: int,
    *,
    process_token: str,
    expected_port_to_close: int,
    label: str,
) -> None:
    launcher = launch_ready(services, api_port, web_port)
    try:
        api_pid = launcher.child_pid("uvicorn")
        frontend_pid = launcher.child_pid("server.js")
        child = api_pid if process_token == "uvicorn" else frontend_pid
        sibling = frontend_pid if process_token == "uvicorn" else api_pid
        subprocess.run(["kill", "-KILL", str(child)], check=True)
        code = wait_launcher_exit(launcher)
        if code == 0:
            raise AssertionError(f"Launcher returned success after {label} exited unexpectedly.")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and pid_running(sibling):
            time.sleep(0.1)
        if pid_running(sibling):
            raise AssertionError(f"Sibling process {sibling} remained after {label} exit.\n{launcher.tail()}")
        wait_for_port(expected_port_to_close, opened=False)
        emit(f"PASS unexpected {label} termination: launcher failed and the sibling process was stopped.")
    finally:
        if launcher.proc.poll() is None:
            launcher.stop()


def test_sigterm_and_restart(
    services: DisposableServices,
    api_port: int,
    web_port: int,
) -> None:
    first = launch_ready(services, api_port, web_port)
    child_pids = [
        first.child_pid("uvicorn"),
        first.child_pid("server.js"),
    ]
    first.stop(expected_code=143)
    for pid in child_pids:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and pid_running(pid):
            time.sleep(0.1)
        if pid_running(pid):
            raise AssertionError(f"Child process {pid} survived SIGTERM cleanup.")
    wait_for_port(web_port, opened=False)
    wait_for_port(api_port, opened=False)
    second = launch_ready(services, api_port, web_port)
    try:
        emit("PASS SIGTERM and restart: children stopped, ports released, same service restarts cleanly.")
    finally:
        second.stop()


def build_production(api_port: int) -> None:
    build_env = minimal_env()
    build_env.update(
        {
            "API_PORT": str(api_port),
            "HI_NEXT_DIST_DIR": ".next-production",
            "API_BACKEND_URL": f"http://127.0.0.1:{api_port}",
        }
    )
    emit("Building Next standalone with the frozen frontend dependencies.")
    run_checked(
        ["bash", str(ROOT / "build-production.sh")],
        cwd=ROOT,
        env=build_env,
        timeout=600,
    )
    candidates = [
        ROOT / "frontend/.next-production/standalone/horario-escolar/frontend/server.js",
        ROOT / "frontend/.next-production/standalone/frontend/server.js",
        ROOT / "frontend/.next-production/standalone/server.js",
    ]
    if not any(candidate.is_file() for candidate in candidates):
        raise AssertionError("Production standalone server.js was not emitted.")
    if not (ROOT / "frontend/.next-production/standalone").is_dir():
        raise AssertionError("Production build did not preserve .next-production/standalone.")
    if (ROOT / "frontend/.next-production/routes-manifest.json").is_file():
        manifest = json.loads(
            (ROOT / "frontend/.next-production/routes-manifest.json").read_text()
        )
        rewrites = [item for group in manifest["rewrites"].values() for item in group]
        if not any(
            item.get("source") == "/api/:path*"
            and f"127.0.0.1:{api_port}" in item.get("destination", "")
            for item in rewrites
        ):
            raise AssertionError("Built Next rewrite does not target the runtime API port.")


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit(f"Python 3.12 required; found {sys.version.split()[0]}.")
    api_port = free_port()
    web_port = free_port()
    if api_port == web_port:
        web_port = free_port()

    # Use a scratch copy for frontend dependency installation and build outputs
    # only in the ignored .next-production tree; source files remain untouched.
    with DisposableServices() as services:
        build_production(api_port)
        with tempfile.TemporaryDirectory(prefix="hi-e14-fault-injection-") as temp_dir:
            temp = Path(temp_dir)
            test_startup_repeated(services, api_port, web_port)
            test_slow_backend(services, api_port, web_port, temp)
            test_slow_frontend(services, api_port, web_port, temp)
            test_postgres_unavailable_at_start(services, api_port, web_port)
            test_rls_failure_at_start(services, api_port, web_port)
            test_postgres_loss_and_recovery(services, api_port, web_port)
            test_critical_process_exit(
                services,
                api_port,
                web_port,
                process_token="uvicorn",
                expected_port_to_close=web_port,
                label="FastAPI",
            )
            test_critical_process_exit(
                services,
                api_port,
                web_port,
                process_token="server.js",
                expected_port_to_close=api_port,
                label="Next.js",
            )
            test_sigterm_and_restart(services, api_port, web_port)
    emit("STARTUP_FAULT_MATRIX_PASSED")


if __name__ == "__main__":
    main()
