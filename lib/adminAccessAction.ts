"use server";

import { cookies } from "next/headers";
import { ADMIN_ACCESS_COOKIE, adminAccessToken, adminPassword } from "./adminAccess";
import { equalsConstantTime } from "./demoAccess";
import type { UnlockResult } from "./demoAccessAction";

/**
 * Checks a typed admin password and, when it matches, hands back the admin access cookie.
 *
 * A server action rather than a route handler, like `unlockDemo`: `vercel.json` rewrites every
 * `/api/*` path to the Python function, so a Next.js endpoint under that prefix would be
 * shadowed in production.
 */
export async function unlockAdmin(typed: string): Promise<UnlockResult> {
    const expected = adminPassword();
    if (!expected) return "unconfigured";

    if (!equalsConstantTime(typed.trim(), expected)) return "incorrect";

    (await cookies()).set(ADMIN_ACCESS_COOKIE, adminAccessToken(expected), {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        // A session cookie, matching the demo gate: closing the browser re-asks for both.
    });

    return "ok";
}
