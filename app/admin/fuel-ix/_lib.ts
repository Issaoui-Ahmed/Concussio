export type DataItem = Record<string, unknown>;
export type ApiListResponse = { items?: DataItem[] };

function findErrorMessage(payload: unknown): string | null {
  if (typeof payload === "string") {
    const message = payload.trim();
    return message || null;
  }
  if (!payload || typeof payload !== "object") return null;
  if (Array.isArray(payload)) {
    const messages = payload
      .map(findErrorMessage)
      .filter((message): message is string => Boolean(message));
    return messages.length ? messages.join("; ") : null;
  }

  const record = payload as Record<string, unknown>;
  for (const key of ["detail", "message", "error", "errors", "msg"]) {
    const message = findErrorMessage(record[key]);
    if (message) return message;
  }

  return null;
}

export function asErrorMessage(payload: unknown, fallback = "Request failed."): string {
  return findErrorMessage(payload) ?? fallback;
}

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  let payload: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  } else {
    const text = await response.text();
    payload = text.trim() || null;
  }

  if (!response.ok) {
    const status = response.statusText
      ? `${response.status} ${response.statusText}`
      : String(response.status);
    const fallback = `Request failed (${status}).`;
    const message = asErrorMessage(payload, fallback);
    throw new Error(
      message.toLowerCase() === response.statusText.toLowerCase()
        ? fallback
        : message
    );
  }
  return payload as T;
}

export function toLabel(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "n/a";
}

export function toDate(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return "n/a";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(n)) {
    const ms = n > 10_000_000_000 ? n : n * 1000;
    return new Date(ms).toLocaleString();
  }
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.valueOf()) ? "n/a" : parsed.toLocaleString();
}
