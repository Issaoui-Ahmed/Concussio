"use client";

import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useSyncExternalStore,
} from "react";
import { en, type TranslationKey } from "./en";
import { fr } from "./fr";

export type Locale = "en" | "fr";

const DICTIONARIES: Record<Locale, Record<TranslationKey, string>> = { en, fr };

// sessionStorage, not localStorage: the disclaimer reappears each browser session and always
// opens in English, so a locale persisted across sessions would contradict its own default.
const STORAGE_KEY = "concussio_locale";

// sessionStorage is an external store, so it is read through useSyncExternalStore rather than
// copied into state by an effect. That keeps SSR and hydration consistent (the server
// snapshot is always "en", which is what the app is defined to boot as).
let listeners: Array<() => void> = [];

const subscribe = (onChange: () => void) => {
    listeners.push(onChange);
    return () => {
        listeners = listeners.filter(listener => listener !== onChange);
    };
};

const getSnapshot = (): Locale => {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    return stored === "fr" || stored === "en" ? stored : "en";
};

const getServerSnapshot = (): Locale => "en";

const writeLocale = (next: Locale) => {
    sessionStorage.setItem(STORAGE_KEY, next);
    for (const listener of listeners) listener();
};

interface LanguageContextValue {
    locale: Locale;
    setLocale: (locale: Locale) => void;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
    const locale = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    const setLocale = useCallback((next: Locale) => writeLocale(next), []);

    useEffect(() => {
        document.documentElement.lang = locale;
    }, [locale]);

    const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);

    return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

/**
 * Falls back to English with a no-op setter when no provider is above it.
 *
 * This is what keeps /admin English by construction: `app/admin/layout.tsx` mounts no
 * provider, so shared components (ChatMessage, used by BatchInterface) render English there
 * without needing a conditional anyone has to remember.
 */
export function useLocale(): LanguageContextValue {
    const ctx = useContext(LanguageContext);
    if (ctx) return ctx;
    return { locale: "en", setLocale: () => {} };
}

export type Translator = (key: TranslationKey, vars?: Record<string, string | number>) => string;

export function useT(): Translator {
    const { locale } = useLocale();
    return useCallback(
        (key: TranslationKey, vars?: Record<string, string | number>) => {
            const template = DICTIONARIES[locale][key] ?? en[key];
            if (!vars) return template;
            return template.replace(/\{(\w+)\}/g, (match, name: string) =>
                name in vars ? String(vars[name]) : match
            );
        },
        [locale]
    );
}
