import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

// The only route in this app that can trigger an AWS IAM write — it does
// nothing but forward the human's explicit click to the backend's
// commit_and_verify(), which itself refuses anything not in
// 'awaiting_approval' state (see server/agent/orchestrator.py).
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${API_BASE}/api/review/${id}/approve`, { method: "POST" });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
