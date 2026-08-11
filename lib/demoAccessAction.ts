"use server";

import { cookies } from "next/headers";
import {
    DEMO_ACCESS_COOKIE,
    demoAccessToken,
    demoPassword,
    equalsConstantTime,
} from "./demoAccess";

export type UnlockResult = "ok" | "incorrect" | "unconfigured";

/**
 * Checks a typed password and, when it matches, hands back the access cookie.
 *
 * A server action rather than a route handler: `vercel.json` rewrites every `/api/*` path to
 * the Python function, so a Next.js endpoint under that prefix would be shadowed in
 * production. Actions POST to the page's own URL and sidestep that entirely.
 */
export async function unlockDemo(typed: string): Promise<UnlockResult> {
    const expected = demoPassword();
    if (!expected) return "unconfigured";

    // Trimmed to match `demoPassword()`: testers paste this out of an email, and a trailing
    // space that nobody can see is not worth a support round-trip.
    if (!equalsConstantTime(typed.trim(), expected)) return "incorrect";

    (await cookies()).set(DEMO_ACCESS_COOKIE, demoAccessToken(expected), {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        // No maxAge, so this is a session cookie: closing the browser asks for the password
        // again. That matches the disclaimer, which sessionStorage already re-shows each
        // session, and keeps a shared or borrowed computer from staying unlocked.
    });

    return "ok";
}
