import { Navbar } from "@/components/Navbar";
import { PasswordGate } from "@/components/PasswordGate";
import { adminPassword, isAdminUnlocked } from "@/lib/adminAccess";
import { demoPassword, isDemoUnlocked } from "@/lib/demoAccess";

// Deliberately mounts no LanguageProvider and no entry modals. Admin tooling stays English,
// and shared components (ChatMessage) fall back to the English dictionary because useT() finds
// no provider above it. The demo/testing notice and the disclaimer are for visitors, not for
// whoever is running the pipeline.
//
// Two password gates apply here, asked for in order. The demo one first, because admin
// shares the confidential deployment link and its batch tool posts to /api/chat, which
// requires that cookie. Then a second, admin-only password: every invited tester holds the
// demo one, and these pages rerun the content pipeline, rewrite pairings and delete Fuel IX
// vector stores. Stacked rather than swapped, so adding the second password only ever narrows
// who gets in.
export default async function AdminLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    // No language toggle on either gate: with no provider above it, it would render inert.
    if (!(await isDemoUnlocked())) {
        return <PasswordGate configured={demoPassword() !== null} showLanguageToggle={false} />;
    }

    if (!(await isAdminUnlocked())) {
        return (
            <PasswordGate
                scope="admin"
                configured={adminPassword() !== null}
                showLanguageToggle={false}
            />
        );
    }

    return (
        <>
            <Navbar />
            <main className="flex-1 overflow-hidden relative">{children}</main>
        </>
    );
}
