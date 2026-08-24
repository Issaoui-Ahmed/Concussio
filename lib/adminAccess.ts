import { createHash } from "node:crypto";
import { cookies } from "next/headers";
import { equalsConstantTime } from "./demoAccess";

/**
 * The second password, in front of /admin only.
 *
 * A separate secret rather than a stronger demo password: every invited tester is given
 * DEMO_PASSWORD, and admin can rerun the content pipeline, rewrite pairings and delete Fuel IX
 * vector stores. This gate is asked for *after* the demo one (`app/admin/layout.tsx`), so admin
 * sits behind both and holding the shared demo link is not enough to reach the tooling.
 *
 * Server-side for the same reason as `lib/demoAccess.ts`: importing `next/headers` makes the
 * module unusable from a client component, so none of this can be bundled for the browser, and
 * a locked visitor never receives the admin markup at all.
 */

export const ADMIN_ACCESS_COOKIE = "concussio_admin_access";

/**
 * A different hash prefix from the demo token, so the two cookies stay distinct even when both
 * variables are set to the same string -- neither can be replayed as the other.
 *
 * Nothing outside Next.js recomputes this one: unlike the demo token, which `api/demo_access.py`
 * derives from the same variable, the admin gate is a page gate only. The endpoints the admin
 * pages call are not gated on it -- see the README.
 */
export function adminAccessToken(password: string): string {
    return createHash("sha256").update(`concussio-admin-access:${password}`).digest("hex");
}

/**
 * The configured admin password, or null when the deployment has none. Trimmed for the reason
 * `demoPassword()` is: the value is pasted into a Vercel environment variable, where a trailing
 * newline is invisible and would otherwise lock everyone out.
 */
export function adminPassword(): string | null {
    const configured = process.env.ADMIN_PASSWORD?.trim();
    return configured ? configured : null;
}

/**
 * Fails closed: with no ADMIN_PASSWORD set, nobody reaches /admin. A missing variable shows up
 * as a locked admin section with an explanation on screen, not as open tooling.
 */
export async function isAdminUnlocked(): Promise<boolean> {
    const password = adminPassword();
    if (!password) return false;

    const cookie = (await cookies()).get(ADMIN_ACCESS_COOKIE)?.value;
    if (!cookie) return false;

    return equalsConstantTime(cookie, adminAccessToken(password));
}
