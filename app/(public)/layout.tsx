import { EntryModals } from "@/components/EntryModals";
import { Navbar } from "@/components/Navbar";
import { PasswordGate } from "@/components/PasswordGate";
import { demoPassword, isDemoUnlocked } from "@/lib/demoAccess";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";

// The bilingual half of the app. /admin has its own layout with no LanguageProvider, so
// shared components fall back to English there.
export default async function PublicLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    // Password first, then the demo/testing notice and the disclaimer inside EntryModals.
    // Locked visitors are served the gate in place of `children`, so no chat markup and no
    // answer reaches a browser that has not passed it. (The static JS chunks stay fetchable by
    // URL, as in any Next app -- what they cannot do is reach /api/chat, which checks the same
    // cookie.)
    const unlocked = await isDemoUnlocked();

    if (!unlocked) {
        return (
            <LanguageProvider>
                <PasswordGate configured={demoPassword() !== null} />
            </LanguageProvider>
        );
    }

    return (
        <LanguageProvider>
            <Navbar />
            <main className="flex-1 overflow-hidden relative">
                <EntryModals />
                {children}
            </main>
        </LanguageProvider>
    );
}
