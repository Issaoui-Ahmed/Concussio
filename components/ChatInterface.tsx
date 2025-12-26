
"use client";

import React, { useState, useRef, useEffect } from "react";
import { ChatMessage } from "./ChatMessage";
import { Sidebar, Session } from "./Sidebar";
import { Send, Sparkles } from "lucide-react";

interface Message {
    role: "user" | "assistant";
    content: string;
}

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
    const messages = currentSession ? currentSession.messages : [];

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

    const [userType, setUserType] = useState<"patient" | "doctor">("patient");

    // ... existing code ...

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
            activeSessionId = createNewSession();
        }

        const userMessage: Message = { role: "user", content: input };

        // Optimistic Update
        setSessions(prev => prev.map(s => {
            if (s.id === activeSessionId) {
                // If it's the first message, update title
                const newTitle = s.messages.length === 0 ? input.slice(0, 30) + (input.length > 30 ? "..." : "") : s.title;
                return { ...s, title: newTitle, messages: [...s.messages, userMessage] };
            }
            return s;
        }));

        setInput("");
        setIsLoading(true);

        try {
            const currentHistory = sessions.find(s => s.id === activeSessionId)?.messages || [];

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: userMessage.content,
                    history: [...currentHistory, userMessage],
                    user_type: userType, // Pass user type
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || "Failed to fetch response");
            }

            const data = await response.json();
            const assistantMessage: Message = {
                role: "assistant",
                content: data.answer,
            };

            setSessions(prev => prev.map(s => {
                if (s.id === activeSessionId) {
                    return { ...s, messages: [...s.messages, assistantMessage] };
                }
                return s;
            }));

        } catch (error: any) {
            console.error(error);
            setSessions(prev => prev.map(s => {
                if (s.id === activeSessionId) {
                    return { ...s, messages: [...s.messages, { role: "assistant", content: error.message || "Sorry, error occurred." }] };
                }
                return s;
            }));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex h-screen bg-[#F7F7F9] text-gray-800 font-sans overflow-hidden">
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
                                <div className="bg-white p-4 rounded-xl shadow-sm mb-6">
                                    <Sparkles className="w-8 h-8 text-[#4361EE]" />
                                </div>
                                <h1 className="text-3xl font-bold mb-2 text-gray-800">ConcussCare</h1>
                                <p className="text-gray-500 max-w-md">Your trusted assistant for concussion healthcare guidelines and patient support.</p>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-6 w-full max-w-4xl mx-auto px-4">
                                {messages.map((msg, idx) => (
                                    <ChatMessage key={idx} role={msg.role} content={msg.content} />
                                ))}

                                {isLoading && (
                                    <div className="w-full">
                                        <div className="flex gap-4 p-4 rounded-xl bg-white/50 border border-gray-100">
                                            <div className="w-8 h-8 rounded-sm bg-[#4361EE]/10 flex items-center justify-center shrink-0">
                                                <div className="w-2 h-2 bg-[#4361EE] rounded-full animate-bounce" />
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
                        {/* User Type Toggle */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-1 flex shrink-0 mb-1">
                            <button
                                type="button"
                                onClick={() => setUserType("patient")}
                                disabled={messages.length > 0}
                                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${userType === "patient"
                                    ? "bg-[#4361EE] text-white"
                                    : "text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                    }`}
                            >
                                Patient
                            </button>
                            <button
                                type="button"
                                onClick={() => setUserType("doctor")}
                                disabled={messages.length > 0}
                                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${userType === "doctor"
                                    ? "bg-[#4361EE] text-white"
                                    : "text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                    }`}
                            >
                                Doctor
                            </button>
                        </div>

                        <form onSubmit={handleSubmit} className="flex-1 relative bg-white rounded-xl shadow-[0_0_20px_rgba(0,0,0,0.05)] border border-gray-100 p-2 focus-within:shadow-[0_0_20px_rgba(67,97,238,0.1)] focus-within:border-[#4361EE]/30 transition-all">
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
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-[#4361EE] text-white rounded-lg hover:bg-[#3651D4] disabled:opacity-50 disabled:hover:bg-[#4361EE] transition-colors"
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
