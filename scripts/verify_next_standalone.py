#!/usr/bin/env python3
"""Fail if the Next standalone artifact depends on files outside itself."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def locate_server(standalone_root: Path) -> Path:
    candidates = (
        standalone_root / "horario-escolar" / "frontend" / "server.js",
        standalone_root / "frontend" / "server.js",
        standalone_root / "server.js",
    )
    matches = [candidate for candidate in candidates if candidate.is_file()]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one standalone server.js under {standalone_root}; "
            f"found {len(matches)}."
        )
    return matches[0]


def verify_standalone(standalone_root: Path) -> Path:
    root = standalone_root.resolve(strict=True)
    server = locate_server(root).resolve(strict=True)
    if not server.is_relative_to(root):
        raise RuntimeError(f"Standalone server escapes its artifact directory: {server}")

    for entry in root.rglob("*"):
        if not entry.is_symlink():
            continue
        try:
            target = entry.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RuntimeError(f"Broken standalone symlink: {entry.relative_to(root)}") from error
        if not target.is_relative_to(root):
            raise RuntimeError(
                f"Standalone symlink escapes artifact: {entry.relative_to(root)}"
            )

    verify_runtime = r"""
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const server = fs.realpathSync(process.argv[1]);
const root = fs.realpathSync(process.argv[2]);
const requireFromServer = createRequire(server);
const startServer = fs.realpathSync(
  requireFromServer.resolve("next/dist/server/lib/start-server.js")
);
const cpuProfile = path.join(path.dirname(startServer), "cpu-profile.js");
const realCpuProfile = fs.realpathSync(cpuProfile);
const within = (file) => {
  const relative = path.relative(root, file);
  return relative !== "" && !relative.startsWith(".." + path.sep) &&
    !path.isAbsolute(relative);
};
if (!within(startServer) || !within(realCpuProfile)) {
  throw new Error("Next runtime modules resolve outside the standalone artifact");
}
console.log("NEXT_STANDALONE_RUNTIME_MODULES_PASS");
"""
    environment = os.environ.copy()
    environment["NODE_PATH"] = ""
    result = subprocess.run(
        ["node", "-e", verify_runtime, str(server), str(root)],
        cwd=server.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = "\n".join((result.stdout, result.stderr)).strip()
        raise RuntimeError(f"Next runtime files are incomplete in standalone:\n{detail[-3000:]}")

    print(f"NEXT_STANDALONE_PORTABLE_PASS={server.relative_to(root)}")
    print(result.stdout.strip())
    return server


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_next_standalone.py <standalone-directory>")
    try:
        verify_standalone(Path(sys.argv[1]))
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
