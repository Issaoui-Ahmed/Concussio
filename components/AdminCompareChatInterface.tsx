"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { Sidebar, Session } from "./Sidebar";

type ProviderKey = "openai" | "fuelix";
type ProviderMode = ProviderKey | "both";
type ProviderStatus = "loading" | "ready" | "error" | "idle";

interface ProviderAnswer {
    status: ProviderStatus;
    ok: boolean;
    answer: string;
    elapsed_ms: number | null;
    error?: string;
    assistant_id?: string;
    run_status?: string;
    started_at_ms?: number;
}

interface CompareAnswerMessage {
    id: string;
    role: "assistant_compare";
    mode: ProviderMode;
    answers: {
        openai?: ProviderAnswer;
        fuelix?: ProviderAnswer;
    };
}

interface UserMessage {
    id: string;
    role: "user";
    content: string;
}

type Message = UserMessage | CompareAnswerMessage;

const createMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
const STORAGE_KEY = "concussio_admin_compare_sessions";

const PROVIDER_LABELS: Record<ProviderKey, string> = {
    openai: "OpenAI",
    fuelix: "Fuel IX",
};

function makeLoadingAnswer(): ProviderAnswer {
    return {
        status: "loading",
        ok: false,
        answer: "",
        elapsed_ms: null,
        started_at_ms: Date.now(),
    };
}

function formatElapsedSeconds(elapsedMs: number | null): string {
    if (elapsedMs === null || Number.isNaN(elapsedMs)) {
        return "n/a";
    }
    return `${(elapsedMs / 1000).toFixed(1)}s`;
}

function getDisplayElapsedMs(answer: ProviderAnswer, nowMs: number): number | null {
    if (answer.status === "loading" && typeof answer.started_at_ms === "number") {
        return Math.max(0, nowMs - answer.started_at_ms);
    }
    return answer.elapsed_ms;
}

function normalizeProviderPayload(
    rawPayload: unknown,
    fallbackAnswer: string,
    fallbackElapsedMs: number,
): ProviderAnswer {
    const payload = (rawPayload && typeof rawPayload === "object")
        ? (rawPayload as Record<string, unknown>)
        : {};

    const ok = payload.ok === false ? false : true;
    const answerCandidate = payload.answer;
    const errorCandidate = payload.error;
    const elapsedCandidate = payload.elapsed_ms;
    const assistantCandidate = payload.assistant_id;
    const runStatusCandidate = payload.run_status;

    const answer = typeof answerCandidate === "string" && answerCandidate.trim()
        ? answerCandidate
        : fallbackAnswer;
    const error = typeof errorCandidate === "string" ? errorCandidate : undefined;
    const elapsedMs = typeof elapsedCandidate === "number" ? elapsedCandidate : fallbackElapsedMs;

    if (!ok) {
        return {
            status: "error",
            ok: false,
            answer: "",
            elapsed_ms: elapsedMs,
            error: error || "Provider call failed.",
            assistant_id: typeof assistantCandidate === "string" ? assistantCandidate : undefined,
            run_status: typeof runStatusCandidate === "string" ? runStatusCandidate : undefined,
        };
    }

    return {
        status: "ready",
        ok: true,
        answer,
        elapsed_ms: elapsedMs,
        assistant_id: typeof assistantCandidate === "string" ? assistantCandidate : undefined,
        run_status: typeof runStatusCandidate === "string" ? runStatusCandidate : undefined,
    };
}

function ProviderCard({
    provider,
    payload,
    nowMs,
}: {
    provider: ProviderKey;
    payload: ProviderAnswer;
    nowMs: number;
}) {
    const elapsedMs = getDisplayElapsedMs(payload, nowMs);
    const elapsedLabel = formatElapsedSeconds(elapsedMs);

    return (
        <section className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-gray-900">{PROVIDER_LABELS[provider]}</h3>
                <span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                    {elapsedLabel}
                </span>
            </div>

            {payload.status === "loading" ? (
                <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm text-gray-700">
                    <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-[#00417d] animate-pulse" />
                        <span>Thinking...</span>
                    </div>
                </div>
            ) : payload.status === "error" ? (
                <p className="text-sm text-red-600">{payload.error || "Provider call failed."}</p>
            ) : (
                <div className="prose prose-slate max-w-none text-sm leading-6 text-gray-800">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {payload.answer || "_No answer text returned._"}
                    </ReactMarkdown>
                </div>
            )}

            {payload.assistant_id && (
                <p className="mt-3 break-all text-xs text-gray-500">Assistant: {payload.assistant_id}</p>
            )}
        </section>
    );
}

export function AdminCompareChatInterface() {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [userType, setUserType] = useState<string>("Healthcare Professional");
    const [providerMode, setProviderMode] = useState<ProviderMode>("both");
    const [nowMs, setNowMs] = useState<number>(Date.now());
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const storedSessions = localStorage.getItem(STORAGE_KEY);
        if (!storedSessions) return;
        try {
            const parsed = JSON.parse(storedSessions);
            setSessions(Array.isArray(parsed) ? parsed : []);
        } catch (error) {
            console.error("Failed to parse admin compare sessions", error);
        }
    }, []);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }, [sessions]);

    const currentSession = sessions.find((session) => session.id === currentSessionId);
    const messages: Message[] = useMemo(
        () => (currentSession ? (currentSession.messages as Message[]) : []),
        [currentSession]
    );

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    useEffect(() => {
        const hasLoadingProviders = messages.some((message) => {
            if (message.role !== "assistant_compare") return false;
            const openaiLoading = message.answers.openai?.status === "loading";
            const fuelixLoading = message.answers.fuelix?.status === "loading";
            return openaiLoading || fuelixLoading;
        });

        if (!hasLoadingProviders) return;

        const interval = setInterval(() => {
            setNowMs(Date.now());
        }, 100);
        return () => clearInterval(interval);
    }, [messages]);

    const createNewSession = () => {
        const newSession: Session = {
            id: Date.now().toString(),
            title: "New Compare Chat",
            messages: [],
            createdAt: Date.now(),
        };
        setSessions((prev) => [newSession, ...prev]);
        setCurrentSessionId(newSession.id);
        return newSession.id;
    };

    const handleDeleteSession = (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        setSessions((prev) => prev.filter((session) => session.id !== id));
        if (currentSessionId === id) {
            setCurrentSessionId(null);
        }
    };

    const handleSelectSession = (id: string) => {
        setCurrentSessionId(id);
    };

    const updateProviderAnswer = (
        sessionId: string,
        compareMessageId: string,
        provider: ProviderKey,
        answer: ProviderAnswer,
    ) => {
        setSessions((prev) =>
            prev.map((session) => {
                if (session.id !== sessionId) return session;
                return {
                    ...session,
                    messages: session.messages.map((message) => {
                        const typed = message as Message;
                        if (typed.role !== "assistant_compare" || typed.id !== compareMessageId) {
                            return typed;
                        }
                        return {
                            ...typed,
                            answers: {
                                ...typed.answers,
                                [provider]: answer,
                            },
                        };
                    }),
                };
            })
        );
    };

    const callProvider = async (params: {
        provider: ProviderKey;
        message: string;
        userType: string;
        sessionId: string;
        compareMessageId: string;
    }) => {
        const startedAt = Date.now();
        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: params.message,
                    history: [],
                    user_type: params.userType,
                    provider_mode: params.provider,
                }),
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = typeof payload?.detail === "string"
                    ? payload.detail
                    : `Failed to fetch ${PROVIDER_LABELS[params.provider]} response.`;
                throw new Error(detail);
            }

            const providerPayload = payload?.answers?.[params.provider];
            const normalized = normalizeProviderPayload(
                providerPayload,
                typeof payload?.answer === "string" ? payload.answer : "",
                Date.now() - startedAt,
            );
            updateProviderAnswer(params.sessionId, params.compareMessageId, params.provider, normalized);
        } catch (error: unknown) {
            const elapsed = Date.now() - startedAt;
            const errorText = error instanceof Error ? error.message : "Provider call failed.";
            updateProviderAnswer(params.sessionId, params.compareMessageId, params.provider, {
                status: "error",
                ok: false,
                answer: "",
                elapsed_ms: elapsed,
                error: errorText,
            });
        }
    };

    const sendMessage = async () => {
        const trimmed = input.trim();
        if (!trimmed || isLoading) return;

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
            activeSessionId = createNewSession();
        }

        const selectedProviders: ProviderKey[] =
            providerMode === "both" ? ["openai", "fuelix"] : [providerMode];

        const userMessage: UserMessage = {
            id: createMessageId(),
            role: "user",
            content: trimmed,
        };
        const compareMessageId = createMessageId();

        const initialAnswers: CompareAnswerMessage["answers"] = {};
        for (const provider of selectedProviders) {
            initialAnswers[provider] = makeLoadingAnswer();
        }

        const compareMessage: CompareAnswerMessage = {
            id: compareMessageId,
            role: "assistant_compare",
            mode: providerMode,
            answers: initialAnswers,
        };

        setSessions((prev) =>
            prev.map((session) => {
                if (session.id !== activeSessionId) return session;
                const newTitle =
                    session.messages.length === 0
                        ? trimmed.slice(0, 30) + (trimmed.length > 30 ? "..." : "")
                        : session.title;
                return {
                    ...session,
                    title: newTitle,
                    messages: [...session.messages, userMessage, compareMessage],
                };
            })
        );

        setInput("");
        setIsLoading(true);
        setNowMs(Date.now());

        try {
            await Promise.all(
                selectedProviders.map((provider) =>
                    callProvider({
                        provider,
                        message: trimmed,
                        userType,
                        sessionId: activeSessionId!,
                        compareMessageId,
                    })
                )
            );
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await sendMessage();
    };

    return (
        <div className="flex h-full overflow-hidden bg-[#F7F7F9] text-gray-800">
            <Sidebar
                sessions={sessions}
                currentSessionId={currentSessionId}
                onNewChat={() => setCurrentSessionId(null)}
                onSelectSession={handleSelectSession}
                onDeleteSession={handleDeleteSession}
            />

            <div className="relative flex h-full flex-1 flex-col">
                <div className="w-full flex-1 overflow-y-auto">
                    <div className="flex min-h-full flex-col pb-36 pt-10">
                        {!currentSessionId || messages.length === 0 ? (
                            <div className="-mt-20 flex flex-1 flex-col items-center justify-center px-4 text-center">
                                <div className="mb-6 flex items-center justify-center rounded-xl bg-white p-4 shadow-sm">
                                    <div className="relative h-12 w-12">
                                        <Image src="/logo-icon-v2.png" alt="Logo" fill className="object-contain" />
                                    </div>
                                </div>
                                <h1 className="mb-2 text-3xl font-bold text-gray-800">Admin Compare Chat</h1>
                                <p className="max-w-xl text-gray-500">
                                    Choose OpenAI, Fuel IX, or Both. In both mode, each side shows its own live timer while processing.
                                </p>
                            </div>
                        ) : (
                            <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4">
                                {messages.map((message) => {
                                    if (message.role === "user") {
                                        return (
                                            <ChatMessage
                                                key={message.id}
                                                role="user"
                                                content={message.content}
                                                followUps={[]}
                                                followUpsStatus="idle"
                                            />
                                        );
                                    }

                                    const providers: ProviderKey[] =
                                        message.mode === "both" ? ["openai", "fuelix"] : [message.mode];

                                    return (
                                        <div key={message.id} className="rounded-2xl border border-gray-100 bg-white/70 p-4">
                                            <div className="mb-3 text-sm font-semibold text-gray-900">
                                                {message.mode === "both" ? "Provider Comparison" : "Provider Response"}
                                            </div>
                                            <div className={`grid gap-4 ${providers.length === 2 ? "md:grid-cols-2" : "md:grid-cols-1"}`}>
                                                {providers.map((provider) => {
                                                    const payload = message.answers[provider];
                                                    if (!payload) {
                                                        return (
                                                            <section key={provider} className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                                                                Missing payload for {PROVIDER_LABELS[provider]}.
                                                            </section>
                                                        );
                                                    }
                                                    return (
                                                        <ProviderCard
                                                            key={provider}
                                                            provider={provider}
                                                            payload={payload}
                                                            nowMs={nowMs}
                                                        />
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    );
                                })}
                                <div ref={bottomRef} />
                            </div>
                        )}
                    </div>
                </div>

                <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-[#F7F7F9] via-[#F7F7F9] to-transparent px-4 pb-6 pt-10">
                    <div className="mx-auto flex max-w-6xl items-end gap-4">
                        <div className="mb-1 flex shrink-0 rounded-xl border border-gray-100 bg-white p-1 shadow-sm">
                            <select
                                value={userType}
                                onChange={(e) => setUserType(e.target.value)}
                                disabled={messages.length > 0}
                                className="cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-sm font-medium text-gray-700 focus:ring-0 disabled:opacity-50"
                            >
                                <option value="Healthcare Professional">Healthcare Professional</option>
                                <option value="Parent or Caregiver">Parent or Caregiver</option>
                                <option value="Youth">Youth</option>
                                <option value="Teacher">Teacher</option>
                                <option value="Coach">Coach</option>
                            </select>
                        </div>

                        <div className="mb-1 flex shrink-0 rounded-xl border border-gray-100 bg-white p-1 shadow-sm">
                            <select
                                value={providerMode}
                                onChange={(e) => setProviderMode(e.target.value as ProviderMode)}
                                disabled={messages.length > 0 || isLoading}
                                className="cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-sm font-medium text-gray-700 focus:ring-0 disabled:opacity-50"
                            >
                                <option value="both">Both</option>
                                <option value="openai">OpenAI Only</option>
                                <option value="fuelix">Fuel IX Only</option>
                            </select>
                        </div>

                        <form
                            onSubmit={handleSubmit}
                            className="relative flex-1 rounded-xl border border-gray-100 bg-white p-2 shadow-[0_0_20px_rgba(0,0,0,0.05)] transition-all focus-within:border-[#00417d]/30 focus-within:shadow-[0_0_20px_rgba(0,65,125,0.1)]"
                        >
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={`Ask as ${userType} (${providerMode})...`}
                                className="w-full border-none bg-transparent px-4 py-3 pr-12 text-base text-gray-800 placeholder-gray-400 focus:ring-0"
                                disabled={isLoading}
                                autoFocus
                            />
                            <button
                                type="submit"
                                disabled={isLoading || !input.trim()}
                                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-[#00417d] p-2 text-white transition-colors hover:bg-[#002a52] disabled:opacity-50 disabled:hover:bg-[#00417d]"
                            >
                                <Send className="h-4 w-4" />
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
}
