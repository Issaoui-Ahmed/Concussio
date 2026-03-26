"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const tabs = [
  { name: "Copilots", href: "/admin/fuel-ix/copilots" },
  { name: "Vector Stores", href: "/admin/fuel-ix/vector-stores" },
];

export function FuelIxTabs() {
  const pathname = usePathname();

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-1 shadow-sm">
      <div className="flex flex-wrap gap-1">
        {tabs.map((tab) => {
          const isActive = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-[#e6efff] text-[#00417d]"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              )}
            >
              {tab.name}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
