import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxy("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
