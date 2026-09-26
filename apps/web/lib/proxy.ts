import { NextResponse } from "next/server";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

/**
 * Forwards a request to the Blast Radius FastAPI backend and returns a clean
 * JSON response either way — including when the backend can't be reached at
 * all (ECONNREFUSED), which `fetch` throws rather than returning a response
 * for. Without this, an unreachable backend surfaces as Next.js's generic,
 * unstyled 500 page with no indication of what actually went wrong; with it,
 * every route returns `{ error: "<readable message>" }` with a proper status
 * (502 for "can't reach the backend at all"), and the UI (lib/api.ts) shows
 * that message instead of a bare "Failed to ...: 500".
 */
export async function proxy(path: string, init?: RequestInit): Promise<NextResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        error: `Can't reach the Blast Radius API at ${API_BASE}. Is the backend running? (cd server && uvicorn main:app --port 8010)`,
        detail,
      },
      { status: 502 }
    );
  }

  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    // The backend returned something that isn't JSON (e.g. its own 500 HTML
    // page, or nothing) — still surface a clean, readable error instead of
    // forwarding an empty/garbled body.
    return NextResponse.json(
      { error: `The Blast Radius API returned an unexpected (non-JSON) response (HTTP ${res.status}).`, detail: text.slice(0, 500) },
      { status: 502 }
    );
  }
  return NextResponse.json(data, { status: res.status });
}
