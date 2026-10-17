import type { NextConfig } from "next";
import fs from "node:fs";
import path from "node:path";

const projectRoot = process.cwd();
const replitWorkspaceRoot = path.resolve(projectRoot, "../..");
const isReplitWorkspace =
  fs.existsSync(path.join(replitWorkspaceRoot, "pnpm-workspace.yaml")) &&
  fs.existsSync(path.join(replitWorkspaceRoot, "horario-escolar", "frontend", "package.json"));
const outputFileTracingRoot = isReplitWorkspace
  ? replitWorkspaceRoot
  : path.resolve(projectRoot, "..");

const config: NextConfig = {
  // Replit builds into an isolated directory so Next dev cannot overwrite the
  // published standalone output.
  distDir: process.env.HI_NEXT_DIST_DIR ?? ".next",
  // Trace from the workspace root so PNPM's physical node_modules/.pnpm tree
  // remains inside the standalone artifact in both the flat GitHub and nested
  // Replit layouts.
  outputFileTracingRoot,
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};
export default config;
