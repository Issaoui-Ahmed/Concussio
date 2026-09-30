"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  Loader2,
  Play,
  XCircle,
} from "lucide-react";

/**
 * Where the CHEO study's chat records go, and a live test that they get there
 * (core/research_log.py).
 *
 * The test writes one record through the code every chat exchange uses, then reads that file back
 * out of SharePoint. So the record shown under a passing test is not what the app meant to write
 * but what CHEO's folder actually holds. It is also the only file the app ever reads back:
 * participant records are never read out of CHEO.
 */

type StepStatus = "ok" | "failed" | "skipped";

interface TestStep {
  key: string;
  label: string;
  status: StepStatus;
  detail?: string;
  hint?: string | null;
  ms?: number;
}

interface TestResult {
  ok: boolean;
  chatLogging: boolean;
  steps: TestStep[];
  file: { name: string; webUrl: string; size: number } | null;
  stored: string | null;
}

interface Status {
  chatLogging: boolean;
  missing: string[];
  destination: {
    siteUrl: string;
    folderPath: string;
    tenantId: string;
    clientId: string;
    thumbprint: string;
  };
}

// The protocol's wording, and the key each item is stored under. A stored key missing from this
// list is flagged under the test result: it would be a field the REB never approved.
const FIELDS = [
  {
    key: "session_id",
    protocol: "Randomly generated session ID",
    meaning: "Made in the participant's browser, one per conversation.",
  },
  {
    key: "timestamp",
    protocol: "Timestamp",
    meaning: "When the question reached the server, in UTC.",
  },
  {
    key: "user_type",
    protocol: "User type selected",
    meaning: "Chosen at the start of the chat.",
  },
  {
    key: "question",
    protocol: "Content of the conversation",
    meaning: "What the participant sent.",
  },
  {
    key: "answer",
    protocol: "Content of the conversation",
    meaning: "What the chatbot answered. Empty when it failed to answer.",
  },
] as const;

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? `Request failed (${response.status}).`);
  }
  return payload as T;
}

function LoggingState({ status }: { status: Status }) {
  if (status.chatLogging && status.missing.length > 0) {
    return (
      <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        <strong>Chat logging is on, but the destination is incomplete</strong>: every exchange is
        being dropped. Missing: {status.missing.join(", ")}.
      </p>
    );
  }
  if (status.chatLogging) {
    return (
      <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
        <strong>Chat logging is on.</strong> Every participant exchange on this deployment is
        written to the folder below.
      </p>
    );
  }
  return (
    <p className="mt-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
      <strong className="text-gray-800">Chat logging is off on this deployment</strong>, so
      participant chats are not being recorded. When the study starts, set{" "}
      <code className="rounded bg-white px-1 py-0.5 text-xs">SHAREPOINT_LOG_CHATS=true</code> in
      the production environment on Vercel and redeploy. The connection test works either way.
    </p>
  );
}

function StepRow({ step }: { step: TestStep }) {
  const icon =
    step.status === "ok" ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
    ) : step.status === "failed" ? (
      <XCircle className="h-4 w-4 text-rose-600" />
    ) : (
      <CircleDashed className="h-4 w-4 text-gray-300" />
    );

  return (
    <li className="flex gap-3 py-2.5">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span
            className={
              step.status === "skipped"
                ? "text-sm text-gray-400"
                : "text-sm font-medium text-gray-800"
            }
          >
            {step.label}
          </span>
          {step.status !== "skipped" && step.ms !== undefined && (
            <span className="shrink-0 text-xs text-gray-400">{step.ms} ms</span>
          )}
        </div>
        {step.status === "skipped" ? (
          <p className="text-xs text-gray-400">Not tried.</p>
        ) : (
          step.detail && (
            <p
              className={`mt-0.5 break-words text-xs ${
                step.status === "failed" ? "text-rose-700" : "text-gray-500"
              }`}
            >
              {step.detail}
            </p>
          )
        )}
        {step.hint && (
          <p className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            {step.hint}
          </p>
        )}
      </div>
    </li>
  );
}

function StoredRecord({ result }: { result: TestResult }) {
  const parsed = useMemo(() => {
    try {
      const value = JSON.parse(result.stored ?? "");
      return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }, [result.stored]);

  const unexpected = parsed
    ? Object.keys(parsed).filter(key => !FIELDS.some(field => field.key === key))
    : [];

  return (
    <div className="mt-5 rounded-xl border border-gray-200">
      <div className="flex flex-col gap-1 border-b border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">What landed in SharePoint</h3>
          {result.file && (
            <p className="break-all font-mono text-[11px] text-gray-500">
              {result.file.name} · {result.file.size.toLocaleString()} bytes
            </p>
          )}
        </div>
        {result.file?.webUrl && (
          <a
            href={result.file.webUrl}
            target="_blank"
            rel="noreferrer"
            title="Opens for anyone with access to the CHEO folder"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-[#00417d] hover:underline"
          >
            Open in SharePoint
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {parsed ? (
        <dl className="divide-y divide-gray-100">
          {FIELDS.map(field => (
            <div key={field.key} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[9rem_1fr] sm:gap-4">
              <dt className="font-mono text-xs text-gray-500">{field.key}</dt>
              <dd className="min-w-0 break-words text-sm text-gray-800">
                {field.key in parsed ? (
                  parsed[field.key] === null ? (
                    <span className="text-gray-400">null</span>
                  ) : (
                    String(parsed[field.key])
                  )
                ) : (
                  <span className="text-rose-600">missing</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="px-4 py-3 text-sm text-rose-700">The stored file is not valid JSON.</p>
      )}

      {unexpected.length > 0 && (
        <p className="border-t border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-700">
          Fields the protocol does not list: {unexpected.join(", ")}.
        </p>
      )}

      <details className="border-t border-gray-100 px-4 py-2.5">
        <summary className="cursor-pointer text-xs font-medium text-gray-600">Raw file</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-3 font-mono text-[11px] text-gray-700">
          {result.stored}
        </pre>
      </details>
    </div>
  );
}

function Setting({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5 py-2 sm:grid-cols-[11rem_1fr] sm:gap-4">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="min-w-0 break-all font-mono text-xs text-gray-800">
        {value || <span className="font-sans text-rose-600">not set</span>}
      </dd>
    </div>
  );
}

export default function ResearchLogPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    requestJson<Status>("/api/admin/research-log/status")
      .then(setStatus)
      .catch((err: unknown) =>
        setStatusError(err instanceof Error ? err.message : "Could not load the configuration."),
      );
  }, []);

  const runTest = useCallback(async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await requestJson<TestResult>("/api/admin/research-log/test", { method: "POST" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The test could not be started.");
    } finally {
      setRunning(false);
    }
  }, []);

  const failedStep = result?.steps.find(step => step.status === "failed");

  return (
    <div className="h-full overflow-y-auto bg-[#F7F7F9] p-4 sm:p-6">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <h1 className="text-2xl font-bold text-gray-800">Research logs</h1>
          <p className="mt-1 max-w-2xl text-sm text-gray-500">
            For the CHEO study, every chat exchange is written as one JSON file into CHEO&apos;s
            SharePoint folder, and nowhere else. Each file holds only the fields the approved REB
            protocol lists.
          </p>
          {status && <LoggingState status={status} />}
          {statusError && (
            <p className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {statusError}
            </p>
          )}
        </section>

        <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-gray-900">Connection test</h2>
              <p className="mt-1 max-w-2xl text-sm text-gray-500">
                Writes one test record through the same code a chat exchange uses, then reads the
                file back from SharePoint and checks it is identical. The file stays in the folder,
                named <span className="font-mono text-xs">TEST_…</span>, so CHEO can see it arrive
                too.
              </p>
            </div>
            <button
              onClick={() => void runTest()}
              disabled={running}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#002a52] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {running ? "Testing…" : "Run test"}
            </button>
          </div>

          {error && (
            <p className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </p>
          )}

          {result && (
            <>
              <div
                className={`mt-5 flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${
                  result.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {result.ok ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                ) : (
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                )}
                <span>
                  {result.ok ? (
                    <>
                      <strong>Logging works.</strong> The test record reached CHEO&apos;s folder
                      and reads back identical.
                      {!result.chatLogging &&
                        " Chat logging is still off here, so participant chats are not being recorded yet."}
                    </>
                  ) : (
                    <>
                      <strong>Not logging yet.</strong> Stopped at “{failedStep?.label}”; the
                      steps after it were not tried.
                    </>
                  )}
                </span>
              </div>

              <ol className="mt-3 divide-y divide-gray-100">
                {result.steps.map(step => (
                  <StepRow key={step.key} step={step} />
                ))}
              </ol>

              {result.stored !== null && <StoredRecord result={result} />}
            </>
          )}
        </section>

        <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900">What each record holds</h2>
          <p className="mt-1 text-sm text-gray-500">
            One file per exchange; a conversation&apos;s files share its session ID. Nothing else
            is recorded: no language, response time, IP address, name or account.
          </p>
          <dl className="mt-3 divide-y divide-gray-100">
            {FIELDS.map(field => (
              <div key={field.key} className="grid gap-0.5 py-2 sm:grid-cols-[9rem_1fr] sm:gap-4">
                <dt className="font-mono text-xs text-gray-800">{field.key}</dt>
                <dd className="text-sm text-gray-600">
                  <span className="font-medium text-gray-800">{field.protocol}.</span>{" "}
                  {field.meaning}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        {status && (
          <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900">Where records go</h2>
            <p className="mt-1 text-sm text-gray-500">
              Read from this deployment&apos;s environment. The certificate&apos;s private key is
              used here but never shown.
            </p>
            <dl className="mt-3 divide-y divide-gray-100">
              <Setting label="Site" value={status.destination.siteUrl} />
              <Setting label="Library / folder" value={status.destination.folderPath} />
              <Setting label="Tenant ID" value={status.destination.tenantId} />
              <Setting label="App (client) ID" value={status.destination.clientId} />
              <Setting label="Certificate thumbprint" value={status.destination.thumbprint} />
            </dl>
          </section>
        )}
      </div>
    </div>
  );
}
