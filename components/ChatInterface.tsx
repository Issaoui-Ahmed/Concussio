
"use client";

import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import Image from "next/image";
import { ChatMessage } from "./ChatMessage";
import { Sidebar, Session } from "./Sidebar";
import { Send } from "lucide-react";
import { useLocale, useT, type Locale } from "@/lib/i18n/LanguageProvider";
import { detectLanguage } from "@/lib/i18n/detect";

type FollowUpsStatus = "idle" | "loading" | "ready" | "error";
type Lang = Locale;
type TranslationStatus = "idle" | "loading" | "ready" | "error";

interface Message {
    id?: string;
    role: "user" | "assistant";
    content: string;
    /** The language this message was actually written in. Set at creation, never inferred later. */
    lang?: Lang;
    translations?: Partial<Record<Lang, string>>;
    translationStatus?: TranslationStatus;
    followUps?: string[];
    followUpTranslations?: Partial<Record<Lang, string[]>>;
    followUpsStatus?: FollowUpsStatus;
}

const createMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

const SESSIONS_KEY = "concussio_sessions_v2";
const LEGACY_SESSIONS_KEY = "concussio_sessions";

// Roughly the character budget for one /api/translate request. Long sessions are split so a
// single batch never grows large enough for the model to drop or merge items.
const TRANSLATE_CHUNK_CHARS = 12000;

const USER_TYPES = [
    "Healthcare Professional",
    "Parent or Caregiver",
    "Youth",
    "Teacher",
    "Coach",
] as const;

// The English string is the wire value: it routes to the Fuel IX assistant
// (ASSISTANT_ENV_BY_USER_TYPE) and selects the prompt personalization. Only the label is
// translated. Typing it as the union keeps `userType.${userType}` a checked dictionary key.
type UserType = (typeof USER_TYPES)[number];

/**
 * Sessions written before the global-locale rework carried a per-chat `displayLang`. The
 * cached `translations` on each message are still valid, so they are kept; only the dead
 * field is dropped.
 */
const loadStoredSessions = (): Session[] => {
    const parse = (raw: string | null): Session[] | null => {
        if (!raw) return null;
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : null;
        } catch {
            return null;
        }
    };

    const current = parse(localStorage.getItem(SESSIONS_KEY));
    if (current) return current;

    const legacy = parse(localStorage.getItem(LEGACY_SESSIONS_KEY));
    if (!legacy) return [];

    return legacy.map(session => {
        const { displayLang, ...rest } = session as Session & { displayLang?: Lang };
        void displayLang;
        return rest as Session;
    });
};

export function ChatInterface() {
    const { locale, setLocale } = useLocale();
    const t = useT();

    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [elapsedTime, setElapsedTime] = useState(0);
    const [userType, setUserType] = useState<UserType>("Healthcare Professional");
    const bottomRef = useRef<HTMLDivElement>(null);

    // Latest values for async work that must not read a stale closure.
    const sessionsRef = useRef<Session[]>(sessions);
    const localeRef = useRef<Locale>(locale);
    const inFlightRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        sessionsRef.current = sessions;
    }, [sessions]);

    useEffect(() => {
        localeRef.current = locale;
    }, [locale]);

    const defaultFollowUps = useMemo(
        () => [t("followUps.default.1"), t("followUps.default.2"), t("followUps.default.3")],
        [t]
    );

    // Timer for loading state
    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isLoading) {
            const startTime = Date.now();
            setElapsedTime(0);
            interval = setInterval(() => {
                setElapsedTime((Date.now() - startTime) / 1000);
            }, 100);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [isLoading]);

    // Initial load from localStorage
    const [hydrated, setHydrated] = useState(false);
    useEffect(() => {
        setSessions(loadStoredSessions());
        setHydrated(true);
    }, []);

    // Save to localStorage whenever sessions change (but not before hydration, or we would
    // immediately overwrite the stored sessions with an empty array).
    useEffect(() => {
        if (!hydrated) return;
        localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
    }, [sessions, hydrated]);

    const currentSession = sessions.find(s => s.id === currentSessionId);
    const messages: Message[] = useMemo(
        () => (currentSession ? (currentSession.messages as Message[]) : []),
        [currentSession]
    );

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const createNewSession = () => {
        const newSession: Session = {
            id: Date.now().toString(),
            title: "New Chat",
            messages: [],
            createdAt: Date.now(),
        };
        setSessions(prev => [newSession, ...prev]);
        setCurrentSessionId(newSession.id);
        return newSession.id;
    };

    const handleDeleteSession = (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        setSessions(prev => prev.filter(s => s.id !== id));
        if (currentSessionId === id) {
            setCurrentSessionId(null);
        }
    };

    const handleSelectSession = (id: string) => {
        setCurrentSessionId(id);
    };

    const normalizeFollowUps = useCallback(
        (items: string[]) => {
            const deduped = Array.from(
                new Set(items.map(item => item.trim()).filter(item => item.length > 0))
            );
            for (const fallback of defaultFollowUps) {
                if (deduped.length >= 3) break;
                if (!deduped.includes(fallback)) deduped.push(fallback);
            }
            return deduped.slice(0, 3);
        },
        [defaultFollowUps]
    );

    const patchMessage = useCallback(
        (sessionId: string, messageId: string, patch: (message: Message) => Message) => {
            setSessions(prev =>
                prev.map(s => {
                    if (s.id !== sessionId) return s;
                    return {
                        ...s,
                        messages: s.messages.map(message => {
                            const typedMessage = message as Message;
                            if (typedMessage.id !== messageId) return typedMessage;
                            return patch(typedMessage);
                        }),
                    };
                })
            );
        },
        []
    );

    const callTranslate = useCallback(
        async (texts: string[], targetLang: Lang): Promise<string[] | null> => {
            try {
                const res = await fetch("/api/translate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ texts, target_lang: targetLang }),
                });
                if (!res.ok) throw new Error("Failed to translate");
                const data = await res.json();
                if (!data || !Array.isArray(data.texts) || data.texts.length !== texts.length) {
                    return null;
                }
                return data.texts as string[];
            } catch (error) {
                console.error(error);
                return null;
            }
        },
        []
    );

    /**
     * Backfill the current session into `lang`.
     *
     * Only assistant content and follow-ups are translated — user messages and session titles
     * stay in whatever the user typed. Work is batched into as few requests as possible,
     * deduplicated while in flight, and discarded if the locale changed before it resolved.
     */
    const ensureSessionTranslated = useCallback(
        async (sessionId: string, lang: Lang) => {
            const session = sessionsRef.current.find(s => s.id === sessionId);
            if (!session) return;

            type Unit = { messageId: string; kind: "content" | "followUps"; texts: string[] };
            const units: Unit[] = [];

            for (const raw of session.messages as Message[]) {
                const message = raw;
                if (!message.id || message.role !== "assistant") continue;
                if (message.lang === lang) continue;

                const contentKey = `${message.id}:content:${lang}`;
                if (
                    message.content?.trim() &&
                    !message.translations?.[lang] &&
                    !inFlightRef.current.has(contentKey)
                ) {
                    units.push({ messageId: message.id, kind: "content", texts: [message.content] });
                }

                const followUps = message.followUps ?? [];
                const followUpsKey = `${message.id}:followUps:${lang}`;
                if (
                    followUps.length > 0 &&
                    !message.followUpTranslations?.[lang] &&
                    !inFlightRef.current.has(followUpsKey)
                ) {
                    units.push({ messageId: message.id, kind: "followUps", texts: followUps });
                }
            }

            if (units.length === 0) return;

            for (const unit of units) {
                inFlightRef.current.add(`${unit.messageId}:${unit.kind}:${lang}`);
                if (unit.kind === "content") {
                    patchMessage(sessionId, unit.messageId, m => ({
                        ...m,
                        translationStatus: "loading",
                    }));
                }
            }

            // Pack units into chunks that stay under the character budget. A unit is never
            // split across chunks, so the index mapping back to messages stays simple.
            const chunks: Unit[][] = [];
            let chunk: Unit[] = [];
            let chunkChars = 0;
            for (const unit of units) {
                const unitChars = unit.texts.reduce((sum, text) => sum + text.length, 0);
                if (chunk.length > 0 && chunkChars + unitChars > TRANSLATE_CHUNK_CHARS) {
                    chunks.push(chunk);
                    chunk = [];
                    chunkChars = 0;
                }
                chunk.push(unit);
                chunkChars += unitChars;
            }
            if (chunk.length > 0) chunks.push(chunk);

            for (const batch of chunks) {
                const flat = batch.flatMap(unit => unit.texts);
                const translated = await callTranslate(flat, lang);

                // The user toggled again while this was in flight — drop the result.
                if (localeRef.current !== lang) {
                    for (const unit of batch) {
                        inFlightRef.current.delete(`${unit.messageId}:${unit.kind}:${lang}`);
                    }
                    continue;
                }

                let cursor = 0;
                for (const unit of batch) {
                    const slice = translated?.slice(cursor, cursor + unit.texts.length) ?? null;
                    cursor += unit.texts.length;
                    inFlightRef.current.delete(`${unit.messageId}:${unit.kind}:${lang}`);

                    if (!slice) {
                        if (unit.kind === "content") {
                            patchMessage(sessionId, unit.messageId, m => ({
                                ...m,
                                translationStatus: "error",
                            }));
                        }
                        continue;
                    }

                    if (unit.kind === "content") {
                        patchMessage(sessionId, unit.messageId, m => ({
                            ...m,
                            translations: { ...(m.translations ?? {}), [lang]: slice[0] ?? m.content },
                            translationStatus: "ready",
                        }));
                    } else {
                        patchMessage(sessionId, unit.messageId, m => ({
                            ...m,
                            followUpTranslations: { ...(m.followUpTranslations ?? {}), [lang]: slice },
                        }));
                    }
                }
            }
        },
        [callTranslate, patchMessage]
    );

    // One code path for both triggers: a manual toggle and an auto-detected switch both just
    // change `locale`, and this backfills whatever the open chat is missing.
    useEffect(() => {
        if (!currentSessionId) return;
        void ensureSessionTranslated(currentSessionId, locale);
    }, [locale, currentSessionId, ensureSessionTranslated]);

    const requestFollowUps = async (params: {
        sessionId: string;
        assistantMessageId: string;
        userMessage: string;
        answer: string;
        lang: Lang;
    }) => {
        const applyFollowUps = (items: string[]) => {
            const normalized = normalizeFollowUps(items);
            patchMessage(params.sessionId, params.assistantMessageId, m => ({
                ...m,
                followUps: normalized,
                followUpsStatus: "ready",
            }));
        };

        try {
            const followUpResponse = await fetch("/api/followups", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: params.userMessage,
                    answer: params.answer,
                    user_type: userType,
                    lang: params.lang,
                }),
            });

            if (!followUpResponse.ok) {
                throw new Error("Failed to fetch follow-up questions");
            }

            const followUpData = await followUpResponse.json();
            const followUps = Array.isArray(followUpData.follow_ups)
                ? followUpData.follow_ups
                    .filter((item: unknown): item is string => typeof item === "string" && item.trim().length > 0)
                    .slice(0, 3)
                : [];

            applyFollowUps(followUps);
        } catch (error) {
            console.error(error);
            applyFollowUps([]);
        }
    };

    const sendMessage = async (rawText: string, source: "input" | "followup" = "input") => {
        const trimmedInput = rawText.trim();
        if (!trimmedInput || isLoading) return;

        // Auto-detect drives the global toggle. Only a confident detection may override the
        // locale — short or ambiguous input must not undo a toggle the user just set.
        const detection = detectLanguage(trimmedInput);
        const resolvedLang: Lang = detection.confident ? detection.lang : locale;
        if (detection.confident && detection.lang !== locale) {
            setLocale(detection.lang);
        }

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
            activeSessionId = createNewSession();
        }

        const userMessage: Message = {
            id: createMessageId(),
            role: "user",
            content: trimmedInput,
            lang: resolvedLang,
        };

        setSessions(prev => prev.map(s => {
            if (s.id === activeSessionId) {
                const newTitle =
                    s.messages.length === 0
                        ? trimmedInput.slice(0, 30) + (trimmedInput.length > 30 ? "..." : "")
                        : s.title;
                return { ...s, title: newTitle, messages: [...s.messages, userMessage] };
            }
            return s;
        }));

        if (source === "input") {
            setInput("");
        }
        setIsLoading(true);

        try {
            const currentHistory = (sessions.find(s => s.id === activeSessionId)?.messages || []) as Message[];
            const historyPayload = [...currentHistory, userMessage].map(({ role, content }) => ({ role, content }));

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: userMessage.content,
                    history: historyPayload,
                    user_type: userType,
                    lang: resolvedLang,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || "Failed to fetch response");
            }

            const data = await response.json();
            const assistantMessageId = createMessageId();

            // Generated directly in `resolvedLang`, so no translation is needed unless the
            // user later switches the locale.
            const assistantMessage: Message = {
                id: assistantMessageId,
                role: "assistant",
                content: data.answer,
                lang: resolvedLang,
                translationStatus: "idle",
                followUps: [],
                followUpsStatus: "loading",
            };

            setSessions(prev => prev.map(s => {
                if (s.id === activeSessionId) {
                    return { ...s, messages: [...s.messages, assistantMessage] };
                }
                return s;
            }));

            void requestFollowUps({
                sessionId: activeSessionId,
                assistantMessageId,
                userMessage: userMessage.content,
                answer: data.answer,
                lang: resolvedLang,
            });
        } catch (error: unknown) {
            console.error(error);
            const assistantErrorMessage: Message = {
                id: createMessageId(),
                role: "assistant",
                content: t("chat.errorGeneric"),
                lang: resolvedLang,
                followUps: [],
                followUpsStatus: "idle",
            };

            setSessions(prev => prev.map(s => {
                if (s.id === activeSessionId) {
                    return { ...s, messages: [...s.messages, assistantErrorMessage] };
                }
                return s;
            }));
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await sendMessage(input, "input");
    };

    return (
        <div className="flex h-full bg-[#F7F7F9] text-gray-800 font-sans overflow-hidden">
            {/* Sidebar */}
            <Sidebar
                sessions={sessions}
                currentSessionId={currentSessionId}
                onNewChat={() => setCurrentSessionId(null)}
                onSelectSession={handleSelectSession}
                onDeleteSession={handleDeleteSession}
            />

            {/* Main Content */}
            <div className="flex-1 flex flex-col h-full relative">

                {/* Chat Area */}
                <div className="flex-1 overflow-y-auto w-full">
                    <div className="flex flex-col min-h-full pb-36 pt-10">
                        {(!currentSessionId || messages.length === 0) ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-center px-4 -mt-20">
                                <div className="bg-white p-4 rounded-xl shadow-sm mb-6 flex items-center justify-center">
                                    <div className="relative w-12 h-12">
                                        <Image
                                            src="/logo-icon-v2.png"
                                            alt="Logo"
                                            fill
                                            className="object-contain"
                                        />
                                    </div>
                                </div>
                                <h1 className="text-3xl font-bold mb-2 text-gray-800">{t("chat.welcomeTitle")}</h1>
                                <p className="text-gray-500 max-w-md">{t("chat.welcomeTagline")}</p>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-6 w-full max-w-4xl mx-auto px-4">
                                {messages.map((msg, idx) => (
                                    <ChatMessage
                                        key={msg.id ?? `${idx}-${msg.role}`}
                                        role={msg.role}
                                        content={msg.content}
                                        lang={msg.lang}
                                        translations={msg.translations}
                                        translationStatus={msg.translationStatus}
                                        followUps={msg.followUps}
                                        followUpTranslations={msg.followUpTranslations}
                                        followUpsStatus={msg.followUpsStatus}
                                        onFollowUpClick={(question) => void sendMessage(question, "followup")}
                                        followUpsDisabled={isLoading}
                                    />
                                ))}

                                {isLoading && (
                                    <div className="w-full">
                                        <div className="flex gap-4 p-4 rounded-xl bg-white/50 border border-gray-100">
                                            <div className="w-8 h-8 rounded-sm bg-[#00417d]/10 flex items-center justify-center shrink-0">
                                                <div className="w-2 h-2 bg-[#00417d] rounded-full animate-bounce" />
                                            </div>
                                            <div className="space-y-2 flex-1 max-w-[200px] flex items-center">
                                                <span className="text-sm text-gray-500 font-medium tracking-wide">
                                                    {t("chat.thinking", { seconds: elapsedTime.toFixed(1) })}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                                <div ref={bottomRef} />
                            </div>
                        )}
                    </div>
                </div>

                {/* Input Area */}
                <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-[#F7F7F9] via-[#F7F7F9] to-transparent pt-10 pb-6 px-4">
                    <div className="max-w-3xl mx-auto flex gap-4 items-end">
                        {/* User Type Dropdown. The `value` stays an English key — it routes to the
                            Fuel IX assistant and the prompt personalization; only the label is
                            translated. */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-1 flex shrink-0 mb-1">
                            <select
                                value={userType}
                                onChange={(e) => setUserType(e.target.value as UserType)}
                                disabled={messages.length > 0}
                                className="px-3 py-2 rounded-lg text-sm font-medium bg-transparent border-none focus:ring-0 text-gray-700 cursor-pointer disabled:opacity-50"
                            >
                                {USER_TYPES.map(value => (
                                    <option key={value} value={value}>
                                        {t(`userType.${value}`)}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <form onSubmit={handleSubmit} className="flex-1 relative bg-white rounded-xl shadow-[0_0_20px_rgba(0,0,0,0.05)] border border-gray-100 p-2 focus-within:shadow-[0_0_20px_rgba(0,65,125,0.1)] focus-within:border-[#00417d]/30 transition-all">
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={t("chat.inputPlaceholder", {
                                    userType: t(`userType.${userType}`),
                                })}
                                className="w-full bg-transparent text-gray-800 placeholder-gray-400 border-none focus:ring-0 px-4 py-3 pr-12 text-base"
                                disabled={isLoading}
                                autoFocus
                            />
                            <button
                                type="submit"
                                disabled={isLoading || !input.trim()}
                                aria-label={t("chat.send")}
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-[#00417d] text-white rounded-lg hover:bg-[#002a52] disabled:opacity-50 disabled:hover:bg-[#00417d] transition-colors"
                            >
                                <Send className="w-4 h-4" />
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
}
