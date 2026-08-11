"use client";

import { useT } from "@/lib/i18n/LanguageProvider";
import { EntryDialog } from "./EntryDialog";

/**
 * Second of the two acknowledgements. Which step is showing is decided in `lib/entryFlow.ts`,
 * not here, so this modal cannot appear over the demo/testing notice.
 */
export function DisclaimerModal({ onAccept }: { onAccept: () => void }) {
    const t = useT();

    return (
        <EntryDialog
            id="disclaimer"
            title={t("disclaimer.title")}
            actionLabel={t("disclaimer.accept")}
            onAction={onAccept}
        >
            <p>{t("disclaimer.p1")}</p>
            <p className="font-semibold text-red-600">{t("disclaimer.p2")}</p>
            <p>{t("disclaimer.p3")}</p>
            <p>{t("disclaimer.p4")}</p>
            <p>{t("disclaimer.p5")}</p>
        </EntryDialog>
    );
}
