"use client";

import { LanguageToggle } from "./LanguageToggle";

interface EntryDialogProps {
    /** Prefixes the heading id, so each step in the sequence labels its own dialog. */
    id: string;
    title: string;
    /** The single button that advances to the next step. */
    actionLabel: string;
    onAction: () => void;
    children: React.ReactNode;
}

/**
 * The chrome shared by the demo/testing notice and the disclaimer: one blocking overlay, a
 * heading with the language toggle beside it, a scrollable body, one button out.
 *
 * Choosing a language in either header sets it for the whole app.
 */
export function EntryDialog({ id, title, actionLabel, onAction, children }: EntryDialogProps) {
    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${id}-title`}
            className="fixed inset-0 z-50 flex items-center justify-center p-3 short:p-2 sm:p-4 bg-black/50 backdrop-blur-sm"
        >
            {/* dvh, not vh: on a phone 90vh is measured against the viewport with the address
                bar hidden, so the "I Understand" button sits below the fold on first paint.
                The heading and the button are pinned; only the text between them scrolls, so
                the way out of the dialog is on screen at every viewport size. */}
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[calc(100dvh-1.5rem)] short:max-h-[calc(100dvh-1rem)] sm:max-h-[90dvh] flex flex-col overflow-hidden">
                <div className="flex items-start justify-between gap-3 px-4 pt-5 short:pt-3 sm:px-6 sm:pt-6">
                    <h2 id={`${id}-title`} className="text-lg short:text-base sm:text-xl font-bold text-gray-900">
                        {title}
                    </h2>
                    <div className="shrink-0">
                        <LanguageToggle showLabel={false} />
                    </div>
                </div>
                <div className="px-4 pb-5 pt-3 short:pb-3 short:pt-2 sm:p-6 sm:pt-4 overflow-y-auto overscroll-contain">
                    <div className="space-y-4 short:space-y-2 text-gray-700 text-sm leading-relaxed">{children}</div>
                </div>
                <div className="p-3 short:p-2 sm:p-4 border-t border-gray-100 bg-gray-50 flex justify-end">
                    <button
                        onClick={onAction}
                        className="w-full short:w-auto sm:w-auto px-6 py-3 short:py-2 sm:py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                        {actionLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
