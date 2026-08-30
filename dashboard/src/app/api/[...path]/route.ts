import { NextRequest, NextResponse } from "next/server";

const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";

/**
 * App Router API catch-all proxy.
 *
 * Replaces Next.js rewrites proxy which has an unconfigurable 30-second socket
 * timeout in the dev server. Long-running AI pipelines (channel audits, roadmaps,
 * video analyses) often run for 30-60s. This Route Handler forwards requests
 * without the 30s abort ceiling while preserving all cookies, headers, and bodies.
 */
async function forwardRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const pathStr = path.join("/");
  const targetUrl = new URL(`/api/${pathStr}${req.nextUrl.search}`, BACKEND_ORIGIN);

  const headers = new Headers(req.headers);
  headers.delete("host");

  let body: BodyInit | undefined = undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.blob();
  }

  try {
    const res = await fetch(targetUrl.toString(), {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });

    const resHeaders = new Headers(res.headers);
    // Remove content-encoding so Next.js handles encoding transparently
    resHeaders.delete("content-encoding");

    return new NextResponse(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: resHeaders,
    });
  } catch (error: unknown) {
    const errMessage = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      { detail: `Backend proxy error: ${errMessage}` },
      { status: 502 }
    );
  }
}

export const GET = forwardRequest;
export const POST = forwardRequest;
export const PUT = forwardRequest;
export const PATCH = forwardRequest;
export const DELETE = forwardRequest;
export const HEAD = forwardRequest;
export const OPTIONS = forwardRequest;
