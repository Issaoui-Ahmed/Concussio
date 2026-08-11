import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ConcussCare",
  description: "Concussion healthcare assistant",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Shrinks the layout viewport when the on-screen keyboard opens, so h-dvh follows it and
  // the composer stays above the keyboard instead of behind it. Honoured by Chrome; iOS
  // Safari ignores it and scrolls the focused field into view instead.
  interactiveWidget: "resizes-content",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The app always boots English (the disclaimer opens in English every session), so
  // rendering lang="en" here is correct by definition. LanguageProvider updates
  // document.documentElement.lang on toggle.
  return (
    <html lang="en">
      <body
        // h-dvh, not h-screen: on mobile browsers 100vh is the viewport *without* the
        // collapsing address bar, so a screen-height column runs under the browser chrome and
        // the composer at its bottom edge is unreachable. dvh tracks the visible height.
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-white text-gray-800 flex flex-col h-dvh`}
      >
        {children}
      </body>
    </html>
  );
}
