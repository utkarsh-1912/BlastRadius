import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  const prefix = req.nextUrl.searchParams.get("prefix");
  const qs = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
  return proxy(`/api/roles${qs}`, { cache: "no-store" });
}
