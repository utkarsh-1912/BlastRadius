import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/api/review/${id}`, { cache: "no-store" });
}
