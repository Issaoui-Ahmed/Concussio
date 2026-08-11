import { createHash, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

/**
 * The password gate in front of the whole prototype.
 *
 * Server-side by construction: the layouts read this before rendering, so a locked visitor
 * never receives the chatbot's markup or its JavaScript at all -- unlike a client-side check,
 * which ships the thing it is supposed to be protecting and then asks nicely.
 *
 * Importing `next/headers` also makes this module unusable from a client component, which is
 * the point: nothing here may be bundled for the browser.
 */

export const DEMO_ACCESS_COOKIE = "concussio_demo_access";

/**
 * What the cookie carries: a hash of the password, never the password itself, so the browser's
 * cookie jar (and any proxy log along the way) never holds the shared secret in the clear.
 *
 * Derived rather than random because the Python API recomputes the same value from the same
 * environment variable (`api/demo_access.py`). Both halves of the app therefore agree on who is
 * let in with no second secret to keep in sync. It is exactly as strong as the shared password,
 * which is the protection that was asked for -- it does not rotate and does not identify who
 * used it.
 */
export function demoAccessToken(password: string): string {
    return createHash("sha256").update(`concussio-demo-access:${password}`).digest("hex");
}

/**
 * The configured password, or null when the deployment has none.
 *
 * Trimmed because the same value is pasted into a Vercel environment variable and into `.env`,
 * where a stray trailing newline is invisible and would otherwise lock everyone out. The typed
 * password is trimmed the same way in `unlockDemo`, so both sides stay comparable.
 */
export function demoPassword(): string | null {
    const configured = process.env.DEMO_PASSWORD?.trim();
    return configured ? configured : null;
}

export function equalsConstantTime(a: string, b: string): boolean {
    const left = Buffer.from(a, "utf8");
    const right = Buffer.from(b, "utf8");
    // timingSafeEqual throws on a length mismatch, so that case is answered first. Length is
    // the one thing this comparison leaks.
    if (left.length !== right.length) return false;
    return timingSafeEqual(left, right);
}

/**
 * Fails closed: with no DEMO_PASSWORD set, nobody gets in. A missing variable then shows up as
 * a locked site with an explanation on screen, rather than as a prototype quietly serving
 * itself to the open internet.
 */
export async function isDemoUnlocked(): Promise<boolean> {
    const password = demoPassword();
    if (!password) return false;

    const cookie = (await cookies()).get(DEMO_ACCESS_COOKIE)?.value;
    if (!cookie) return false;

    return equalsConstantTime(cookie, demoAccessToken(password));
}
