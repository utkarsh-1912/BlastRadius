import { PermissionCheckResult, ReviewRun, ReviewSummary } from "./types";

/**
 * Every route in app/api/* returns a clean JSON error body on failure —
 * either `{ error, detail }` (synthesized by lib/proxy.ts when the backend
 * can't be reached at all, or returned something unparseable) or FastAPI's
 * own `{ detail }` shape (e.g. a 404/409 from a real endpoint). This pulls
 * out whichever is present so callers throw a message worth actually
 * showing, instead of a bare "Failed to X: 500".
 */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.error === "string") return body.error;
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON at all — fall through to the generic message
  }
  return `${fallback} (HTTP ${res.status})`;
}

export async function createReview(request: string): Promise<ReviewRun> {
  const res = await fetch("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to create review"));
  return res.json();
}

export async function getReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to fetch review"));
  return res.json();
}

export async function approveReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to approve review"));
  return res.json();
}

export async function rejectReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}/reject`, { method: "POST" });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to reject review"));
  return res.json();
}

export async function listReviews(): Promise<ReviewSummary[]> {
  const res = await fetch("/api/reviews", { cache: "no-store" });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to list reviews"));
  return res.json();
}

export async function checkPermission(roleName: string, action: string, lookbackDays = 90): Promise<PermissionCheckResult> {
  const res = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role_name: roleName, action, lookback_days: lookbackDays }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, "Failed to check permission"));
  return res.json();
}
