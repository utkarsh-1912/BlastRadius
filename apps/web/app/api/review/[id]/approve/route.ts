import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

// The only route in this app that can trigger an AWS IAM write — it does
// nothing but forward the human's explicit click to the backend's
// commit_and_verify(), which itself refuses anything not in
// 'awaiting_approval' state (see server/agent/orchestrator.py).
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/api/review/${id}/approve`, { method: "POST" });
}
