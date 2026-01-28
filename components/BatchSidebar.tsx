"use client";

import React from "react";
import { Plus, MessageSquare, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface BatchSession {
    id: string;
    title: string;
    questions: any[]; // Using any[] to avoid circular dependency, but ideally strict type
    createdAt: number;
}

interface BatchSidebarProps {
    sessions: BatchSession[];
    currentSessionId: string | null;
    onNewBatch: () => void;
    onSelectSession: (id: string) => void;
    onDeleteSession: (e: React.MouseEvent, id: string) => void;
    isOpen?: boolean;     // For mobile responsiveness if needed
    onClose?: () => void; // For mobile responsiveness
}

export function BatchSidebar({
    sessions,
    currentSessionId,
    onNewBatch,
    onSelectSession,
    onDeleteSession,
    isOpen = true,
    onClose
}: BatchSidebarProps) {
    return (
        <>
            {/* Mobile Overlay */}
            <div
                className={cn(
                    "fixed inset-0 bg-black/20 z-20 lg:hidden transition-opacity",
                    isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
                )}
                onClick={onClose}
            />

            {/* Sidebar Container */}
            <div className={cn(
                "fixed lg:static inset-y-0 left-0 z-30 w-64 bg-white border-r border-[#ECECF1] flex flex-col transition-transform duration-300 transform font-sans",
                isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
            )}>
                {/* Header / New Chat Button */}
                <div className="p-4 border-b border-[#ECECF1]">
                    <button
                        onClick={onNewBatch}
                        className="w-full flex items-center gap-3 px-4 py-3 bg-[#00417d] hover:bg-[#002a52] text-white rounded-lg transition-all shadow-sm hover:shadow-md group"
                    >
                        <Plus className="w-5 h-5 group-hover:scale-110 transition-transform" />
                        <span className="font-semibold text-sm">New Batch</span>
                    </button>

                    {/* Mobile Close Button */}
                    <button
                        onClick={onClose}
                        className="lg:hidden absolute top-4 right-4 text-gray-500"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Session List */}
                <div className="flex-1 overflow-y-auto py-2 px-3 space-y-1">
                    <div className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        Your Batches
                    </div>

                    {sessions.length === 0 ? (
                        <div className="text-center py-8 text-sm text-gray-400">
                            No saved batches yet.
                        </div>
                    ) : (
                        sessions.map((session) => {
                            const isActive = session.id === currentSessionId;
                            return (
                                <div
                                    key={session.id}
                                    onClick={() => onSelectSession(session.id)}
                                    className={cn(
                                        "group flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer transition-all duration-200 border border-transparent",
                                        isActive
                                            ? "bg-[#e6efff] border-[#00417d]/10 text-[#00417d]"
                                            : "hover:bg-gray-50 text-gray-700 hover:text-gray-900"
                                    )}
                                >
                                    <MessageSquare className={cn(
                                        "w-4 h-4 shrink-0 transition-colors",
                                        isActive ? "text-[#00417d]" : "text-gray-400 group-hover:text-gray-600"
                                    )} />

                                    <div className="flex-1 overflow-hidden">
                                        <p className="text-sm font-medium truncate">
                                            {session.title || "Untitled Batch"}
                                        </p>
                                        <p className="text-xs text-gray-400 truncate mt-0.5">
                                            {new Date(session.createdAt).toLocaleDateString()}
                                        </p>
                                    </div>

                                    {/* Delete Button (visible on hover or active) */}
                                    <button
                                        onClick={(e) => onDeleteSession(e, session.id)}
                                        className={cn(
                                            "opacity-0 group-hover:opacity-100 p-1.5 rounded-md hover:bg-white hover:text-red-500 transition-all",
                                            isActive && "opacity-100"
                                        )}
                                        title="Delete Batch"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Footer User Profile (Static for now) */}
                <div className="p-4 border-t border-[#ECECF1]">
                    <div className="flex items-center gap-3 px-2 py-2">
                        <div className="w-8 h-8 rounded-full bg-[#00417d] text-white flex items-center justify-center text-xs font-bold">
                            CC
                        </div>
                        <div className="flex-1 overflow-hidden">
                            <p className="text-sm font-medium text-gray-700 truncate">User Account</p>
                            <p className="text-xs text-gray-400 truncate">Healthcare Professional</p>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
