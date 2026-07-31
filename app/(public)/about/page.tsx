"use client";

import { useT } from "@/lib/i18n/LanguageProvider";

export default function AboutPage() {
    const t = useT();
    const brand = t("about.p1.brand");
    const [beforeBrand, ...afterBrand] = t("about.p1").split(brand);

    return (
        <div className="max-w-4xl mx-auto py-12 px-6 overflow-y-auto h-full">
            <h1 className="text-3xl font-bold mb-6 text-[#00417d]">{t("about.title")}</h1>
            <div className="bg-white p-8 rounded-xl shadow-sm border border-gray-100 space-y-4 text-gray-700 leading-relaxed">
                <p>
                    {beforeBrand}
                    <span className="font-semibold text-[#00417d]">{brand}</span>
                    {afterBrand.join(brand)}
                </p>
                <p>{t("about.p2")}</p>
                <p>{t("about.p3")}</p>
            </div>
        </div>
    );
}
