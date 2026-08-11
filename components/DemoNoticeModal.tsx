"use client";

import { useT } from "@/lib/i18n/LanguageProvider";
import { EntryDialog } from "./EntryDialog";

/**
 * First of the two acknowledgements, shown once the password gate is passed: what this
 * deployment is (a prototype under evaluation) and what not to type into it.
 */
export function DemoNoticeModal({ onContinue }: { onContinue: () => void }) {
    const t = useT();

    return (
        <EntryDialog
            id="demo-notice"
            title={t("demo.title")}
            actionLabel={t("demo.continue")}
            onAction={onContinue}
        >
            <p>{t("demo.p1")}</p>
            <p className="font-semibold text-gray-900">{t("demo.p2")}</p>
            {/* The one instruction with consequences for someone other than the reader. */}
            <p className="font-semibold text-red-600">{t("demo.p3")}</p>
            <p>{t("demo.p4")}</p>
            <p>{t("demo.p5")}</p>
        </EntryDialog>
    );
}
