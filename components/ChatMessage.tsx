import React from "react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface ChatMessageProps {
    role: "user" | "assistant";
    content: string;
}

export function ChatMessage({ role, content }: ChatMessageProps) {
    const isUser = role === "user";

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
