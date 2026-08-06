"use client";

import { useEffect } from "react";
import { Loader2 } from "lucide-react";

/**
 * Mounted only while open, rather than kept mounted with an `open` prop, so nothing has to be
 * reset between openings — the component simply has not existed since the last dialog closed.
 *
 * Shared by the pairing workbench and the pipeline runner, which both need the same thing: a
 * last look before something irreversible.
 */
export function ConfirmDialog({
    title,
    body,
    confirmLabel,
    tone = "brand",
    busy,
    onConfirm,
    onCancel,
}: {
    title: string;
    body: React.ReactNode;
    confirmLabel: string;
    tone?: "brand" | "danger";
    busy?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}) {
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") onCancel();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [onCancel]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-gray-900/30 backdrop-blur-[2px]" onClick={onCancel} />
            <div className="relative w-full max-w-md rounded-2xl border border-gray-100 bg-white p-6 shadow-xl">
                <h3 className="text-base font-semibold text-gray-900">{title}</h3>
                <div className="mt-2 text-sm leading-relaxed text-gray-600">{body}</div>

                <div className="mt-5 flex justify-end gap-2">
                    <button
                        onClick={onCancel}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => onConfirm()}
                        disabled={busy}
                        className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                            tone === "danger"
                                ? "bg-rose-600 hover:bg-rose-700"
                                : "bg-[#00417d] hover:bg-[#002a52]"
                        }`}
                    >
                        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
