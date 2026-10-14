import type { NextConfig } from "next";
import fs from "node:fs";
import path from "node:path";

const projectRoot = process.cwd();
const replitWorkspaceRoot = path.resolve(projectRoot, "../..");
const isReplitWorkspace =
  fs.existsSync(path.join(replitWorkspaceRoot, "pnpm-workspace.yaml")) &&
  fs.existsSync(path.join(replitWorkspaceRoot, "horario-escolar", "frontend", "package.json"));

const config: NextConfig = {
  // Replit builds into an isolated directory so Next dev cannot overwrite the
  // published standalone output.
  distDir: process.env.HI_NEXT_DIST_DIR ?? ".next",
  // Preserve the Replit monorepo's nested standalone server path. The GitHub
  // projection keeps frontend at the repository root, so trace from the app
  // there and keep CI's standalone/server.js startup path valid.
  outputFileTracingRoot: isReplitWorkspace ? replitWorkspaceRoot : projectRoot,
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};
export default config;
