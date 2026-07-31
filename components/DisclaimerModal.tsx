"use client";

import { useSyncExternalStore } from "react";
import { useT } from "@/lib/i18n/LanguageProvider";
import { LanguageToggle } from "./LanguageToggle";

// Per browser session, not per browser. The app deliberately re-asks (and re-opens in
// English) each new session, which is also why the locale itself lives in sessionStorage.
const ACCEPTED_KEY = "concussio_disclaimer_accepted";

// A minimal external store so the sessionStorage read is hydration-safe: React uses the
// server snapshot for SSR and the first hydration pass, then re-reads on the client. Reading
// storage during render (or via setState in an effect) would mismatch or cascade instead.
let listeners: Array<() => void> = [];

const subscribe = (onChange: () => void) => {
    listeners.push(onChange);
    return () => {
        listeners = listeners.filter(listener => listener !== onChange);
    };
};

const getSnapshot = () => sessionStorage.getItem(ACCEPTED_KEY) === "true";

// On the server, act as though it were accepted so the modal is not part of the SSR markup.
const getServerSnapshot = () => true;

const acceptDisclaimer = () => {
    sessionStorage.setItem(ACCEPTED_KEY, "true");
    for (const listener of listeners) listener();
};

export function DisclaimerModal() {
    const t = useT();
    const accepted = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

    if (accepted) return null;

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="disclaimer-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
        >
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
                <div className="flex items-start justify-between gap-4 px-6 pt-6">
                    <h2 id="disclaimer-title" className="text-xl font-bold text-gray-900">
                        {t("disclaimer.title")}
                    </h2>
                    {/* Choosing a language here sets it for the whole app. */}
                    <LanguageToggle showLabel={false} />
                </div>
                <div className="p-6 pt-4 overflow-y-auto">
                    <div className="space-y-4 text-gray-700 text-sm leading-relaxed">
                        <p>{t("disclaimer.p1")}</p>
                        <p className="font-semibold text-red-600">{t("disclaimer.p2")}</p>
                        <p>{t("disclaimer.p3")}</p>
                        <p>{t("disclaimer.p4")}</p>
                        <p>{t("disclaimer.p5")}</p>
                    </div>
                </div>
                <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end">
                    <button
                        onClick={acceptDisclaimer}
                        className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                        {t("disclaimer.accept")}
                    </button>
                </div>
            </div>
        </div>
    );
}
