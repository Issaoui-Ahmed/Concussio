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
        // Two rows on a phone, one on md+. The logo, three link labels and the toggle add up
        // to well over a phone's width, so side by side they push each other off the screen.
        // min-h-16, not h-16: just at the md breakpoint the single row is a few pixels too
        // narrow for the links, and a fixed height clips the line they wrap onto.
        <nav className="bg-white border-b border-[#ECECF1] flex flex-col gap-1 py-2 short:flex-row short:items-center short:gap-0 short:py-0 md:min-h-16 md:flex-row md:items-center md:gap-0 md:py-0 px-3 sm:px-4 md:px-6 shrink-0 z-50">
            <div className="flex items-center justify-between gap-2 short:mr-4 md:mr-8">
                {/* The French mark carries three subtitle lines to the English mark's two, so
                    at a shared height its wordmark reads noticeably smaller. Giving it a
                    taller box evens them out. Admin has no provider, so locale is "en" there. */}
                <div className={cn("relative w-40 short:w-32 md:w-48 shrink-0", locale === "fr" ? "h-11 short:h-9 md:h-14" : "h-10 short:h-8 md:h-12")}>
                    <Image
                        src={t("nav.logo")}
                        alt={t("nav.logoAlt")}
                        fill
                        className="object-contain object-left"
                        priority
                    />
                </div>

                {/* The toggle rides on the logo row while the navbar is stacked, and moves to
                    the far right once it collapses to a single row. */}
                {!isAdminRoute && (
                    <div className="short:hidden md:hidden">
                        <LanguageToggle showLabel={false} />
                    </div>
                )}
            </div>

            {/* Wraps rather than scrolls: on the narrowest phones the three French labels are
                wider than the row, and a second line shows all of them where a scroller hides
                one. The tight row gap keeps that second line cheap. */}
            <div className="flex flex-wrap items-center gap-x-1 gap-y-0.5 short:gap-1 sm:gap-4">
                {navItems.map((item) => {
                    const isActive = item.href === "/"
                        ? pathname === "/"
                        : pathname === item.href || pathname.startsWith(`${item.href}/`);
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                // Tighter below sm so the French labels ("Robot
                                // conversationnel", "Sources d'information") fit a phone
                                // without the row having to wrap. A sideways phone is wide
                                // enough for the roomier styling but cannot spare the second
                                // row it would cost, so it keeps the compact one.
                                "px-2 sm:px-3 short:px-2 py-2 short:py-1.5 rounded-md text-xs sm:text-sm short:text-xs font-medium transition-colors whitespace-nowrap",
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
                <div className="hidden short:block md:block ml-auto pl-4 shrink-0">
                    <LanguageToggle />
                </div>
            )}
        </nav>
    );
}
