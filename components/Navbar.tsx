"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function Navbar() {
    const pathname = usePathname();

    const navItems = [
        { name: "Chatbot", href: "/" },
        { name: "About us", href: "/about" },
        { name: "Source of information", href: "/sources" },
    ];

    return (
        <nav className="bg-white border-b border-[#ECECF1] h-16 flex items-center px-4 md:px-6 shrink-0 z-50">
            <div className="flex items-center mr-8">
                <div className="relative w-48 h-12">
                    <Image
                        src="/logo.png"
                        alt="ConcussCare Logo"
                        fill
                        className="object-contain object-left"
                        priority
                    />
                </div>
            </div>

            <div className="flex items-center gap-1 sm:gap-4 overflow-x-auto">
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
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
        </nav>
    );
}
