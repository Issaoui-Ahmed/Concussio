
"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import Image from "next/image";
import { ChatMessage } from "./ChatMessage";
import { Sidebar, Session } from "./Sidebar";
import { Send } from "lucide-react";

type FollowUpsStatus = "idle" | "loading" | "ready" | "error";

interface Message {
    id?: string;
    role: "user" | "assistant";
    content: string;
    followUps?: string[];
    followUpsStatus?: FollowUpsStatus;
}

const createMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

const DEFAULT_FOLLOW_UPS = [
    "Can you explain that in simpler terms?",
    "What should I do first?",
    "What warning signs mean I should seek urgent care?",
];

const normalizeFollowUps = (items: string[]) => {
    const deduped = Array.from(
        new Set(
            items
                .map(item => item.trim())
                .filter(item => item.length > 0)
        )
    );

    for (const fallback of DEFAULT_FOLLOW_UPS) {
        if (deduped.length >= 3) break;
        if (!deduped.includes(fallback)) {
            deduped.push(fallback);
        }
    }

    return deduped.slice(0, 3);
};

export function ChatInterface() {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [elapsedTime, setElapsedTime] = useState(0);
    const bottomRef = useRef<HTMLDivElement>(null);

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

    // Initial Load from LocalStorage
    useEffect(() => {
        const storedSessions = localStorage.getItem("concussio_sessions");
        if (storedSessions) {
            try {
                const parsed = JSON.parse(storedSessions);
                setSessions(parsed);
                if (parsed.length > 0) {
                    // Automatically select most recent or first? 
                    // Let's not auto-select to show empty state like ChatGPT unless they have one
                    // Actually, ChatGPT usually opens clean or last one. Let's start clean if not specified.
                }
            } catch (e) {
                console.error("Failed to parse sessions", e);
            }
        }
    }, []);

    // Save to LocalStorage whenever sessions change
    useEffect(() => {
        localStorage.setItem("concussio_sessions", JSON.stringify(sessions));
    }, [sessions]);

    // Scroll to bottom when messages change
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

    const [userType, setUserType] = useState<string>("Healthcare Professional");

    const updateFollowUpsForMessage = (
        sessionId: string,
        messageId: string,
        followUps: string[],
        followUpsStatus: FollowUpsStatus
    ) => {
        setSessions(prev =>
            prev.map(s => {
                if (s.id !== sessionId) return s;
                return {
                    ...s,
                    messages: s.messages.map((message) => {
                        const typedMessage = message as Message;
                        if (typedMessage.id !== messageId) return typedMessage;
                        return {
                            ...typedMessage,
                            followUps,
                            followUpsStatus,
                        };
                    }),
                };
            })
        );
    };

    const requestFollowUps = async (params: {
        sessionId: string;
        assistantMessageId: string;
        userMessage: string;
        answer: string;
    }) => {
        try {
            const followUpResponse = await fetch("/api/followups", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: params.userMessage,
                    answer: params.answer,
                    user_type: userType,
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

            updateFollowUpsForMessage(
                params.sessionId,
                params.assistantMessageId,
                normalizeFollowUps(followUps),
                "ready"
            );
        } catch (error) {
            console.error(error);
            updateFollowUpsForMessage(
                params.sessionId,
                params.assistantMessageId,
                normalizeFollowUps([]),
                "ready"
            );
        }
    };

    const sendMessage = async (rawText: string, source: "input" | "followup" = "input") => {
        const trimmedInput = rawText.trim();
        if (!trimmedInput || isLoading) return;

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
            activeSessionId = createNewSession();
        }

        const userMessage: Message = {
            id: createMessageId(),
            role: "user",
            content: trimmedInput,
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
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || "Failed to fetch response");
            }

            const data = await response.json();
            const assistantMessageId = createMessageId();
            const assistantMessage: Message = {
                id: assistantMessageId,
                role: "assistant",
                content: data.answer,
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
            });
        } catch (error: unknown) {
            console.error(error);
            const errorMessage = error instanceof Error ? error.message : "Sorry, error occurred.";
            const assistantErrorMessage: Message = {
                id: createMessageId(),
                role: "assistant",
                content: errorMessage,
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
                                <h1 className="text-3xl font-bold mb-2 text-gray-800">ConcussCare</h1>
                                <p className="text-gray-500 max-w-md">Your trusted assistant for concussion healthcare guidelines and patient support.</p>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-6 w-full max-w-4xl mx-auto px-4">
                                {messages.map((msg, idx) => (
                                    <ChatMessage
                                        key={msg.id ?? `${idx}-${msg.role}`}
                                        role={msg.role}
                                        content={msg.content}
                                        followUps={msg.followUps}
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
                                                    Thinking... {elapsedTime.toFixed(1)}s
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
                        {/* User Type Dropdown */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-1 flex shrink-0 mb-1">
                            <select
                                value={userType}
                                onChange={(e) => setUserType(e.target.value)}
                                disabled={messages.length > 0}
                                className="px-3 py-2 rounded-lg text-sm font-medium bg-transparent border-none focus:ring-0 text-gray-700 cursor-pointer disabled:opacity-50"
                            >
                                <option value="Healthcare Professional">Healthcare Professional</option>
                                <option value="Parent or Caregiver">Parent or Caregiver</option>
                                <option value="Youth">Youth</option>
                                <option value="Teacher">Teacher</option>
                                <option value="Coach">Coach</option>
                            </select>
                        </div>

                        <form onSubmit={handleSubmit} className="flex-1 relative bg-white rounded-xl shadow-[0_0_20px_rgba(0,0,0,0.05)] border border-gray-100 p-2 focus-within:shadow-[0_0_20px_rgba(0,65,125,0.1)] focus-within:border-[#00417d]/30 transition-all">
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={`Message as ${userType}...`}
                                className="w-full bg-transparent text-gray-800 placeholder-gray-400 border-none focus:ring-0 px-4 py-3 pr-12 text-base"
                                disabled={isLoading}
                                autoFocus
                            />
                            <button
                                type="submit"
                                disabled={isLoading || !input.trim()}
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
