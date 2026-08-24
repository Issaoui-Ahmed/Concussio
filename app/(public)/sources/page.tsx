"use client";

import { useT } from "@/lib/i18n/LanguageProvider";

export default function SourcesPage() {
    const t = useT();

    return (
        <div className="max-w-4xl mx-auto py-8 px-4 sm:py-12 sm:px-6 overflow-y-auto h-full">
            <h1 className="text-2xl sm:text-3xl font-bold mb-4 sm:mb-6 text-[#00417d]">{t("sources.title")}</h1>
            <div className="bg-white p-5 sm:p-8 rounded-xl shadow-sm border border-gray-100 space-y-4 text-gray-700 leading-relaxed">
                <p>{t("sources.intro")}</p>
                <h2 className="text-xl font-semibold text-[#00417d] mt-4">{t("sources.primaryHeading")}</h2>
                <ul className="list-disc list-inside space-y-2 ml-2">
                    <li>
                        <strong>{t("sources.item1.label")}</strong> {t("sources.item1.body")}
                    </li>
                    <li>
                        <strong>{t("sources.item2.label")}</strong> {t("sources.item2.body")}
                    </li>
                </ul>
                <div className="mt-6 p-4 bg-[#e6efff] rounded-lg border border-[#00417d]/20">
                    <p className="text-sm text-[#00417d]">
                        <strong>{t("sources.disclaimerLabel")}</strong> {t("sources.disclaimerBody")}
                    </p>
                </div>
            </div>
        </div>
    );
}
