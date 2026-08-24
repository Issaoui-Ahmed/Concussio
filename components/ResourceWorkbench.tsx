"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    AlertTriangle,
    Check,
    ChevronLeft,
    ChevronRight,
    Link2,
    Loader2,
    RefreshCw,
    Search,
    Trash2,
    Unlink,
    Wand2,
    X,
} from "lucide-react";
import { normalizeUrl } from "@/lib/i18n/resourceLinks";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

/**
 * The single place EN->FR resource pairing is curated.
 *
 * Layout follows the shape of the decision rather than the shape of the data: paired resources
 * render as **aligned three-column rows**, so the two documents sit side by side with the
 * verdict between them. Everything unpaired falls into two independent columns below. The
 * alternative — two free-scrolling lists with drawn connectors — looks impressive and is far
 * worse to use, because the two ends of a line are rarely on screen together.
 *
 * Writes go to `/api/resource-links/*`, which records them in the `resource_pairs` table as
 * origin='manual'. The nightly refresh never touches a manual row, and clearing them lets the
 * matcher's derived pairs show through again — so "Clear manual" always has a known-good state
 * to return to.
 */

// Two provenances, no third: the matcher found it, or a person made it.
type Origin = "manual" | "auto";

interface ResourceEntry {
    title: string;
    url: string;
    toolNumber: string | null;
    group: string;
    sourcePage: string;
    host: string;
    isPdf: boolean;
    offListing: boolean;
}

interface LinkEntry {
    enUrl: string;
    frUrl: string;
    frTitle: string;
    origin: Origin;
    note: string;
    overrideId: string | null;
    createdAt: string | null;
    /** Set when the matcher proposes this live and nothing has recorded a decision yet. */
    proposed?: boolean;
    /** Whether the matcher reproduces this pair unaided — i.e. it survives without the baseline. */
    derivable?: "auto" | "conflict";
}

interface Report {
    english: ResourceEntry[];
    french: ResourceEntry[];
    links: LinkEntry[];
    summary: Record<string, number>;
    store: { configured: boolean; available: boolean; error: string | null; overrides: number };
    errors: string[];
    /**
     * Whether the "Living Guideline Tools" heading could be read on the source page. Separate
     * from `errors` because it has a place on screen: an empty English column reads as "there
     * are no tools" unless something says the heading itself went missing.
     */
    englishSource?: {
        ok: boolean;
        count: number;
        listedOnPage: number;
        heading: string;
        sourcePage: string;
        message: string | null;
    };
    elapsedMs: number;
}

const ORIGIN_META: Record<Origin, { label: string; chip: string; dot: string; hint: string }> = {
    manual: {
        label: "Manual",
        chip: "bg-violet-50 text-violet-700 ring-violet-600/20",
        dot: "bg-violet-500",
        hint: "Paired by a person on this page. The nightly refresh never overwrites these.",
    },
    auto: {
        label: "Auto",
        chip: "bg-sky-50 text-sky-700 ring-sky-600/20",
        dot: "bg-sky-500",
        hint: "Matched on tool number — the same number on both sides, language-independent.",
    },
};

// Two views, and they are the two halves of the page: the pairings table, or the resources that
// have no pairing yet. The badge on "Paired" counts settled pairings only — a suggestion sits in
// that list awaiting a decision but is not one yet.
type FilterKey = "paired" | "unpaired";

const FILTERS: Array<{ key: FilterKey; label: string; countKey?: string }> = [
    { key: "paired", label: "Paired", countKey: "paired" },
    { key: "unpaired", label: "Unpaired", countKey: "unpairedEnglish" },
];

/** Entries per page. Each list pages independently. */
const PAGE_SIZE = 5;

interface Page<T> {
    items: T[];
    page: number;
    pageCount: number;
    total: number;
}

/**
 * Slice a list into the current page.
 *
 * The page index is *clamped here* rather than corrected in state, so a search that shrinks the
 * list below the current page cannot strand the user on an empty one — and nothing has to write
 * state during render to fix it.
 */
function paginate<T>(items: T[], requested: number): Page<T> {
    const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
    const page = Math.min(Math.max(requested, 0), pageCount - 1);
    return {
        items: items.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
        page,
        pageCount,
        total: items.length,
    };
}

/** Strip the scheme and trailing slash so the eye lands on the meaningful part of the path. */
function prettyUrl(url: string): string {
    return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}

function matches(needle: string, ...values: Array<string | null | undefined>): boolean {
    if (!needle) return true;
    return values.some(value => (value ?? "").toLowerCase().includes(needle));
}

function relativeTime(iso: string | null): string {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
}

// --- small pieces ---------------------------------------------------------------------------

/**
 * Page through one list. Renders nothing when everything already fits on a single page, so a
 * short list never carries a control that would do nothing.
 */
function Pager<T>({ slice, onChange }: { slice: Page<T>; onChange: (page: number) => void }) {
    if (slice.total <= PAGE_SIZE) return null;

    const first = slice.page * PAGE_SIZE + 1;
    const last = Math.min(slice.total, first + PAGE_SIZE - 1);
    const step = "rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-gray-400";

    return (
        <div className="flex items-center justify-between gap-2 pt-1">
            <button
                onClick={() => onChange(slice.page - 1)}
                disabled={slice.page === 0}
                aria-label="Previous page"
                className={step}
            >
                <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-[11px] tabular-nums text-gray-400">
                {first}–{last} of {slice.total}
            </span>
            <button
                onClick={() => onChange(slice.page + 1)}
                disabled={slice.page >= slice.pageCount - 1}
                aria-label="Next page"
                className={step}
            >
                <ChevronRight className="h-4 w-4" />
            </button>
        </div>
    );
}

function MetaBadge({
    children,
    title,
    tone = "gray",
}: {
    children: React.ReactNode;
    title?: string;
    tone?: "gray" | "brand" | "rose";
}) {
    const tones = {
        gray: "bg-gray-100 text-gray-500",
        brand: "bg-[#e9f1fb] text-[#00417d]",
        rose: "bg-rose-50 text-rose-600",
    };
    return (
        <span
            title={title}
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tones[tone]}`}
        >
            {children}
        </span>
    );
}

function ResourceCard({
    resource,
    selected,
    onSelect,
}: {
    resource: ResourceEntry;
    selected?: boolean;
    onSelect?: () => void;
}) {
    const interactive = Boolean(onSelect);
    return (
        <div
            onClick={onSelect}
            role={interactive ? "button" : undefined}
            tabIndex={interactive ? 0 : undefined}
            aria-pressed={interactive ? Boolean(selected) : undefined}
            onKeyDown={
                interactive
                    ? event => {
                          if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              onSelect?.();
                          }
                      }
                    : undefined
            }
            className={`min-w-0 rounded-xl border px-3 py-2.5 transition-all duration-150 ${
                selected
                    ? "border-[#00417d] bg-[#e9f1fb] ring-2 ring-[#00417d]/20"
                    : "border-gray-100 bg-white hover:border-gray-200 hover:bg-gray-50/80"
            } ${interactive ? "cursor-pointer" : ""}`}
        >
            <div className="flex items-center gap-1.5">
                {resource.toolNumber && (
                    <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] font-medium text-gray-600">
                        {resource.toolNumber}
                    </span>
                )}
                <a
                    href={resource.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={event => event.stopPropagation()}
                    title={resource.title || resource.url}
                    className="truncate text-sm font-medium text-gray-800 hover:text-[#00417d] hover:underline"
                >
                    {resource.title || prettyUrl(resource.url)}
                </a>
            </div>

            <div className="mt-1 flex items-center gap-1.5">
                {resource.isPdf && <MetaBadge title="Links straight to a PDF">pdf</MetaBadge>}
                {/*
                  No "living tool" badge: the English column is now narrowed to that section, so
                  the badge fired on every row and marked nothing.
                */}
                {/*
                  Expected never to render: both columns are scraped from the live listings, so
                  a pairing can only reference something already in one. It fires if the site
                  moves a URL out from under a recorded pairing — worth showing, not hiding.
                */}
                {resource.offListing && (
                    <MetaBadge
                        tone="rose"
                        title="No longer on the live listing, but a recorded pairing still points at it. Re-pair or remove it."
                    >
                        off-listing
                    </MetaBadge>
                )}
                {resource.host && resource.host !== "pedsconcussion.com" && (
                    <MetaBadge title={`Hosted off-site on ${resource.host}`}>
                        {resource.host}
                    </MetaBadge>
                )}
                <span
                    className="min-w-0 truncate font-mono text-[11px] text-gray-400"
                    title={resource.url}
                >
                    {prettyUrl(resource.url)}
                </span>
            </div>
        </div>
    );
}

// --- main ----------------------------------------------------------------------------------

type Pending =
    | { kind: "unpair"; link: LinkEntry }
    | { kind: "clear-all"; count: number };

export function ResourceWorkbench() {
    const [report, setReport] = useState<Report | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState<FilterKey>("paired");
    const [selectedEn, setSelectedEn] = useState<string | null>(null);
    const [selectedFr, setSelectedFr] = useState<string | null>(null);
    const [pending, setPending] = useState<Pending | null>(null);
    const [page, setPage] = useState({ paired: 0, en: 0, fr: 0 });
    const [busy, setBusy] = useState(false);
    const inFlight = useRef(false);

    const load = useCallback(async (manual: boolean) => {
        if (inFlight.current) return;
        inFlight.current = true;
        if (manual) setRefreshing(true);

        try {
            const response = await fetch("/api/resource-links/report", { cache: "no-store" });
            if (!response.ok) throw new Error(`Request failed (${response.status}).`);
            setReport((await response.json()) as Report);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Could not load the pairing report.");
        } finally {
            setLoading(false);
            setRefreshing(false);
            inFlight.current = false;
        }
    }, []);

    useEffect(() => {
        void load(false);
    }, [load]);

    // Escape is the universal "I did not mean to start this" — clear the selection.
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !pending) {
                setSelectedEn(null);
                setSelectedFr(null);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [pending]);

    const mutate = useCallback(
        async (
            path: string,
            init: RequestInit,
            // A function when the message depends on what came back — auto-pair reports a count
            // it cannot know until the server answers.
            successMessage: string | ((data: unknown) => string),
        ) => {
            setBusy(true);
            setError(null);
            try {
                const response = await fetch(`/api/resource-links${path}`, {
                    ...init,
                    headers: {
                        ...(init.body ? { "Content-Type": "application/json" } : {}),
                        ...(init.headers ?? {}),
                    },
                });
                if (!response.ok) {
                    const detail = await response.json().catch(() => null);
                    throw new Error(detail?.detail ?? `Request failed (${response.status}).`);
                }
                const data = await response.json().catch(() => null);
                setNotice(
                    typeof successMessage === "function" ? successMessage(data) : successMessage,
                );
                setSelectedEn(null);
                setSelectedFr(null);
                setPending(null);
                await load(false);
                return true;
            } catch (err) {
                setError(err instanceof Error ? err.message : "The change could not be saved.");
                return false;
            } finally {
                setBusy(false);
            }
        },
        [load],
    );

    useEffect(() => {
        if (!notice) return;
        const timer = window.setTimeout(() => setNotice(null), 4000);
        return () => window.clearTimeout(timer);
    }, [notice]);

    // --- derived -------------------------------------------------------------------------
    const needle = query.trim().toLowerCase();
    // Gates *saving*, never selecting. Selection is local state and costs nothing, so a store
    // outage must not make the page feel inert — you can still explore and line two resources
    // up; only the button that would write is disabled, and it says why.
    const canEdit = Boolean(report?.store.available);

    const byUrl = useMemo(() => {
        const index = new Map<string, ResourceEntry>();
        for (const entry of report?.english ?? []) index.set(normalizeUrl(entry.url), entry);
        for (const entry of report?.french ?? []) index.set(normalizeUrl(entry.url), entry);
        return index;
    }, [report]);

    /** Pairings, as aligned rows. Recorded ones first, then the matcher's live suggestions. */
    const rows = useMemo(() => {
        if (!report) return [];
        return report.links
            .filter(link => {
                // Suggestions live in this list too, sorted to the bottom below. They used to
                // have their own tab; with that gone, excluding them here would leave nowhere
                // to confirm or reject one.
                if (filter === "unpaired") return false;
                if (!needle) return true;
                const en = byUrl.get(normalizeUrl(link.enUrl));
                const fr = byUrl.get(normalizeUrl(link.frUrl));
                return matches(needle, en?.title, link.enUrl, fr?.title, link.frUrl);
            })
            .sort((a, b) => Number(Boolean(a.proposed)) - Number(Boolean(b.proposed)));
    }, [report, filter, needle, byUrl]);

    /** Every EN/FR URL that already has a pairing, regardless of the active filter. */
    const paired = useMemo(() => {
        const en = new Set<string>();
        const fr = new Set<string>();
        for (const link of report?.links ?? []) {
            en.add(normalizeUrl(link.enUrl));
            fr.add(normalizeUrl(link.frUrl));
        }
        return { en, fr };
    }, [report]);

    const looseEnglish = useMemo(() => {
        if (!report) return [];
        return report.english.filter(entry => {
            if (paired.en.has(normalizeUrl(entry.url))) return false;
            if (filter === "paired") return false;
            return matches(needle, entry.title, entry.url);
        });
    }, [report, paired, filter, needle]);

    const looseFrench = useMemo(() => {
        if (!report) return [];
        return report.french.filter(entry => {
            if (paired.fr.has(normalizeUrl(entry.url))) return false;
            if (filter === "paired") return false;
            return matches(needle, entry.title, entry.url);
        });
    }, [report, paired, filter, needle]);

    // Paged after filtering, so "1–5 of 12" always counts what the current search matches.
    const pagedRows = paginate(rows, page.paired);
    const pagedEnglish = paginate(looseEnglish, page.en);
    const pagedFrench = paginate(looseFrench, page.fr);

    const summary = report?.summary ?? {};
    const selectedEnEntry = selectedEn ? byUrl.get(normalizeUrl(selectedEn)) : undefined;
    const selectedFrEntry = selectedFr ? byUrl.get(normalizeUrl(selectedFr)) : undefined;
    const selectedEnAlreadyPaired =
        selectedEn != null &&
        (report?.links ?? []).some(link => normalizeUrl(link.enUrl) === normalizeUrl(selectedEn));

    // --- actions -------------------------------------------------------------------------
    const pair = useCallback(
        (enUrl: string, frUrl: string, frTitle: string) =>
            mutate(
                "/pairs",
                { method: "POST", body: JSON.stringify({ enUrl, frUrl, frTitle }) },
                "Pairing saved.",
            ),
        [mutate],
    );

    // No confirm step: everything it writes is a tool-number match, and every one of them can be
    // removed individually afterwards or undone wholesale with "Clear manual".
    const autoPair = useCallback(
        () =>
            mutate("/auto-pair", { method: "POST" }, data => {
                const result = data as { added?: number; skippedSuppressed?: number } | null;
                const added = result?.added ?? 0;
                const skipped = result?.skippedSuppressed ?? 0;
                if (!added) {
                    return skipped
                        ? `Nothing to add — ${skipped} match(es) stayed removed.`
                        : "Nothing to add: every tool number that matches is already paired.";
                }
                const tail = skipped ? ` ${skipped} stayed removed.` : "";
                return `Auto-pair added ${added} pairing${added === 1 ? "" : "s"}.${tail}`;
            }),
        [mutate],
    );

    const confirmPending = useCallback(
        async () => {
            if (!pending) return;
            switch (pending.kind) {
                case "unpair":
                    // One call for every kind of link. The server records a suppression, which
                    // is what lets a baseline or matcher pairing be removed at all — neither can
                    // be deleted where it lives.
                    await mutate(
                        "/unpair",
                        { method: "POST", body: JSON.stringify({ enUrl: pending.link.enUrl }) },
                        "Pairing removed.",
                    );
                    return;
                case "clear-all":
                    await mutate("/overrides", { method: "DELETE" }, "All manual pairings cleared.");
                    return;
            }
        },
        [pending, mutate],
    );

    // --- render --------------------------------------------------------------------------
    const gutter = (link: LinkEntry) => {
        const meta = ORIGIN_META[link.origin];
        return (
            <div className="flex flex-col items-center gap-1">
                <div className="flex items-center gap-1">
                    <span
                        title={`${meta.hint}${link.note ? `\n\n${link.note}` : ""}${
                            link.createdAt ? `\n\nAdded ${relativeTime(link.createdAt)}` : ""
                        }`}
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium ring-1 ring-inset ${meta.chip}`}
                    >
                        <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                        {link.proposed ? "Suggested" : meta.label}
                    </span>
                </div>

                <div className="flex items-center gap-0.5">
                    {link.proposed && (
                        <button
                            onClick={() => void pair(link.enUrl, link.frUrl, link.frTitle)}
                            disabled={!canEdit || busy}
                            title="Confirm this suggestion as a manual pairing"
                            className="rounded p-1 text-gray-300 transition-colors hover:bg-emerald-50 hover:text-emerald-600 disabled:opacity-40"
                        >
                            <Check className="h-3.5 w-3.5" />
                        </button>
                    )}
                    {/*
                      Every link is removable, whatever produced it. A manual row is deleted; a
                      baseline or matcher pairing gets a suppression recorded against it, since
                      neither can be deleted where it lives. Clearing the store undoes either.
                    */}
                    <button
                        onClick={() => setPending({ kind: "unpair", link })}
                        disabled={!canEdit}
                        title={
                            link.proposed
                                ? "Reject this suggestion — it will stop being proposed"
                                : "Remove this pairing"
                        }
                        className="rounded p-1 text-gray-300 transition-colors hover:bg-rose-50 hover:text-rose-500 disabled:opacity-40"
                    >
                        <Unlink className="h-3.5 w-3.5" />
                    </button>
                </div>

                {link.derivable === "conflict" && (
                    <span
                        title="The matcher independently proposes a DIFFERENT French page for this resource."
                        className="rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-700"
                    >
                        conflict
                    </span>
                )}
            </div>
        );
    };

    return (
        <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
            {/* Header */}
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-gray-900">Living Guideline Tools</h2>
                    <p className="mt-1 max-w-2xl text-sm text-gray-500">
                        Every tool in the Living Guideline Tools section of{" "}
                        <a
                            href="https://pedsconcussion.com/tools-resources/"
                            target="_blank"
                            rel="noreferrer"
                            className="text-[#00417d] hover:underline"
                        >
                            Tools &amp; Resources
                        </a>{" "}
                        and every French resource on{" "}
                        <a
                            href="https://pedsconcussion.com/ressources/"
                            target="_blank"
                            rel="noreferrer"
                            className="text-[#00417d] hover:underline"
                        >
                            Ressources
                        </a>
                        . Pick one from each side to pair them. Unpaired resources keep their
                        English link in the chat.
                    </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                    <button
                        onClick={() => void autoPair()}
                        disabled={!canEdit || busy}
                        title="Match every unpaired resource on tool number and record what it finds"
                        className="inline-flex items-center gap-2 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-800 transition-colors hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {busy ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Wand2 className="h-4 w-4" />
                        )}
                        Auto-pair
                    </button>
                    <button
                        onClick={() =>
                            setPending({ kind: "clear-all", count: summary.manualOverrides ?? 0 })
                        }
                        disabled={!canEdit || !(summary.manualOverrides ?? 0)}
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        <Trash2 className="h-4 w-4" />
                        Clear manual
                        {(summary.manualOverrides ?? 0) > 0 && (
                            <span className="rounded-full bg-violet-100 px-1.5 text-xs font-semibold text-violet-700">
                                {summary.manualOverrides}
                            </span>
                        )}
                    </button>
                    <button
                        onClick={() => void load(true)}
                        disabled={refreshing}
                        className="inline-flex items-center gap-2 rounded-lg border border-[#00417d] px-4 py-2 text-sm font-medium text-[#00417d] transition-colors hover:bg-[#e9f1fb] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {refreshing ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <RefreshCw className="h-4 w-4" />
                        )}
                        Re-scan
                    </button>
                </div>
            </div>

            {report && !report.store.available && (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                        <strong className="font-semibold">Editing is unavailable.</strong> The
                        manual-pairing store could not be read, so what you see below is the
                        committed baseline plus live matches only.
                        <div className="mt-1 font-mono text-[11px] leading-relaxed opacity-80">
                            {report.store.error}
                        </div>
                        {report.store.configured && (
                            <div className="mt-1 text-[12px]">
                                If this is a fresh install, run{" "}
                                <code className="rounded bg-white/70 px-1 py-0.5">
                                    scripts/sql/resource_overrides.sql
                                </code>{" "}
                                in the Supabase SQL editor.
                            </div>
                        )}
                    </div>
                </div>
            )}

            {error && (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {notice && (
                <div className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                    <Check className="h-4 w-4 shrink-0" />
                    <span>{notice}</span>
                </div>
            )}

            {report?.errors?.length ? (
                <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    Scrape warnings: {report.errors.join("; ")}
                </div>
            ) : null}

            {/* Controls */}
            <div className="mt-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="relative w-full lg:max-w-xs">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                    <input
                        value={query}
                        onChange={event => setQuery(event.target.value)}
                        placeholder="Search title or URL…"
                        className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-9 text-sm text-gray-800 outline-none transition-colors placeholder:text-gray-400 focus:border-[#00417d] focus:ring-2 focus:ring-[#00417d]/15"
                    />
                    {query && (
                        <button
                            onClick={() => setQuery("")}
                            aria-label="Clear search"
                            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                        >
                            <X className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>

                <div className="flex flex-wrap gap-1.5">
                    {FILTERS.map(item => {
                        const count = item.countKey ? summary[item.countKey] ?? 0 : undefined;
                        const active = filter === item.key;
                        return (
                            <button
                                key={item.key}
                                onClick={() => setFilter(item.key)}
                                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
                                    active
                                        ? "bg-[#00417d] text-white shadow-sm"
                                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                                }`}
                            >
                                {item.label}
                                {count !== undefined && (
                                    <span
                                        className={active ? "ml-1.5 opacity-70" : "ml-1.5 text-gray-400"}
                                    >
                                        {count}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* The source heading is missing — say so where the tools would have been, rather
                than leaving a blank column that reads as "this site has no tools". */}
            {report?.englishSource && !report.englishSource.ok && (
                <div
                    role="status"
                    className="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
                >
                    <p className="font-semibold">
                        No English tools could be read from the source page
                    </p>
                    <p className="mt-1 leading-relaxed">{report.englishSource.message}</p>
                    <a
                        href={report.englishSource.sourcePage}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block font-medium underline underline-offset-2 hover:text-amber-950"
                    >
                        Open the source page to check the heading
                    </a>
                </div>
            )}

            {/* Column headers */}
            <div className="mt-5 hidden grid-cols-[1fr_7rem_1fr] gap-4 border-b border-gray-100 pb-2 lg:grid">
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    English{" "}
                    <span className="font-normal text-gray-400">({summary.english ?? 0})</span>
                    {report?.englishSource && !report.englishSource.ok && (
                        <span className="ml-2 font-normal normal-case tracking-normal text-amber-700">
                            heading not found
                        </span>
                    )}
                </div>
                <div className="text-center text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Pairing
                </div>
                <div className="text-right text-xs font-semibold uppercase tracking-wide text-gray-500 lg:text-left">
                    French <span className="font-normal text-gray-400">({summary.french ?? 0})</span>
                </div>
            </div>

            {loading ? (
                <div className="mt-4 space-y-3">
                    {Array.from({ length: 6 }).map((_, index) => (
                        <div key={index} className="grid grid-cols-[1fr_7rem_1fr] gap-4">
                            <div className="h-14 animate-pulse rounded-xl bg-gray-100" />
                            <div className="h-14 animate-pulse rounded-xl bg-gray-50" />
                            <div className="h-14 animate-pulse rounded-xl bg-gray-100" />
                        </div>
                    ))}
                </div>
            ) : (
                <>
                    {/* Paired: aligned so both documents read as one row. */}
                    {rows.length > 0 && (
                        <div className="mt-4 space-y-2">
                            {pagedRows.items.map(link => {
                                const en = byUrl.get(normalizeUrl(link.enUrl));
                                const fr = byUrl.get(normalizeUrl(link.frUrl));
                                if (!en || !fr) return null;
                                return (
                                    <div
                                        key={`${link.enUrl}|${link.frUrl}`}
                                        className="grid grid-cols-1 items-center gap-2 rounded-xl p-1 transition-colors hover:bg-gray-50/60 lg:grid-cols-[1fr_7rem_1fr] lg:gap-4"
                                    >
                                        <ResourceCard
                                            resource={en}
                                            onSelect={() =>
                                                setSelectedEn(
                                                    selectedEn === en.url ? null : en.url,
                                                )
                                            }
                                            selected={
                                                selectedEn != null &&
                                                normalizeUrl(selectedEn) === normalizeUrl(en.url)
                                            }
                                        />
                                        <div className="flex items-center justify-center">
                                            <div className="hidden h-px flex-1 bg-gray-200 lg:block" />
                                            <div className="px-1">{gutter(link)}</div>
                                            <div className="hidden h-px flex-1 bg-gray-200 lg:block" />
                                        </div>
                                        <ResourceCard
                                            resource={fr}
                                            onSelect={() =>
                                                setSelectedFr(
                                                    selectedFr === fr.url ? null : fr.url,
                                                )
                                            }
                                            selected={
                                                selectedFr != null &&
                                                normalizeUrl(selectedFr) === normalizeUrl(fr.url)
                                            }
                                        />
                                    </div>
                                );
                            })}

                            <div className="mx-auto max-w-xs">
                                <Pager
                                    slice={pagedRows}
                                    onChange={next =>
                                        setPage(state => ({ ...state, paired: next }))
                                    }
                                />
                            </div>
                        </div>
                    )}

                    {/* Unpaired: two independent lists. */}
                    {(looseEnglish.length > 0 || looseFrench.length > 0) && (
                        <>
                            {rows.length > 0 && (
                                <div className="my-5 flex items-center gap-3">
                                    <div className="h-px flex-1 bg-gray-100" />
                                    <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                                        Not yet paired
                                    </span>
                                    <div className="h-px flex-1 bg-gray-100" />
                                </div>
                            )}

                            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_7rem_1fr]">
                                {/* min-w-0 on the column wrappers, not just the cards: a grid
                                    track is minmax(auto, 1fr), and that auto floor is max-content
                                    — one long un-wrapping URL would otherwise push the French
                                    column off-screen. */}
                                <div className="min-w-0 space-y-2">
                                    {pagedEnglish.items.map(entry => (
                                        <ResourceCard
                                            key={entry.url}
                                            resource={entry}
                                            selected={
                                                selectedEn != null &&
                                                normalizeUrl(selectedEn) === normalizeUrl(entry.url)
                                            }
                                            onSelect={() =>
                                                setSelectedEn(
                                                    selectedEn === entry.url ? null : entry.url,
                                                )
                                            }
                                        />
                                    ))}
                                    {looseEnglish.length === 0 && (
                                        <p className="rounded-xl border border-dashed border-gray-200 px-3 py-6 text-center text-xs text-gray-400">
                                            Nothing unpaired on the English side.
                                        </p>
                                    )}
                                    <Pager
                                        slice={pagedEnglish}
                                        onChange={next => setPage(state => ({ ...state, en: next }))}
                                    />
                                </div>

                                <div className="hidden items-start justify-center pt-6 lg:flex">
                                    <div
                                        className={`rounded-full p-2 transition-colors ${
                                            selectedEn && selectedFr
                                                ? "bg-[#e9f1fb] text-[#00417d]"
                                                : "text-gray-200"
                                        }`}
                                        title="Select one resource on each side to pair them"
                                    >
                                        <Link2 className="h-5 w-5" />
                                    </div>
                                </div>

                                <div className="min-w-0 space-y-2">
                                    {pagedFrench.items.map(entry => (
                                        <ResourceCard
                                            key={entry.url}
                                            resource={entry}
                                            selected={
                                                selectedFr != null &&
                                                normalizeUrl(selectedFr) === normalizeUrl(entry.url)
                                            }
                                            onSelect={() =>
                                                setSelectedFr(
                                                    selectedFr === entry.url ? null : entry.url,
                                                )
                                            }
                                        />
                                    ))}
                                    {looseFrench.length === 0 && (
                                        <p className="rounded-xl border border-dashed border-gray-200 px-3 py-6 text-center text-xs text-gray-400">
                                            Every French resource is accounted for.
                                        </p>
                                    )}
                                    <Pager
                                        slice={pagedFrench}
                                        onChange={next => setPage(state => ({ ...state, fr: next }))}
                                    />
                                </div>
                            </div>
                        </>
                    )}

                    {rows.length === 0 && looseEnglish.length === 0 && looseFrench.length === 0 && (
                        <div className="px-4 py-16 text-center">
                            <p className="text-sm font-medium text-gray-700">No matching resources</p>
                            <p className="mt-1 text-sm text-gray-400">
                                Try a different search term or filter.
                            </p>
                        </div>
                    )}
                </>
            )}

            {report && (
                <p className="mt-4 flex flex-wrap items-center gap-1.5 text-xs text-gray-400">
                    <Check className="h-3.5 w-3.5" />
                    Scanned in {(report.elapsedMs / 1000).toFixed(1)}s
                </p>
            )}

            {/* Selection action bar. Sticky so the verdict is reachable from anywhere in a long list. */}
            {(selectedEn || selectedFr) && (
                <div className="sticky bottom-4 z-20 mt-4">
                    <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-2xl border border-gray-200 bg-white/95 p-4 shadow-lg backdrop-blur sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0 text-sm">
                            <div className="truncate text-gray-800">
                                <span className="text-xs uppercase tracking-wide text-gray-400">
                                    EN
                                </span>{" "}
                                {selectedEnEntry
                                    ? selectedEnEntry.title || prettyUrl(selectedEnEntry.url)
                                    : "— pick an English resource"}
                            </div>
                            <div className="truncate text-gray-800">
                                <span className="text-xs uppercase tracking-wide text-gray-400">
                                    FR
                                </span>{" "}
                                {selectedFrEntry
                                    ? selectedFrEntry.title || prettyUrl(selectedFrEntry.url)
                                    : "— pick a French resource"}
                            </div>
                            {!canEdit ? (
                                <div className="mt-1 text-[11px] text-amber-700">
                                    Saving is unavailable — the pairing store could not be reached.
                                </div>
                            ) : (
                                selectedEnAlreadyPaired &&
                                selectedFr && (
                                    <div className="mt-1 text-[11px] text-amber-700">
                                        This English resource is already paired; saving replaces it.
                                    </div>
                                )
                            )}
                        </div>

                        <div className="flex shrink-0 flex-wrap items-center gap-2">
                            {selectedEn && selectedFr && (
                                <button
                                    onClick={() =>
                                        void pair(
                                            selectedEn,
                                            selectedFr,
                                            selectedFrEntry?.title ?? "",
                                        )
                                    }
                                    disabled={busy || !canEdit}
                                    title={
                                        canEdit
                                            ? undefined
                                            : "The pairing store could not be reached, so this cannot be saved."
                                    }
                                    className="inline-flex items-center gap-2 rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#002a52] disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                    {busy ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Link2 className="h-4 w-4" />
                                    )}
                                    Pair
                                </button>
                            )}
                            <button
                                onClick={() => {
                                    setSelectedEn(null);
                                    setSelectedFr(null);
                                }}
                                className="rounded-lg px-3 py-2 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100"
                            >
                                Clear
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {pending?.kind === "unpair" && (
                <ConfirmDialog
                    title="Remove this pairing?"
                    tone="danger"
                    confirmLabel="Remove pairing"
                    busy={busy}
                    body="This English resource will have no French counterpart — the baseline and the matcher are both overruled, and it keeps its English link in the chat. Reversible: “Clear manual pairings” brings it back."
                    onConfirm={confirmPending}
                    onCancel={() => setPending(null)}
                />
            )}

            {pending?.kind === "clear-all" && (
                <ConfirmDialog
                    title="Clear all manual pairings?"
                    tone="danger"
                    confirmLabel={`Clear ${pending.count} pairing(s)`}
                    busy={busy}
                    body={
                        <>
                            Deletes every pairing made from this page —{" "}
                            <strong>{pending.count}</strong> in total. Pairs the matcher derived
                            are{" "}
                            <code className="rounded bg-gray-100 px-1 py-0.5 text-[12px]">
                                origin=auto
                            </code>{" "}
                            and are not touched, so the app returns to exactly what the nightly
                            refresh produces from the live listings.
                        </>
                    }
                    onConfirm={confirmPending}
                    onCancel={() => setPending(null)}
                />
            )}
        </section>
    );
}
