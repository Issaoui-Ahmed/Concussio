"use client";

import { acceptDisclaimer, acknowledgeDemoNotice, useEntryStep } from "@/lib/entryFlow";
import { DemoNoticeModal } from "./DemoNoticeModal";
import { DisclaimerModal } from "./DisclaimerModal";

/**
 * The entry sequence after the password gate: demo/testing notice, then disclaimer, then the
 * app. Exactly one of them is on screen at a time because exactly one step is current.
 */
export function EntryModals() {
    const step = useEntryStep();

    if (step === "demo-notice") return <DemoNoticeModal onContinue={acknowledgeDemoNotice} />;
    if (step === "disclaimer") return <DisclaimerModal onAccept={acceptDisclaimer} />;
    return null;
}
