"use client";

import { useLocale, useT, type Locale } from "@/lib/i18n/LanguageProvider";

const LOCALES: Locale[] = ["en", "fr"];

interface LanguageToggleProps {
    /** Renders the "Language" caption. Omitted inside the compact disclaimer header. */
    showLabel?: boolean;
}

export function LanguageToggle({ showLabel = true }: LanguageToggleProps) {
    const { locale, setLocale } = useLocale();
    const t = useT();

    return (
        <div className="flex items-center gap-2">
            {showLabel && (
                <span className="text-xs font-medium text-gray-400">{t("nav.languageLabel")}</span>
            )}
            <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
                {LOCALES.map(item => (
                    <button
                        key={item}
                        type="button"
                        onClick={() => setLocale(item)}
                        aria-pressed={locale === item}
                        className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                            locale === item
                                ? "bg-[#00417d] text-white"
                                : "text-gray-600 hover:bg-gray-100"
                        }`}
                    >
                        {item.toUpperCase()}
                    </button>
                ))}
            </div>
        </div>
    );
}
