"use client";

import React from "react";
import { Plus, MessageSquare, Trash2, X } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { useT } from "@/lib/i18n/LanguageProvider";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export interface Session {
    id: string;
    title: string;
    // `unknown[]` avoids a circular type dependency on ChatInterface's Message; callers cast.
    messages: unknown[];
    createdAt: number;
    // NOTE: `displayLang` was removed. Display language is now derived from the global app
    // locale (LanguageProvider), which is what makes one toggle switch every open chat.
}

interface SidebarProps {
    sessions: Session[];
    currentSessionId: string | null;
    onSelectSession: (id: string) => void;
    onNewChat: () => void;
    onDeleteSession: (e: React.MouseEvent, id: string) => void;
    /** Drawer state. Ignored at md+, where the sidebar is a permanent column. */
    open: boolean;
    onClose: () => void;
}

export function Sidebar({
    sessions,
    currentSessionId,
    onSelectSession,
    onNewChat,
    onDeleteSession,
    open,
    onClose,
}: SidebarProps) {
    const t = useT();

    // Picking a conversation on a phone means the drawer has served its purpose. At md+ the
    // sidebar never moves, so closing it there is a no-op.
    const selectAndClose = (id: string) => {
        onSelectSession(id);
        onClose();
    };

    const newChatAndClose = () => {
        onNewChat();
        onClose();
    };

    return (
        <>
            {/* Backdrop: only ever visible while the drawer is out, i.e. below md. */}
            {open && (
                <div
                    className="absolute inset-0 z-30 bg-black/40 md:hidden"
                    onClick={onClose}
                    aria-hidden="true"
                />
            )}

            <div
                className={cn(
                    "flex flex-col h-full bg-white border-r border-[#ECECF1] flex-shrink-0",
                    // Below md the sidebar is an overlay drawer: a permanent 260px column would
                    // leave a phone barely 100px for the conversation itself.
                    "absolute inset-y-0 left-0 z-40 w-[85%] max-w-[300px] shadow-xl",
                    "transition-transform duration-200 ease-out",
                    // `invisible`, not just the offscreen transform: a translated element is
                    // still focusable and still read out by screen readers. Paired with
                    // md:visible so the breakpoint alone decides, with no JS media query that
                    // could desync and leave the permanent column unreachable.
                    open ? "translate-x-0" : "-translate-x-full invisible",
                    // At md+ it goes back to being an ordinary column in the flex row.
                    "md:static md:z-auto md:w-[260px] md:max-w-none md:translate-x-0 md:visible md:shadow-none md:transition-none"
                )}
            >
                {/* Header */}
                <div className="p-4 pt-4 md:pt-6">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={newChatAndClose}
                            className="flex-1 flex items-center justify-center gap-2 bg-[#00417d] hover:bg-[#002a52] text-white rounded-full py-3 px-4 transition-colors shadow-sm text-sm font-medium"
                        >
                            <Plus className="w-5 h-5" />
                            {t("sidebar.newChat")}
                        </button>

                        <button
                            onClick={onClose}
                            aria-label={t("sidebar.close")}
                            className="md:hidden shrink-0 rounded-full p-2.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Scrollable Content */}
                <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6 scrollbar-hide">

                    {/* Your Conversations Section */}
                    <div>
                        <div className="flex items-center justify-between px-3 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                            <span>{t("sidebar.yourConversations")}</span>
                        </div>

                        <div className="space-y-1">
                            {sessions.length === 0 ? (
                                <div className="px-3 text-sm text-gray-400 italic">{t("sidebar.noConversations")}</div>
                            ) : (
                                sessions.map((session) => (
                                    <button
                                        key={session.id}
                                        onClick={() => selectAndClose(session.id)}
                                        className={cn(
                                            "group w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm text-gray-700 hover:bg-gray-100 transition-colors text-left relative",
                                            session.id === currentSessionId && "bg-[#e6efff] text-[#00417d]"
                                        )}
                                    >
                                        <MessageSquare className={cn("w-4 h-4 text-gray-400 shrink-0", session.id === currentSessionId && "text-[#00417d]")} />
                                        <span className="truncate flex-1">{session.title}</span>

                                        {session.id === currentSessionId && (
                                            // Padded rather than sized up, so the icon still
                                            // reads small but the tap target is finger-sized.
                                            <div className="absolute right-1 flex items-center gap-1 bg-[#e6efff] py-2 pl-2 pr-1">
                                                <Trash2
                                                    onClick={(e) => onDeleteSession(e, session.id)}
                                                    aria-label={t("sidebar.deleteChat")}
                                                    className="w-4 h-4 text-gray-500 hover:text-red-500 cursor-pointer"
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
        </>
    );
}
