import { Navbar } from "@/components/Navbar";
import { PasswordGate } from "@/components/PasswordGate";
import { demoPassword, isDemoUnlocked } from "@/lib/demoAccess";

// Deliberately mounts no LanguageProvider and no entry modals. Admin tooling stays English,
// and shared components (ChatMessage) fall back to the English dictionary because useT() finds
// no provider above it. The demo/testing notice and the disclaimer are for visitors, not for
// whoever is running the pipeline.
//
// The password gate does apply here: admin shares the confidential deployment link, its
// pipeline and pairing writes are otherwise unauthenticated, and its batch tool posts to
// /api/chat -- which now requires the same cookie.
export default async function AdminLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    const unlocked = await isDemoUnlocked();

    if (!unlocked) {
        // No language toggle: with no provider above it, it would render inert.
        return <PasswordGate configured={demoPassword() !== null} showLanguageToggle={false} />;
    }

    return (
        <>
            <Navbar />
            <main className="flex-1 overflow-hidden relative">{children}</main>
        </>
    );
}
