import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = (
  process.env.API_BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");
const READINESS_TIMEOUT_MS = 1500;

export async function middleware(request: NextRequest) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return NextResponse.next();
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), READINESS_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/api/ready`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (response.ok) return NextResponse.next();
  } catch {
    // Do not claim the app is ready when the API or a required dependency is down.
  } finally {
    clearTimeout(timeout);
  }

  return new NextResponse("Service Unavailable\n", {
    status: 503,
    headers: {
      "Cache-Control": "no-store, max-age=0",
      "Retry-After": "1",
    },
  });
}

export const config = {
  matcher: ["/"],
};
