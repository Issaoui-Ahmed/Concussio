import React from "react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface ChatMessageProps {
    role: "user" | "assistant";
    content: string;
    followUps?: string[];
    followUpsStatus?: "idle" | "loading" | "ready" | "error";
    onFollowUpClick?: (question: string) => void;
    followUpsDisabled?: boolean;
}

export function ChatMessage({
    role,
    content,
    followUps = [],
    followUpsStatus = "idle",
    onFollowUpClick,
    followUpsDisabled = false,
}: ChatMessageProps) {
    const isUser = role === "user";
    const shouldRenderFollowUps =
        !isUser && (
            followUpsStatus === "loading" ||
            (followUpsStatus === "ready" && followUps.length > 0)
        );

    return (
        <div
            className={cn(
                "w-full py-2", // Reduced padding
                // Removed background colors for a cleaner "text on canvas" look, or subtle diff
                isUser ? "" : ""
            )}
        >
            <div className="flex gap-4">
                <div
                    className={cn(
                        "w-8 h-8 rounded-sm flex items-center justify-center shrink-0 overflow-hidden relative",
                        isUser ? "bg-[#ECECF1]" : "bg-transparent" // User gray, Bot transparent for logo
                    )}
                >
                    {isUser ? (
                        <User className="text-gray-500 w-5 h-5" />
                    ) : (
                        <Image
                            src="/logo-icon-v2.png"
                            alt="AI"
                            fill
                            className="object-contain"
                        />
                    )}
                </div>

                <div className="prose prose-slate max-w-none flex-1 leading-7 text-gray-800">
                    {/* Added name label */}
                    <div className="font-semibold text-sm mb-1 text-gray-900">
                        {isUser ? "You" : "ConcussCare"}
                    </div>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>

                    {shouldRenderFollowUps && (
                        <div className="mt-5 border-t border-gray-100 pt-4 not-prose">
                            <h3 className="text-base font-semibold text-gray-800">Ask a follow up</h3>
                            <div className="mt-3 space-y-2">
                                {followUpsStatus === "loading" ? (
                                    Array.from({ length: 3 }).map((_, idx) => (
                                        <div
                                            key={`followup-loading-${idx}`}
                                            className="rounded-xl border border-gray-100 bg-white px-3 py-3"
                                        >
                                            <div className="h-4 w-full rounded bg-gray-100 follow-up-shimmer" />
                                        </div>
                                    ))
                                ) : (
                                    followUps.slice(0, 3).map((question, idx) => (
                                        <button
                                            key={`${question}-${idx}`}
                                            type="button"
                                            onClick={() => onFollowUpClick?.(question)}
                                            disabled={followUpsDisabled}
                                            className="group w-full rounded-xl border border-transparent px-3 py-2 text-left transition-all duration-200 hover:border-[#00417d]/20 hover:bg-[#00417d]/5 hover:translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                            <span className="mr-2 inline-block text-gray-500 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-[#00417d]">
                                                -&gt;
                                            </span>
                                            <span className="text-gray-700 group-hover:text-gray-900">{question}</span>
                                        </button>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Optional: Edit icon only for user, consistent with image */}
                {isUser && (
                    <button className="text-gray-400 hover:text-gray-600">
                        {/* <Edit2 className="w-4 h-4" /> */}
                    </button>
                )}
            </div>
        </div>
    );
}
