"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarRange, BarChart3 } from "lucide-react";

const TABS = [
  { href: "/planner", label: "Planner", icon: CalendarRange },
  { href: "/planner-analysis", label: "Analysis", icon: BarChart3 },
];

export default function PlannerTabs() {
  const pathname = usePathname();

  return (
    <div className="border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex items-center gap-1 -mb-px">
          {TABS.map((tab) => {
            const active = pathname === tab.href;
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  active
                    ? "border-blue-500 text-blue-300"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/10"
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
