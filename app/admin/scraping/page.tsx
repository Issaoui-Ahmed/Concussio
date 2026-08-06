"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Download, Loader2, RefreshCw } from "lucide-react";
import { ResourceWorkbench } from "@/components/ResourceWorkbench";
import { ContentPipelineRunner } from "@/components/ContentPipelineRunner";

interface ScrapedDomain {
  domain: string;
  section_title: string;
  section_url: string;
  recommendation_html: string;
  recommendation_text: string;
}

// The response also carries `living_guideline_tools`, which this page no longer reads: those are
// English resources, and they now appear once, in the pairing workbench. The ZIP download below
// still uses them, but server-side from its own snapshot.
interface ScrapingResponse {
  updated_at: string | null;
  refresh_interval_seconds: number;
  is_refreshing: boolean;
  last_error: string | null;
  domain_count: number;
  domains: ScrapedDomain[];
  living_guideline_tools_count: number;
}

const REFRESH_MS = 60_000;

export default function AdminScrapingPage() {
  const [data, setData] = useState<ScrapingResponse | null>(null);
  // Bumped when a pipeline run actually writes pairings, which remounts the workbench below.
  // Otherwise it would keep rendering the table as it was before the run that just changed it —
  // stale data directly beneath a panel saying what changed.
  const [workbenchKey, setWorkbenchKey] = useState(0);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);
  const [isDownloadingTools, setIsDownloadingTools] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);

  const loadScrapingData = useCallback(async (force: boolean) => {
    if (inFlightRef.current) {
      return;
    }

    inFlightRef.current = true;
    if (force) {
      setIsManualRefreshing(true);
    }

    try {
      const params = force ? "?force=true" : "";
      const response = await fetch(`/api/scraping${params}`, {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error("Failed to fetch scraping data.");
      }

      const payload: ScrapingResponse = await response.json();
      setData(payload);
      setError(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unexpected error while fetching data.";
      setError(message);
    } finally {
      setIsInitialLoading(false);
      setIsManualRefreshing(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    void loadScrapingData(false);

    const interval = window.setInterval(() => {
      void loadScrapingData(false);
    }, REFRESH_MS);

    return () => window.clearInterval(interval);
  }, [loadScrapingData]);

  const formattedUpdatedAt = useMemo(() => {
    if (!data?.updated_at) {
      return "Never";
    }
    return new Date(data.updated_at).toLocaleString();
  }, [data?.updated_at]);

  const downloadLivingGuidelineTools = useCallback(async () => {
    setIsDownloadingTools(true);
    setError(null);
    try {
      const response = await fetch("/api/scraping/living-guideline-tools/download?force=true", {
        method: "GET",
      });
      if (!response.ok) {
        throw new Error("Failed to download Living Guideline Tools ZIP.");
      }

      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") ?? "";
      const match = disposition.match(/filename=\"?([^\";]+)\"?/i);
      const fileName = match?.[1] ?? `living-guideline-tools-${new Date().toISOString().slice(0, 10)}.zip`;

      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unexpected error while downloading ZIP.";
      setError(message);
    } finally {
      setIsDownloadingTools(false);
    }
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-[#F7F7F9] p-6">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-800">Scraping</h1>
              <p className="text-sm text-gray-500">
                Resources, pairings, and guideline recommendations scraped from
                pedsconcussion.com (auto-refresh every minute).
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => void downloadLivingGuidelineTools()}
                disabled={isDownloadingTools}
                className="inline-flex items-center gap-2 rounded-lg border border-[#00417d] px-4 py-2 text-sm font-medium text-[#00417d] transition-colors hover:bg-[#e9f1fb] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isDownloadingTools ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Download tools ZIP
              </button>
              <button
                onClick={() => void loadScrapingData(true)}
                disabled={isManualRefreshing}
                className="inline-flex items-center gap-2 rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#002a52] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isManualRefreshing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {/*
                  "Refresh view", not "Refresh now": this re-reads the scrape cache behind this
                  page and publishes nothing. The pipeline card below is the one that writes.
                  Two buttons both saying "refresh" on one screen, one of which patches six
                  production copilots, is a trap worth naming your way out of.
                */}
                Refresh view
              </button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600">
            <span>
              <strong className="text-gray-800">Domains:</strong>{" "}
              {data?.domain_count ?? 0}
            </span>
            <span>
              <strong className="text-gray-800">Living tools:</strong>{" "}
              {data?.living_guideline_tools_count ?? 0}{" "}
              <span className="text-gray-400">(in the ZIP)</span>
            </span>
            <span>
              <strong className="text-gray-800">Last update:</strong>{" "}
              {formattedUpdatedAt}
            </span>
          </div>

          {data?.last_error && (
            <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Last scrape error: {data.last_error}
            </div>
          )}

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/*
          Runs the nightly refresh on demand and reports its diff. Sits above the workbench
          because it is what makes the workbench's contents change.
        */}
        <ContentPipelineRunner onApplied={() => setWorkbenchKey(key => key + 1)} />

        {/*
          The single view of the Living Guideline Tools and their French counterparts. Loads
          independently of the recommendations scrape below, so it appears immediately.

          Its English side is the same Living Guideline Tools scrape the ZIP above carries, so
          the two counts agree by construction rather than by coincidence. Both narrow the 96
          links on the Tools & Resources page down to that one section; the rest is third-party
          material with no French counterpart to pair against.
        */}
        <ResourceWorkbench key={workbenchKey} />

        {isInitialLoading ? (
          <div className="rounded-2xl border border-gray-100 bg-white p-12 text-center text-gray-500 shadow-sm">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-[#00417d]" />
            <p className="mt-3 text-sm">Loading scraped content...</p>
          </div>
        ) : (
          <div className="space-y-4">
            <h2 className="px-1 pt-2 text-lg font-semibold text-gray-900">
              Guideline recommendations
              <span className="ml-2 text-sm font-normal text-gray-400">
                {data?.domain_count ?? 0} domains
              </span>
            </h2>

            {data?.domains.map((item) => (
              <article
                key={`${item.domain}-${item.section_url}`}
                className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm"
              >
                <h2 className="text-lg font-semibold text-gray-900">{item.domain}</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Source:{" "}
                  <a
                    href={item.section_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#00417d] hover:underline"
                  >
                    {item.section_title || item.section_url}
                  </a>
                </p>

                <details className="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-gray-800">
                    Recommendations
                  </summary>
                  <div
                    className="prose prose-sm mt-4 max-w-none text-gray-700 prose-headings:text-gray-900 prose-strong:text-gray-900"
                    dangerouslySetInnerHTML={{
                      __html:
                        item.recommendation_html ||
                        `<p>${item.recommendation_text || "No recommendation content found."}</p>`,
                    }}
                  />
                </details>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
