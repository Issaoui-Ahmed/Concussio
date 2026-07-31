"use client";

import { useSyncExternalStore } from "react";
import { type FrenchResource } from "./resourceLinks.data";
import { BUNDLED_RESOURCE_MAP, type ResourceMap } from "./resourceLinks";

/**
 * Runtime source for the EN->FR resource map.
 *
 * The bundled `resourceLinks.data.ts` only changes on redeploy, which would mean French links
 * going stale whenever pedsconcussion.com publishes a new translated tool. `/api/resource-links`
 * recomputes the map (CDN-cached, so roughly once a day) and this store swaps it in.
 *
 * The bundled data is the initial value and the permanent fallback: if the fetch fails, times
 * out, or returns something malformed, links keep working from the last committed map. A stale
 * link is recoverable; a missing one is not.
 *
 * Written as an external store rather than component state because `localizeLink` is called
 * synchronously during render — the same reason LanguageProvider uses this pattern.
 */

export type { ResourceMap };

const BUNDLED = BUNDLED_RESOURCE_MAP;

let current: ResourceMap = BUNDLED;
let listeners: Array<() => void> = [];
let started = false;

const emit = () => {
    for (const listener of listeners) listener();
};

function isValid(payload: unknown): payload is { pairs: Record<string, FrenchResource> } {
    if (!payload || typeof payload !== "object") return false;
    const { pairs } = payload as Record<string, unknown>;
    if (!pairs || typeof pairs !== "object" || Array.isArray(pairs)) return false;
    // An empty map would silently strip every French link — treat it as a failed fetch.
    return Object.keys(pairs).length > 0;
}

async function load(): Promise<void> {
    try {
        const response = await fetch("/api/resource-links", { cache: "force-cache" });
        if (!response.ok) return;
        const payload: unknown = await response.json();
        if (!isValid(payload)) return;

        const entries = Object.entries(payload.pairs).filter(
            ([english, french]) =>
                typeof english === "string" &&
                french != null &&
                typeof (french as FrenchResource).url === "string"
        );
        if (entries.length === 0) return;

        current = {
            resources: Object.fromEntries(entries) as Record<string, FrenchResource>,
        };
        emit();
    } catch {
        // Keep the bundled map. Never surface this to the user: the links still work.
    }
}

const subscribe = (onChange: () => void) => {
    listeners.push(onChange);
    if (!started) {
        started = true;
        void load();
    }
    return () => {
        listeners = listeners.filter(listener => listener !== onChange);
    };
};

const getSnapshot = () => current;

// The server must render the bundled map so hydration matches; the fetched map arrives after.
const getServerSnapshot = () => BUNDLED;

export function useResourceMap(): ResourceMap {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
