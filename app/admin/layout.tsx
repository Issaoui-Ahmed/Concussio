import { Navbar } from "@/components/Navbar";

// Deliberately mounts no LanguageProvider and no DisclaimerModal. Admin tooling stays
// English, and shared components (ChatMessage) fall back to the English dictionary because
// useT() finds no provider above it.
export default function AdminLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <>
            <Navbar />
            <main className="flex-1 overflow-hidden relative">{children}</main>
        </>
    );
}
