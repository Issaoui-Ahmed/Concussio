"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    AlertTriangle,
    CheckCircle2,
    ChevronDown,
    Clock,
    Eye,
    Loader2,
    Lock,
    Minus,
    Play,
    Plus,
    ShieldAlert,
    Sparkles,
} from "lucide-react";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

/**
 * Run the nightly content refresh on demand, and read what it did.
 *
 * The pipeline has always run itself — 06:17 UTC, three sinks, one Vercel cron. What it had no
 * way of doing was *telling anyone*. A run's only trace was an HTTP status code in a log that
 * cannot say what changed, so "did the site publish a new tool yesterday?" was unanswerable
 * from here. This card is that missing half: the same run, on demand, with its diff on screen.
 *
 * Two buttons, because the interesting question usually is not "run it" but "would running it
 * do anything?":
 *
 *     Preview   scrapes and diffs every sink, writes nothing. Cheap (~7s) and always safe.
 *     Run       applies. Behind a confirm dialog — it patches six production copilots.
 *
 * Both report identically, so a preview is a rehearsal of the panel you will read afterwards.
 *
 * The confirm dialog is the only thing between a click and a production write: the endpoint is
 * deliberately unauthenticated (see api/admin_pipeline.py). That makes the dialog's wording load
 * -bearing rather than decorative — it is where "this publishes for real" gets said.
 */

// --- payload shapes, mirroring scripts/content_pipeline/refresh.py --------------------------

interface CorpusResult {
    ok: boolean;
    /** no-change | would-patch | patched | verified | aborted | error */
    action: string;
    reason?: string;
    problems?: string[];
    domains?: number;
    recommendations?: number;
    corpusChars?: number;
    hash?: string;
    previousHash?: string | null;
    publishedAt?: string;
    patched?: number;
    assistants?: { role: string; status: string; reason?: string }[];
}

interface VectorStoreResult {
    ok: boolean;
    scraped?: number;
    stored?: number;
    unchanged?: number;
    added?: string[];
    removed?: string[];
    needsReview?: string[];
    deferred?: string[];
    problems?: string[];
    failures?: string[];
}

interface PairsResult {
    ok: boolean;
    english?: number;
    french?: number;
    unchanged?: number;
    locked?: number;
    added?: string[];
    updated?: string[];
    retired?: string[];
    problems?: string[];
    failures?: string[];
}

interface RunPayload {
    ok: boolean;
    changed: boolean;
    dryRun: boolean;
    forced: boolean;
    trigger: string;
    elapsed_ms: number;
    runId: number | null;
    startedAt: string | null;
    fetchError?: string;
    leaseError?: string;
    sinks: {
        corpus?: CorpusResult;
        vectorStore?: VectorStoreResult;
        pairs?: PairsResult;
    };
}

interface HistoryRun {
    id: number | null;
    trigger: string;
    dryRun: boolean;
    forced: boolean;
    startedAt: string;
    finishedAt: string | null;
    ok: boolean | null;
    changed: boolean | null;
    inFlight: boolean;
    report: RunPayload | Record<string, never>;
}

interface StatusPayload {
    storeConfigured: boolean;
    cronSchedule: string;
    history: { available: boolean; error: string | null; runs: HistoryRun[] };
}

// --- small pieces ---------------------------------------------------------------------------

type Tone = "neutral" | "good" | "warn" | "bad" | "info";

const TONE_CLASS: Record<Tone, string> = {
    neutral: "border-gray-200 bg-gray-50 text-gray-600",
    good: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warn: "border-amber-300 bg-amber-50 text-amber-800",
    bad: "border-rose-200 bg-rose-50 text-rose-700",
    info: "border-sky-200 bg-sky-50 text-sky-700",
};

function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
    return (
        <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONE_CLASS[tone]}`}
        >
            {children}
        </span>
    );
}

function prettyUrl(url: string): string {
    return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}

/**
 * A list of URLs a sink acted on, or would act on.
 *
 * Collapsed past a handful rather than truncated: the count is the headline, but "which ones"
 * is the whole reason someone opened this panel, so the rest has to stay reachable.
 */
function UrlList({
    label,
    urls,
    tone,
    icon,
    hint,
}: {
    label: string;
    urls: string[];
    tone: Tone;
    icon?: React.ReactNode;
    hint?: string;
}) {
    const [expanded, setExpanded] = useState(false);
    if (!urls.length) return null;

    const visible = expanded ? urls : urls.slice(0, 4);
    return (
        <div className={`rounded-lg border px-3 py-2 ${TONE_CLASS[tone]}`}>
            <div className="flex items-center gap-2 text-xs font-semibold">
                {icon}
                <span>
                    {label} · {urls.length}
                </span>
            </div>
            {hint && <p className="mt-1 text-[11px] font-normal opacity-80">{hint}</p>}
            <ul className="mt-1.5 space-y-1">
                {visible.map(url => (
                    <li key={url} className="min-w-0">
                        <a
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            title={url}
                            className="block truncate font-mono text-[11px] underline-offset-2 hover:underline"
                        >
                            {prettyUrl(url)}
                        </a>
                    </li>
                ))}
            </ul>
            {urls.length > visible.length && (
                <button
                    onClick={() => setExpanded(true)}
                    className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium underline-offset-2 hover:underline"
                >
                    <ChevronDown className="h-3 w-3" />
                    Show {urls.length - visible.length} more
                </button>
            )}
        </div>
    );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <span className="whitespace-nowrap">
            <strong className="font-semibold text-gray-800">{value}</strong>{" "}
            <span className="text-gray-500">{label}</span>
        </span>
    );
}

function SinkCard({
    title, subtitle, badge, stats, children,
}: {
    title: string;
    subtitle: string;
    badge: React.ReactNode;
    stats?: React.ReactNode;
    children?: React.ReactNode;
}) {
    return (
        <section className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-gray-900">{title}</h4>
                    <p className="text-[11px] text-gray-400">{subtitle}</p>
                </div>
                {badge}
            </div>
            {stats && (
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">{stats}</div>
            )}
            {children && <div className="mt-3 space-y-2">{children}</div>}
        </section>
    );
}

/** Gate refusals and hard failures read differently and must not share a colour. */
function Problems({ problems, failures }: { problems?: string[]; failures?: string[] }) {
    return (
        <>
            {(problems ?? []).length > 0 && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    <p className="font-semibold">Refused — nothing written</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {problems!.map(problem => (
                            <li key={problem}>{problem}</li>
                        ))}
                    </ul>
                </div>
            )}
            {(failures ?? []).length > 0 && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    <p className="font-semibold">Failed</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {failures!.map(failure => (
                            <li key={failure}>{failure}</li>
                        ))}
                    </ul>
                </div>
            )}
        </>
    );
}

/** Refused / failed / changed / quiet — the same four states for every sink. */
function verdict(
    problems: string[] | undefined,
    failures: string[] | undefined,
    changed: boolean,
    dryRun: boolean,
): { tone: Tone; label: string } {
    if (problems?.length) return { tone: "warn", label: "Refused" };
    if (failures?.length) return { tone: "bad", label: "Failed" };
    if (changed) return { tone: "good", label: dryRun ? "Would change" : "Changed" };
    return { tone: "neutral", label: "No change" };
}

// --- sink panels ------------------------------------------------------------------------------

const ASSISTANT_TONE: Record<string, Tone> = {
    patched: "good",
    "would-patch": "info",
    "already-current": "neutral",
    skipped: "warn",
    "patch-not-verified": "bad",
};

function CorpusPanel({ result, dryRun }: { result: CorpusResult; dryRun: boolean }) {
    const changed = result.action === "patched" || result.action === "would-patch";
    const mark = result.action === "error"
        ? { tone: "bad" as Tone, label: "Failed" }
        : verdict(result.problems, undefined, changed, dryRun);

    return (
        <SinkCard
            title="Copilot instructions"
            subtitle="pedsconcussion.com recommendations → 6 Fuel IX assistants"
            badge={<Badge tone={mark.tone}>{mark.label}</Badge>}
            stats={
                result.domains !== undefined && (
                    <>
                        <Stat label="domains" value={result.domains} />
                        <Stat label="recommendations" value={result.recommendations ?? 0} />
                        <Stat
                            label="characters"
                            value={(result.corpusChars ?? 0).toLocaleString()}
                        />
                    </>
                )
            }
        >
            {result.hash && (
                <p className="font-mono text-[11px] text-gray-500">
                    {result.previousHash ?? "(nothing published)"} → {result.hash}
                    {result.reason && (
                        <span className="ml-2 font-sans text-gray-400">({result.reason})</span>
                    )}
                </p>
            )}

            {result.action === "no-change" && result.publishedAt && (
                <p className="text-xs text-gray-500">
                    The guideline has not moved since it was published{" "}
                    {new Date(result.publishedAt).toLocaleString()}.
                </p>
            )}

            {(result.assistants ?? []).length > 0 && (
                <ul className="grid gap-1 sm:grid-cols-2">
                    {result.assistants!.map(assistant => (
                        <li
                            key={assistant.role}
                            className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50 px-2.5 py-1.5"
                        >
                            {/* `capitalize` only because one key in ASSISTANT_ENV_BY_USER_TYPE
                                is lowercase ("patient") while the rest are title case. Display
                                fix, not a data fix — that map is a lookup key elsewhere. */}
                            <span className="truncate text-xs capitalize text-gray-700">
                                {assistant.role}
                            </span>
                            <Badge tone={ASSISTANT_TONE[assistant.status] ?? "neutral"}>
                                {assistant.status}
                            </Badge>
                        </li>
                    ))}
                </ul>
            )}

            {(result.assistants ?? []).some(item => item.reason) && (
                <ul className="space-y-0.5 text-[11px] text-amber-700">
                    {result.assistants!
                        .filter(item => item.reason)
                        .map(item => (
                            <li key={item.role}>
                                {item.role}: {item.reason}
                            </li>
                        ))}
                </ul>
            )}

            <Problems problems={result.problems} />
        </SinkCard>
    );
}

function VectorStorePanel({ result, dryRun }: { result: VectorStoreResult; dryRun: boolean }) {
    const changed = Boolean(result.added?.length || result.removed?.length);
    const mark = verdict(result.problems, result.failures, changed, dryRun);

    return (
        <SinkCard
            title="Vector store"
            subtitle="Living Guideline Tools → ConcussCare Coach knowledge base"
            badge={<Badge tone={mark.tone}>{mark.label}</Badge>}
            stats={
                <>
                    <Stat label="scraped" value={result.scraped ?? 0} />
                    <Stat label="stored" value={result.stored ?? 0} />
                    <Stat label="unchanged" value={result.unchanged ?? 0} />
                </>
            }
        >
            <UrlList
                label={dryRun ? "Would upload" : "Uploaded"}
                urls={result.added ?? []}
                tone="good"
                icon={<Plus className="h-3 w-3" />}
            />
            <UrlList
                label={dryRun ? "Would remove" : "Removed"}
                urls={result.removed ?? []}
                tone="bad"
                icon={<Minus className="h-3 w-3" />}
            />
            <UrlList
                label="Needs a person"
                urls={result.needsReview ?? []}
                tone="warn"
                icon={<Lock className="h-3 w-3" />}
                hint="These links vanished from the listing, but their files are hand-made conversions that exist nowhere else. Removal is permanent on this API, so the pipeline reports them and stops."
            />
            <UrlList
                label="Deferred to the next run"
                urls={result.deferred ?? []}
                tone="info"
                icon={<Clock className="h-3 w-3" />}
                hint="Over this run's upload cap. Not lost — the next run diffs against what this one wrote and continues."
            />
            <Problems problems={result.problems} failures={result.failures} />
        </SinkCard>
    );
}

function PairsPanel({ result, dryRun }: { result: PairsResult; dryRun: boolean }) {
    const changed = Boolean(
        result.added?.length || result.updated?.length || result.retired?.length,
    );
    const mark = verdict(result.problems, result.failures, changed, dryRun);

    return (
        <SinkCard
            title="French pairings"
            subtitle="EN tools × FR resources → the map the app resolves against"
            badge={<Badge tone={mark.tone}>{mark.label}</Badge>}
            stats={
                <>
                    <Stat label="EN tools" value={result.english ?? 0} />
                    <Stat label="FR resources" value={result.french ?? 0} />
                    <Stat label="unchanged" value={result.unchanged ?? 0} />
                    <Stat label="manual rows untouched" value={result.locked ?? 0} />
                </>
            }
        >
            <UrlList
                label={dryRun ? "Would pair" : "Paired"}
                urls={result.added ?? []}
                tone="good"
                icon={<Plus className="h-3 w-3" />}
            />
            <UrlList
                label={dryRun ? "Would repoint" : "Repointed"}
                urls={result.updated ?? []}
                tone="info"
            />
            <UrlList
                label={dryRun ? "Would retire" : "Retired"}
                urls={result.retired ?? []}
                tone="warn"
                icon={<Minus className="h-3 w-3" />}
                hint="The listing no longer supports these derived pairs. Manual decisions are never retired this way."
            />
            <Problems problems={result.problems} failures={result.failures} />
        </SinkCard>
    );
}

// --- history ----------------------------------------------------------------------------------

const TRIGGER_LABEL: Record<string, string> = {
    cron: "Scheduled",
    admin: "Admin",
    cli: "Local CLI",
};

function describeRun(run: HistoryRun): string {
    const when = run.startedAt ? new Date(run.startedAt).toLocaleString() : "unknown time";
    const who = TRIGGER_LABEL[run.trigger] ?? run.trigger;
    if (run.inFlight) return `${who} run started ${when} — still going`;
    const outcome = run.ok === false ? "failed" : run.changed ? "made changes" : "found nothing";
    return `${who}${run.dryRun ? " preview" : ""} · ${when} · ${outcome}`;
}

// --- main ---------------------------------------------------------------------------------------

export function ContentPipelineRunner({ onApplied }: { onApplied?: () => void }) {
    const [status, setStatus] = useState<StatusPayload | null>(null);
    const [result, setResult] = useState<RunPayload | null>(null);
    const [busy, setBusy] = useState<false | "preview" | "run">(false);
    const [error, setError] = useState<string | null>(null);
    const [force, setForce] = useState(false);
    const [confirming, setConfirming] = useState(false);
    const [elapsed, setElapsed] = useState(0);
    const startedRef = useRef(0);

    const loadStatus = useCallback(async () => {
        try {
            const response = await fetch("/api/admin/pipeline/status", { cache: "no-store" });
            if (!response.ok) throw new Error(`Request failed (${response.status}).`);
            setStatus((await response.json()) as StatusPayload);
        } catch {
            // Non-fatal: this only supplies the schedule line and the run history. The buttons
            // work without it, so a page-level error would be louder than it deserves.
            setStatus(null);
        }
    }, []);

    useEffect(() => {
        void loadStatus();
    }, [loadStatus]);

    // A run takes seconds when nothing changed and minutes when everything did. A spinner alone
    // cannot tell those apart, and the second one looks broken without a number moving.
    useEffect(() => {
        if (!busy) return;
        startedRef.current = Date.now();
        setElapsed(0);
        const timer = window.setInterval(
            () => setElapsed(Math.round((Date.now() - startedRef.current) / 1000)),
            1000,
        );
        return () => window.clearInterval(timer);
    }, [busy]);

    const run = useCallback(
        async (dryRun: boolean) => {
            setBusy(dryRun ? "preview" : "run");
            setError(null);
            setResult(null);
            try {
                const response = await fetch("/api/admin/pipeline/run", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ dryRun, force }),
                });

                if (!response.ok) {
                    const detail = await response.json().catch(() => null);
                    throw new Error(detail?.detail ?? `Request failed (${response.status}).`);
                }

                const payload = (await response.json()) as RunPayload;
                setResult(payload);
                setConfirming(false);
                if (!payload.dryRun && payload.changed) onApplied?.();
            } catch (err) {
                setError(err instanceof Error ? err.message : "The run could not be started.");
            } finally {
                setBusy(false);
                void loadStatus();
            }
        },
        [force, loadStatus, onApplied],
    );

    const latest = status?.history.runs?.[0];

    const summary = useMemo(() => {
        if (!result) return null;
        if (!result.ok) {
            const refused = Object.values(result.sinks).some(sink => sink?.problems?.length);
            return {
                tone: (refused ? "warn" : "bad") as Tone,
                icon: refused ? <ShieldAlert className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />,
                text: refused
                    ? "A sink refused to act. Nothing was written by it — read the reason below."
                    : "Something failed. Sinks that succeeded still applied.",
            };
        }
        if (!result.changed) {
            return {
                tone: "neutral" as Tone,
                icon: <CheckCircle2 className="h-4 w-4" />,
                text: "No changes — every sink already matches the live site.",
            };
        }
        return {
            tone: "good" as Tone,
            icon: <Sparkles className="h-4 w-4" />,
            text: result.dryRun
                ? "Changes found. Nothing was written — press Run pipeline to apply them."
                : "Changes applied.",
        };
    }, [result]);

    return (
        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-gray-900">Content pipeline</h2>
                    <p className="mt-1 max-w-2xl text-sm text-gray-500">
                        Scrapes pedsconcussion.com, compares it against what we last published,
                        and updates only what moved: copilot instructions, the vector store, and
                        the French pairing table.
                    </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                    <button
                        onClick={() => void run(true)}
                        disabled={Boolean(busy)}
                        className="inline-flex items-center gap-2 rounded-lg border border-[#00417d] px-4 py-2 text-sm font-medium text-[#00417d] transition-colors hover:bg-[#e9f1fb] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {busy === "preview" ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Eye className="h-4 w-4" />
                        )}
                        Preview changes
                    </button>
                    <button
                        onClick={() => setConfirming(true)}
                        disabled={Boolean(busy)}
                        className="inline-flex items-center gap-2 rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#002a52] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {busy === "run" ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4" />
                        )}
                        Run pipeline
                    </button>
                </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-gray-500">
                <span className="inline-flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-gray-400" />
                    Runs automatically every day at 06:17 UTC
                </span>
                {latest && <span>Last: {describeRun(latest)}</span>}
                {status && !status.storeConfigured && (
                    <span className="text-amber-700">Supabase is not configured.</span>
                )}

                <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-gray-600">
                    <input
                        type="checkbox"
                        checked={force}
                        onChange={event => setForce(event.target.checked)}
                        className="h-3.5 w-3.5 rounded border-gray-300 text-[#00417d] focus:ring-[#00417d]"
                    />
                    <span
                        title="Re-push the guideline to all six copilots even when it has not changed. The repair path for an assistant edited outside this system."
                    >
                        Force re-push copilot instructions
                    </span>
                </label>
            </div>

            {busy && (
                <div className="mt-4 flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    <span>
                        {busy === "preview" ? "Previewing" : "Running"} — {elapsed}s elapsed.
                        Scraping ~20 pages
                        {busy === "run" ? " and publishing what changed" : ""}; this can take a
                        minute.
                    </span>
                </div>
            )}

            {error && (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {result && summary && (
                <div className="mt-5 space-y-3">
                    <div
                        className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${TONE_CLASS[summary.tone]}`}
                    >
                        <span className="flex min-w-0 items-center gap-2">
                            {summary.icon}
                            <span>{summary.text}</span>
                        </span>
                        <span className="shrink-0 text-xs opacity-80">
                            {result.dryRun ? "preview" : "applied"} in{" "}
                            {(result.elapsed_ms / 1000).toFixed(1)}s
                        </span>
                    </div>

                    {result.fetchError && (
                        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
                            Could not fetch the listings: {result.fetchError}
                        </div>
                    )}
                    {result.leaseError && (
                        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-600">
                            The run itself completed, but it could not be recorded in the history:{" "}
                            {result.leaseError}
                        </div>
                    )}

                    <div className="grid gap-3">
                        {result.sinks.corpus && (
                            <CorpusPanel result={result.sinks.corpus} dryRun={result.dryRun} />
                        )}
                        {result.sinks.vectorStore && (
                            <VectorStorePanel
                                result={result.sinks.vectorStore}
                                dryRun={result.dryRun}
                            />
                        )}
                        {result.sinks.pairs && (
                            <PairsPanel result={result.sinks.pairs} dryRun={result.dryRun} />
                        )}
                    </div>
                </div>
            )}

            {!result && !busy && (status?.history.runs?.length ?? 0) > 1 && (
                <details className="mt-4 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
                    <summary className="cursor-pointer text-xs font-semibold text-gray-600">
                        Recent runs
                    </summary>
                    <ul className="mt-2 space-y-1 text-xs text-gray-500">
                        {status!.history.runs.map(item => (
                            <li key={item.id ?? item.startedAt}>{describeRun(item)}</li>
                        ))}
                    </ul>
                </details>
            )}

            {confirming && (
                <ConfirmDialog
                    title="Run the content pipeline?"
                    confirmLabel="Run it"
                    busy={Boolean(busy)}
                    body={
                        <>
                            This publishes for real: it can rewrite the instructions of all six
                            production copilots, upload to the vector store, and change which
                            French document a clinician is sent to.
                            {force && (
                                <strong className="mt-2 block text-amber-700">
                                    Force is on — the copilots will be re-pushed even if the
                                    guideline has not changed.
                                </strong>
                            )}
                            <span className="mt-2 block text-gray-500">
                                Manual pairings are never touched. Press Preview instead to see
                                the same diff without writing anything.
                            </span>
                        </>
                    }
                    onConfirm={() => void run(false)}
                    onCancel={() => setConfirming(false)}
                />
            )}

        </div>
    );
}
