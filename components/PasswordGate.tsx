"use client";

import { useState, useTransition } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { unlockAdmin } from "@/lib/adminAccessAction";
import { unlockDemo } from "@/lib/demoAccessAction";
import { useLocale, useT } from "@/lib/i18n/LanguageProvider";
import { cn } from "@/lib/utils";
import { LanguageToggle } from "./LanguageToggle";

interface PasswordGateProps {
    /**
     * False when the deployment has no password set for this scope. The form is pointless then
     * -- no typed password can match -- so the screen explains the misconfiguration instead of
     * letting someone guess at a lock with no key.
     */
    configured: boolean;
    /**
     * Which lock this form opens: the DEMO_PASSWORD in front of the whole prototype, or the
     * ADMIN_PASSWORD that /admin asks for after it. Only the copy and the action behind the
     * button differ -- deliberately the same screen twice, since on /admin the second one
     * appears immediately after the first.
     */
    scope?: "demo" | "admin";
    /**
     * Admin mounts no LanguageProvider, so its toggle would be inert. Off there, on for the
     * public app, where choosing a language here carries through to every screen after it.
     */
    showLanguageToggle?: boolean;
}

export function PasswordGate({
    configured,
    showLanguageToggle = true,
    scope = "demo",
}: PasswordGateProps) {
    const admin = scope === "admin";
    const fieldId = admin ? "admin-password" : "demo-password";
    const t = useT();
    const { locale } = useLocale();
    const router = useRouter();
    const [password, setPassword] = useState("");
    const [failed, setFailed] = useState(false);
    const [pending, startTransition] = useTransition();

    const submit = (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        startTransition(async () => {
            const result = admin ? await unlockAdmin(password) : await unlockDemo(password);
            if (result !== "ok") {
                setFailed(true);
                setPassword("");
                return;
            }
            // The cookie arrived with the action's response, so re-rendering the layout on the
            // server is all that is left: it re-reads the cookie and swaps this screen for the
            // app behind it.
            router.refresh();
        });
    };

    return (
        // overflow-y-auto: on a short phone in landscape the card is taller than the viewport,
        // and a centred flex item that overflows gets clipped at the top rather than scrolled.
        <div className="flex-1 overflow-y-auto flex items-center justify-center bg-gray-50 p-4 short:p-3">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 short:p-4 sm:p-8 my-auto">
                {/* Same taller box for the French mark as the navbar, for the same reason: its
                    three subtitle lines shrink the wordmark at a shared height. */}
                <div className={cn("relative w-40 short:w-32 sm:w-48 mx-auto", locale === "fr" ? "h-11 short:h-9 sm:h-14" : "h-10 short:h-8 sm:h-12")}>
                    <Image
                        src={t("nav.logo")}
                        alt={t("nav.logoAlt")}
                        fill
                        className="object-contain"
                        priority
                    />
                </div>

                <h1 className="mt-6 short:mt-3 text-xl short:text-lg font-bold text-gray-900 text-center">
                    {t(admin ? "adminGate.title" : "gate.title")}
                </h1>

                {configured ? (
                    <>
                        <p className="mt-3 short:mt-2 text-sm text-gray-600 leading-relaxed text-center">
                            {t(admin ? "adminGate.intro" : "gate.intro")}
                        </p>

                        <form onSubmit={submit} className="mt-6 short:mt-3 space-y-4 short:space-y-2">
                            <div>
                                <label
                                    htmlFor={fieldId}
                                    className="block text-sm font-medium text-gray-700"
                                >
                                    {t(admin ? "adminGate.passwordLabel" : "gate.passwordLabel")}
                                </label>
                                <input
                                    id={fieldId}
                                    type="password"
                                    value={password}
                                    onChange={event => {
                                        setPassword(event.target.value);
                                        setFailed(false);
                                    }}
                                    autoComplete="current-password"
                                    autoFocus
                                    required
                                    aria-invalid={failed}
                                    aria-describedby={failed ? `${fieldId}-error` : undefined}
                                    // text-base: iOS Safari zooms the page in on focus for any
                                    // field under 16px, and this one is autofocused.
                                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2.5 text-base sm:text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>

                            {failed && (
                                <p
                                    id={`${fieldId}-error`}
                                    role="alert"
                                    className="text-sm text-red-600"
                                >
                                    {t("gate.incorrect")}
                                </p>
                            )}

                            <button
                                type="submit"
                                disabled={pending || password.length === 0}
                                className="w-full px-6 py-3 sm:py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {pending ? t("gate.checking") : t("gate.submit")}
                            </button>
                        </form>
                    </>
                ) : (
                    <p role="alert" className="mt-3 text-sm text-red-600 leading-relaxed">
                        {t(admin ? "adminGate.unconfigured" : "gate.unconfigured")}
                    </p>
                )}

                {showLanguageToggle && (
                    <div className="mt-6 short:mt-3 flex justify-center">
                        <LanguageToggle />
                    </div>
                )}
            </div>
        </div>
    );
}
