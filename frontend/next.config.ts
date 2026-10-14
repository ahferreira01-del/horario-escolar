import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  // Replit builds into an isolated directory so Next dev cannot overwrite the
  // published standalone output.
  distDir: process.env.HI_NEXT_DIST_DIR ?? ".next",
  // The app lives below the monorepo root; anchor tracing there rather than
  // allowing an enclosing Replit workspace or another worktree to be selected.
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};
export default config;
