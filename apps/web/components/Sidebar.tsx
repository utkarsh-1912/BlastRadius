"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FilePlus2, History, ShieldCheck, Radar } from "lucide-react";

const NAV = [
  { href: "/", label: "New Review", icon: FilePlus2 },
  { href: "/reviews", label: "History", icon: History },
  { href: "/check", label: "Check a Permission", icon: ShieldCheck },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
          <Radar className="h-4 w-4 text-white" strokeWidth={2} />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight text-slate-900">Blast Radius</div>
          <div className="text-[11px] leading-tight text-slate-400">AWS IAM Reviews</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          // Exact match only — a review detail page (/reviews/<id>) is one path
          // segment deeper than the History list (/reviews) and belongs to
          // neither "New Review" nor "History"; it should light up neither tab
          // rather than falsely highlighting History via a startsWith() match.
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                active ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <Icon className="h-4 w-4" strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-100 px-5 py-4">
        <p className="text-[11px] leading-snug text-slate-400">
          TrueFoundry × Polaris
          <br />
          Agents That Act
        </p>
      </div>
    </aside>
  );
}
