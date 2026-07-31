// EN -> FR resource link resolution.
//
// The model is never asked to produce French URLs — it would hallucinate them, and the real
// French slugs are long enough to mangle (see
// `/outil-10-1-algorithme-de-gestion-des-troubles-de-la-vision-...`). Instead the model always
// emits the English URL it has, and the *display* layer swaps it here.
//
// Why the display layer and not generation: one assistant message is shown in EN or FR
// depending on the app locale, and `core/translator.py` deliberately leaves URLs untouched. If
// the swap happened at generation time, toggling a French answer to English would leave French
// links behind. Link language has to follow the locale that is being *rendered*.
//
// THE DATA LIVES IN `./resourceLinks.data.ts`, which is GENERATED from
// `data/resource-pairs.json` — the reviewed source of truth. Add or change a mapping there,
// never here. The logic below is hand-written and covered by tests; the pipeline is not
// allowed to rewrite it.
//
// Every French URL is confirmed live before it enters the data file. A French link that 404s
// is worse than the English original it replaces. When a resource has no French version the
// English URL is left alone — that is the intended fallback, not a gap.

import { RESOURCES, type FrenchResource } from "./resourceLinks.data";

export type { FrenchResource };

/** A resolvable set of EN->FR mappings. Supplied by the runtime store, or the bundled default. */
export interface ResourceMap {
    resources: Record<string, FrenchResource>;
}

/**
 * The build-time map. Also the permanent fallback when `/api/resource-links` is unavailable.
 *
 * Defined here rather than in the store so this module stays free of React — `localizeLink` is
 * pure and must remain testable in plain Node.
 */
export const BUNDLED_RESOURCE_MAP: ResourceMap = {
    resources: RESOURCES,
};

/**
 * Canonical form for comparison: force https, drop `www.`, lowercase the host, drop a trailing
 * slash. The corpus is inconsistent about all four (`http://www.5pconcussion.com/...` vs
 * `https://www.5pconcussion.com/...`, `/dva` vs `/scat/`), and the path itself stays
 * case-sensitive because some hosts serve case-sensitive paths.
 *
 * `scripts/content_pipeline/urls.py` is the Python twin of this function. The two must agree,
 * or the generated table will contain keys this file can never match.
 */
export function normalizeUrl(raw: string): string {
    try {
        const parsed = new URL(raw.trim());
        const host = parsed.host.toLowerCase().replace(/^www\./, "");
        const path = parsed.pathname.replace(/\/+$/, "");
        return `https://${host}${path}${parsed.search}${parsed.hash}`;
    } catch {
        return raw.trim();
    }
}

/**
 * Lookup table derived from a resource map.
 *
 * Cached per map object: the map is swapped at most once per page load (when
 * `/api/resource-links` responds), so rebuilding it on every render would be pure waste in a
 * component that renders on every message.
 */
const LOOKUP_CACHE = new WeakMap<object, Map<string, FrenchResource>>();

function lookupsFor(map: ResourceMap): Map<string, FrenchResource> {
    const cached = LOOKUP_CACHE.get(map);
    if (cached) return cached;

    const byUrl = new Map<string, FrenchResource>(
        Object.entries(map.resources).map(([english, french]) => [normalizeUrl(english), french])
    );
    LOOKUP_CACHE.set(map, byUrl);
    return byUrl;
}

export interface LocalizedLink {
    /** The href to render. Unchanged unless a verified French equivalent exists. */
    href: string;
    /** Official French title, when one exists and differs from the English. */
    title?: string;
}

/**
 * Resolve a link for the given locale.
 *
 * In English, nothing changes. In French, a mapped URL is swapped for its verified French
 * equivalent; an unmapped one is left alone.
 *
 * `map` defaults to the bundled data so non-React callers and tests need not supply one.
 * Components pass the runtime map from `useResourceMap()`, which self-updates from
 * `/api/resource-links`.
 */
export function localizeLink(
    href: string | undefined,
    locale: string,
    map: ResourceMap = BUNDLED_RESOURCE_MAP
): LocalizedLink {
    const original = href ?? "";

    // Only external web links are candidates. In-page anchors, mailto:, etc. are left alone.
    if (locale !== "fr" || !/^https?:\/\//i.test(original)) {
        return { href: original };
    }

    const french = lookupsFor(map).get(normalizeUrl(original));
    if (french) {
        return { href: french.url, title: french.title };
    }

    return { href: original };
}
