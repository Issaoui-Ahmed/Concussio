"use client";

import { useSyncExternalStore } from "react";

/**
 * The two acknowledgements a visitor gives before reaching the chat, in order: the
 * demo/testing notice, then the disclaimer. The password gate sits ahead of both, but that one
 * is enforced on the server (`lib/demoAccess.ts`) rather than remembered here.
 *
 * Both live in sessionStorage, per browser session rather than per browser: the app
 * deliberately re-asks (and re-opens in English) each new session, which is also why the locale
 * itself lives in sessionStorage.
 */
const DEMO_NOTICE_KEY = "concussio_demo_notice_acknowledged";
const DISCLAIMER_KEY = "concussio_disclaimer_accepted";

// A minimal external store so the sessionStorage reads are hydration-safe: React uses the
// server snapshot for SSR and the first hydration pass, then re-reads on the client. Reading
// storage during render (or via setState in an effect) would mismatch or cascade instead.
let listeners: Array<() => void> = [];

const subscribe = (onChange: () => void) => {
    listeners.push(onChange);
    return () => {
        listeners = listeners.filter(listener => listener !== onChange);
    };
};

const acknowledge = (key: string) => {
    sessionStorage.setItem(key, "true");
    for (const listener of listeners) listener();
};

export type EntryStep = "demo-notice" | "disclaimer" | null;

// Derived rather than stored: one source of truth for the order means the two modals cannot
// both decide it is their turn.
const getSnapshot = (): EntryStep => {
    if (sessionStorage.getItem(DEMO_NOTICE_KEY) !== "true") return "demo-notice";
    if (sessionStorage.getItem(DISCLAIMER_KEY) !== "true") return "disclaimer";
    return null;
};

// On the server, act as though both were acknowledged so no modal is part of the SSR markup.
const getServerSnapshot = (): EntryStep => null;

export function useEntryStep(): EntryStep {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export const acknowledgeDemoNotice = () => acknowledge(DEMO_NOTICE_KEY);
export const acceptDisclaimer = () => acknowledge(DISCLAIMER_KEY);
