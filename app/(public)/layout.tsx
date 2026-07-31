import { DisclaimerModal } from "@/components/DisclaimerModal";
import { Navbar } from "@/components/Navbar";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";

// The bilingual half of the app. /admin has its own layout with no LanguageProvider, so
// shared components fall back to English there.
export default function PublicLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <LanguageProvider>
            <Navbar />
            <main className="flex-1 overflow-hidden relative">
                <DisclaimerModal />
                {children}
            </main>
        </LanguageProvider>
    );
}
