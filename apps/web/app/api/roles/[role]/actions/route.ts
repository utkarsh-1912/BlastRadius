import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ role: string }> }) {
  const { role } = await params;
  return proxy(`/api/roles/${encodeURIComponent(role)}/actions`, { cache: "no-store" });
}
