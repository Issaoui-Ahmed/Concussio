"use client";

import { useSyncExternalStore } from "react";

/**
 * The three steps a visitor completes before reaching the chat, in order: acknowledge the
 * demo/testing notice, accept the disclaimer, then choose a user group. The password gate sits
 * ahead of all of them, but that one is enforced on the server (`lib/demoAccess.ts`) rather
 * than remembered here.
 *
 * All three live in sessionStorage, per browser session rather than per browser: the app
 * deliberately re-asks (and re-opens in English) each new session, which is also why the locale
 * itself lives in sessionStorage.
 */
const DEMO_NOTICE_KEY = "concussio_demo_notice_acknowledged";
const DISCLAIMER_KEY = "concussio_disclaimer_accepted";
const USER_TYPE_KEY = "concussio_user_type";

export const USER_TYPES = [
    "Healthcare Professional",
    "Parent or Caregiver",
    "Youth",
    "Teacher",
    "Coach",
] as const;

// The English string is the wire value: it routes to the Fuel IX assistant
// (ASSISTANT_ENV_BY_USER_TYPE) and selects the prompt personalization. Only the label is
// translated. Typing it as the union keeps `userType.${userType}` a checked dictionary key.
export type UserType = (typeof USER_TYPES)[number];

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

const write = (key: string, value: string) => {
    sessionStorage.setItem(key, value);
    for (const listener of listeners) listener();
};

// Validated rather than cast: a value stored under a since-renamed option must send the
// visitor back to the picker, not reach /api/chat as a user type no assistant answers to.
const readUserType = (): UserType | null => {
    const stored = sessionStorage.getItem(USER_TYPE_KEY);
    return USER_TYPES.find(value => value === stored) ?? null;
};

export type EntryStep = "demo-notice" | "disclaimer" | "user-type" | null;

// Derived rather than stored: one source of truth for the order means no two steps can both
// decide it is their turn.
const getSnapshot = (): EntryStep => {
    if (sessionStorage.getItem(DEMO_NOTICE_KEY) !== "true") return "demo-notice";
    if (sessionStorage.getItem(DISCLAIMER_KEY) !== "true") return "disclaimer";
    if (readUserType() === null) return "user-type";
    return null;
};

// On the server, act as though every step was completed so no modal is part of the SSR markup.
const getServerSnapshot = (): EntryStep => null;

export function useEntryStep(): EntryStep {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/**
 * The user group chosen on the entry screen, or later from the chat's dropdown. Null until one
 * has been chosen this session (and always on the server).
 */
export function useUserType(): UserType | null {
    return useSyncExternalStore(subscribe, readUserType, () => null);
}

export const acknowledgeDemoNotice = () => write(DEMO_NOTICE_KEY, "true");
export const acceptDisclaimer = () => write(DISCLAIMER_KEY, "true");
export const chooseUserType = (value: UserType) => write(USER_TYPE_KEY, value);
