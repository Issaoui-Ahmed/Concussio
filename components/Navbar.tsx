"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useLocale, useT } from "@/lib/i18n/LanguageProvider";
import { LanguageToggle } from "./LanguageToggle";

export function Navbar() {
    const pathname = usePathname();
    const isAdminRoute = pathname.startsWith("/admin");
    const t = useT();
    const { locale } = useLocale();

    // Admin labels stay hardcoded English — that route mounts no LanguageProvider.
    const navItems = isAdminRoute
        ? [
            { name: "Batch Answers", href: "/admin/batch" },
            { name: "Scraping", href: "/admin/scraping" },
            { name: "Fuel IX", href: "/admin/fuel-ix/copilots" },
        ]
        : [
            { name: t("nav.chatbot"), href: "/" },
            { name: t("nav.about"), href: "/about" },
            { name: t("nav.sources"), href: "/sources" },
        ];

    return (
        <nav className="bg-white border-b border-[#ECECF1] h-16 flex items-center px-4 md:px-6 shrink-0 z-50">
            <div className="flex items-center mr-8">
                {/* The French mark carries three subtitle lines to the English mark's two, so
                    at a shared height its wordmark reads noticeably smaller. Giving it a
                    taller box evens them out. Admin has no provider, so locale is "en" there. */}
                <div className={cn("relative w-48", locale === "fr" ? "h-14" : "h-12")}>
                    <Image
                        src={t("nav.logo")}
                        alt={t("nav.logoAlt")}
                        fill
                        className="object-contain object-left"
                        priority
                    />
                </div>
            </div>

            <div className="flex items-center gap-1 sm:gap-4 overflow-x-auto">
                {navItems.map((item) => {
                    const isActive = item.href === "/"
                        ? pathname === "/"
                        : pathname === item.href || pathname.startsWith(`${item.href}/`);
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "px-3 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
                                isActive
                                    ? "bg-[#e6efff] text-[#00417d]"
                                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                            )}
                        >
                            {item.name}
                        </Link>
                    );
                })}
            </div>

            {!isAdminRoute && (
                <div className="ml-auto pl-4 shrink-0">
                    <LanguageToggle />
                </div>
            )}
        </nav>
    );
}
