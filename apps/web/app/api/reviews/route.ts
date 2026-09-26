import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export async function GET(_req: NextRequest) {
  return proxy("/api/reviews", { cache: "no-store" });
}
