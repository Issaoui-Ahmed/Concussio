/**
 * The admin secret, held in session storage and nowhere else.
 *
 * Session rather than local storage on purpose: it survives a reload, so a reviewer working
 * through the pairing list is not re-prompted every time, but it does not survive the tab. The
 * value gates writes to the pairing table and to the content pipeline, and a shared machine is
 * the normal case for a clinic.
 */
export const SECRET_KEY = "concussio.adminSecret";

export function readAdminSecret(): string {
    if (typeof window === "undefined") return "";
    return window.sessionStorage.getItem(SECRET_KEY) ?? "";
}

export function writeAdminSecret(secret: string): void {
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(SECRET_KEY, secret);
}
