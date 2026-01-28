"use client";

import React, { useState, useEffect } from "react";
import { Trash2, Plus, Play, Download, Loader2 } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { BatchSidebar, BatchSession } from "./BatchSidebar";
import { cn } from "@/lib/utils";

interface BatchQuestion {
    id: string;
    text: string;
    status: "pending" | "processing" | "completed" | "error";
    answer?: string;
}

export function BatchInterface() {
    const [sessions, setSessions] = useState<BatchSession[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

    // State for the currently active session's data
    const [questions, setQuestions] = useState<BatchQuestion[]>([]);
    const [userType, setUserType] = useState<string>("Healthcare Professional");

    const [isProcessing, setIsProcessing] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Mobile toggle

    // Load Sessions from LocalStorage
    useEffect(() => {
        const stored = localStorage.getItem("concussio_batch_sessions");
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                setSessions(parsed);
                if (parsed.length > 0) {
                    // Load the first session by default if none selected?
                    // Or explicit selection. Let's start with explicit or none.
                    // If we want consistency with ChatInterface, maybe no auto select.
                }
            } catch (e) {
                console.error("Failed to parse batch sessions", e);
            }
        }
    }, []);

    // Save Sessions to LocalStorage
    useEffect(() => {
        localStorage.setItem("concussio_batch_sessions", JSON.stringify(sessions));
    }, [sessions]);

    // Update current session when questions/userType changes
    useEffect(() => {
        if (!currentSessionId) return;

        setSessions(prev => prev.map(s => {
            if (s.id === currentSessionId) {
                // Determine title based on first question or default
                let title = s.title;
                if (questions.length > 0 && questions[0].text.trim() && (s.title === "New Batch" || !s.title)) {
                    title = questions[0].text.substring(0, 30) + (questions[0].text.length > 30 ? "..." : "");
                }

                return {
                    ...s,
                    title,
                    questions: questions,
                    userType: userType // Persist user type in session if we added that field, lets stick to questions for now or add it to BatchSession type implicitly via questions logic or separate field. 
                    // For simplicity, let's just save questions. If we want to save userType per session, we should extend BatchSession, but I'll keeping it simple.
                    // Actually, re-reading the stored data, we might want to store userType too.
                };
            }
            return s;
        }));
    }, [questions, userType, currentSessionId]);

    // Load session data when currentSessionId changes
    useEffect(() => {
        if (!currentSessionId) {
            setQuestions([{ id: "1", text: "", status: "pending" }]);
            setUserType("Healthcare Professional");
            return;
        }

        const session = sessions.find(s => s.id === currentSessionId);
        if (session) {
            setQuestions(session.questions || []);
            // If we stored userType, we would load it here.
        }
    }, [currentSessionId]);

    const createNewSession = () => {
        const newSession: BatchSession = {
            id: Date.now().toString(),
            title: "New Batch",
            questions: [{ id: "1", text: "", status: "pending" }],
            createdAt: Date.now(),
        };
        setSessions(prev => [newSession, ...prev]);
        setCurrentSessionId(newSession.id);
        setQuestions(newSession.questions);
        setIsSidebarOpen(false); // Close sidebar on mobile
    };

    const deleteSession = (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        setSessions(prev => prev.filter(s => s.id !== id));
        if (currentSessionId === id) {
            setCurrentSessionId(null);
        }
    };

    const addQuestion = () => {
        setQuestions(prev => [
            ...prev,
            { id: Date.now().toString(), text: "", status: "pending" }
        ]);

        // If no session exists, create one implicitly on first action? 
        // Or enforce explicit creation? 
        // Let's create one if none exists similar to ChatInterface
        if (!currentSessionId) {
            createNewSession();
        }
    };

    const removeQuestion = (id: string) => {
        setQuestions(prev => prev.filter(q => q.id !== id));
    };

    const updateQuestionText = (id: string, text: string) => {
        setQuestions(prev => prev.map(q =>
            q.id === id ? { ...q, text } : q
        ));
        if (!currentSessionId) {
            createNewSession();
        }
    };

    const runBatch = async () => {
        if (isProcessing) return;

        if (!currentSessionId) {
            createNewSession();
            // Wait for state update? In React batching, might be tricky. 
            // Better to create session first or handle it immediately.
            // For now, let's assume valid session or create one.
            // Actually, `createNewSession` updates state, which is async.
            // We should arguably forcing a session creation before run if none exists.

            // Simpler: Just proceed, the useEffect hook for `questions` change will try to update session, 
            // but if currentSessionId is null, it won't save. 
            // Requires logic fix: `createNewSession` returns ID?
        }

        // Hack: Create session if missing so we can save results
        let activeId = currentSessionId;
        if (!activeId) {
            const newSession: BatchSession = {
                id: Date.now().toString(),
                title: questions[0]?.text.slice(0, 20) || "New Batch",
                questions: questions,
                createdAt: Date.now(),
            };
            setSessions(prev => [newSession, ...prev]);
            setCurrentSessionId(newSession.id);
            activeId = newSession.id;
        }

        setIsProcessing(true);

        const newQuestions = [...questions];

        for (let i = 0; i < newQuestions.length; i++) {
            if (newQuestions[i].status === "completed" || !newQuestions[i].text.trim()) continue;

            setQuestions(prev => prev.map((q, idx) =>
                idx === i ? { ...q, status: "processing" } : q
            ));

            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        message: newQuestions[i].text,
                        history: [],
                        user_type: userType,
                    }),
                });

                if (!response.ok) {
                    throw new Error("Failed to fetch response");
                }

                const data = await response.json();

                setQuestions(prev => prev.map((q, idx) =>
                    idx === i ? { ...q, status: "completed", answer: data.answer } : q
                ));

            } catch (error) {
                console.error(error);
                setQuestions(prev => prev.map((q, idx) =>
                    idx === i ? { ...q, status: "error", answer: "Failed to generate answer." } : q
                ));
            }
        }

        setIsProcessing(false);
    };

    const downloadResults = () => {
        let content = `# Batch Answers Report\n\nGenerated for: ${userType}\nDate: ${new Date().toLocaleDateString()}\n\n`;

        questions.forEach((q, idx) => {
            content += `## Question ${idx + 1}\n\n**Q:** ${q.text}\n\n**A:** ${q.answer || "(No answer generated)"}\n\n---\n\n`;
        });

        const blob = new Blob([content], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `batch_answers_${new Date().toISOString().slice(0, 10)}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const hasAnswers = questions.some(q => q.answer);

    return (
        <div className="flex h-full bg-[#F7F7F9] overflow-hidden">

            <BatchSidebar
                sessions={sessions}
                currentSessionId={currentSessionId}
                onNewBatch={createNewSession}
                onSelectSession={setCurrentSessionId}
                onDeleteSession={deleteSession}
                isOpen={isSidebarOpen}
                onClose={() => setIsSidebarOpen(false)}
            />

            <div className="flex-1 flex flex-col h-full relative overflow-hidden">
                {/* Mobile Header Toggle */}
                <div className="lg:hidden p-4 bg-white border-b border-gray-200 flex items-center gap-4">
                    <button onClick={() => setIsSidebarOpen(true)} className="p-2 text-gray-600">
                        <span className="sr-only">Open Menu</span>
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
                    </button>
                    <span className="font-semibold text-gray-700">Batch Answers</span>
                </div>

                <div className="flex-1 overflow-y-auto p-6">
                    <div className="max-w-4xl mx-auto w-full space-y-8 pb-20">

                        {/* Header */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-800">Batch Answers</h1>
                                <p className="text-gray-500">Generate answers for multiple questions at once.</p>
                            </div>
                            <div className="flex flex-wrap gap-4 items-center">
                                <select
                                    value={userType}
                                    onChange={(e) => setUserType(e.target.value)}
                                    disabled={isProcessing}
                                    className="px-4 py-2 rounded-lg border border-gray-200 bg-white text-sm font-medium focus:ring-2 focus:ring-[#00417d]/20 outline-none"
                                >
                                    <option value="Healthcare Professional">Healthcare Professional</option>
                                    <option value="Parent or Caregiver">Parent or Caregiver</option>
                                    <option value="Youth">Youth</option>
                                    <option value="Teacher">Teacher</option>
                                    <option value="Coach">Coach</option>
                                </select>
                                <button
                                    onClick={runBatch}
                                    disabled={isProcessing || questions.every(q => !q.text.trim())}
                                    className="flex items-center gap-2 px-4 py-2 bg-[#00417d] text-white rounded-lg hover:bg-[#002a52] disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                                >
                                    {isProcessing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                    Run Batch
                                </button>
                            </div>
                        </div>

                        {/* Questions List */}
                        <div className="space-y-6">
                            {questions.map((q, idx) => (
                                <div key={q.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 transition-all">
                                    <div className="flex gap-4 items-start">
                                        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center text-sm font-medium mt-2">
                                            {idx + 1}
                                        </span>
                                        <div className="flex-1 space-y-4">
                                            <div className="flex gap-2">
                                                <textarea
                                                    value={q.text}
                                                    onChange={(e) => updateQuestionText(q.id, e.target.value)}
                                                    placeholder="Enter your question here..."
                                                    disabled={isProcessing || q.status === "completed"}
                                                    className="w-full p-3 rounded-lg border border-gray-200 focus:border-[#00417d] focus:ring-1 focus:ring-[#00417d] outline-none resize-none min-h-[80px]"
                                                />
                                                <button
                                                    onClick={() => removeQuestion(q.id)}
                                                    disabled={isProcessing}
                                                    className="text-gray-400 hover:text-red-500 p-2 transition-colors disabled:opacity-50"
                                                    title="Remove question"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>

                                            {/* Status / Answer Area */}
                                            {q.status !== "pending" && (
                                                <div className="pt-4 border-t border-gray-50">
                                                    {q.status === "processing" && (
                                                        <div className="flex items-center gap-2 text-[#00417d]">
                                                            <Loader2 className="w-4 h-4 animate-spin" />
                                                            <span className="text-sm font-medium">Generating answer...</span>
                                                        </div>
                                                    )}
                                                    {q.status === "error" && (
                                                        <div className="text-red-500 text-sm">Error generating answer.</div>
                                                    )}
                                                    {q.status === "completed" && q.answer && (
                                                        <div className="bg-gray-50 rounded-lg p-4">
                                                            <ChatMessage role="assistant" content={q.answer} />
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Actions Footer */}
                        <div className="flex justify-between items-center py-4">
                            <button
                                onClick={addQuestion}
                                disabled={isProcessing}
                                className="flex items-center gap-2 text-gray-600 hover:text-[#00417d] font-medium transition-colors disabled:opacity-50"
                            >
                                <Plus className="w-4 h-4" />
                                Add Another Question
                            </button>

                            {hasAnswers && (
                                <button
                                    onClick={downloadResults}
                                    className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium shadow-sm"
                                >
                                    <Download className="w-4 h-4" />
                                    Download Results
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
