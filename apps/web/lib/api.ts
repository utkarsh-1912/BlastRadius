import { ReviewRun } from "./types";

export async function createReview(request: string): Promise<ReviewRun> {
  const res = await fetch("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request }),
  });
  if (!res.ok) throw new Error(`Failed to create review: ${res.status}`);
  return res.json();
}

export async function getReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch review: ${res.status}`);
  return res.json();
}

export async function approveReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to approve review: ${res.status}`);
  return res.json();
}

export async function rejectReview(id: string): Promise<ReviewRun> {
  const res = await fetch(`/api/review/${id}/reject`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to reject review: ${res.status}`);
  return res.json();
}
