"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * Mounted only while open, rather than kept mounted with an `open` prop. That is what makes the
 * reason field start empty every time without an effect resetting it — the component simply has
 * not existed since the last dialog closed.
 *
 * Shared by the pairing workbench and the pipeline runner, which both need the same two things:
 * a last look before something irreversible, and somewhere to type the admin secret.
 */
export function ConfirmDialog({
    title,
    body,
    confirmLabel,
    tone = "brand",
    withReason,
    reasonLabel,
    reasonPlaceholder,
    busy,
    onConfirm,
    onCancel,
}: {
    title: string;
    body: React.ReactNode;
    confirmLabel: string;
    tone?: "brand" | "danger";
    withReason?: boolean;
    reasonLabel?: string;
    reasonPlaceholder?: string;
    busy?: boolean;
    onConfirm: (reason: string) => void;
    onCancel: () => void;
}) {
    const [reason, setReason] = useState("");

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

                {withReason && (
                    <label className="mt-4 block">
                        <span className="text-xs font-medium uppercase tracking-wide text-gray-400">
                            {reasonLabel ?? "Reason"}
                        </span>
                        <textarea
                            value={reason}
                            onChange={event => setReason(event.target.value)}
                            rows={3}
                            autoFocus
                            placeholder={
                                reasonPlaceholder ??
                                "Why — so the next reviewer does not have to work it out again."
                            }
                            className="mt-1 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none transition-colors placeholder:text-gray-400 focus:border-[#00417d] focus:ring-2 focus:ring-[#00417d]/15"
                        />
                    </label>
                )}

                <div className="mt-5 flex justify-end gap-2">
                    <button
                        onClick={onCancel}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => onConfirm(reason)}
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
