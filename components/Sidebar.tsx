"use client";

import React from "react";
import { Plus, MessageSquare, Trash2, Edit2 } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export interface Session {
    id: string;
    title: string;
    messages: any[]; // Using any for now to avoid circular dependency types, or replicate Message type
    createdAt: number;
}

interface SidebarProps {
    sessions: Session[];
    currentSessionId: string | null;
    onSelectSession: (id: string) => void;
    onNewChat: () => void;
    onDeleteSession: (e: React.MouseEvent, id: string) => void;
}

export function Sidebar({ sessions, currentSessionId, onSelectSession, onNewChat, onDeleteSession }: SidebarProps) {
    return (
        <div className="flex flex-col h-full w-[260px] bg-white border-r border-[#ECECF1] flex-shrink-0">
            {/* Header */}
            <div className="p-4 pt-6">
                <div className="flex items-center justify-between mb-6">
                    <h1 className="text-xl font-bold tracking-tight text-gray-900">ConcussCare</h1>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={onNewChat}
                        className="flex-1 flex items-center justify-center gap-2 bg-[#4361EE] hover:bg-[#3651D4] text-white rounded-full py-3 px-4 transition-colors shadow-sm text-sm font-medium"
                    >
                        <Plus className="w-5 h-5" />
                        New chat
                    </button>
                </div>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6 scrollbar-hide">

                {/* Your Conversations Section */}
                <div>
                    <div className="flex items-center justify-between px-3 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        <span>Your conversations</span>
                    </div>

                    <div className="space-y-1">
                        {sessions.length === 0 ? (
                            <div className="px-3 text-sm text-gray-400 italic">No conversations yet.</div>
                        ) : (
                            sessions.map((session) => (
                                <button
                                    key={session.id}
                                    onClick={() => onSelectSession(session.id)}
                                    className={cn(
                                        "group w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm text-gray-700 hover:bg-gray-100 transition-colors text-left relative",
                                        session.id === currentSessionId && "bg-[#EEF2FF] text-[#4361EE]"
                                    )}
                                >
                                    <MessageSquare className={cn("w-4 h-4 text-gray-400", session.id === currentSessionId && "text-[#4361EE]")} />
                                    <span className="truncate flex-1">{session.title}</span>

                                    {session.id === currentSessionId && (
                                        <div className="absolute right-2 flex items-center gap-1 bg-[#EEF2FF] pl-2">
                                            {/* <Edit2 className="w-3 h-3 text-gray-500 hover:text-gray-700 cursor-pointer" /> */}
                                            <Trash2
                                                onClick={(e) => onDeleteSession(e, session.id)}
                                                className="w-3 h-3 text-gray-500 hover:text-red-500 cursor-pointer"
                                            />
                                        </div>
                                    )}
                                </button>
                            ))
                        )}
                    </div>
                </div>

            </div>

            {/* Footer */}
            <div className="p-4 border-t border-[#ECECF1]"></div>
        </div>
    );
}
