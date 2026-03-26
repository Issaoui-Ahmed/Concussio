export type DataItem = Record<string, unknown>;
export type ApiListResponse = { items?: DataItem[] };

export function asErrorMessage(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (!payload || typeof payload !== "object") return "Request failed.";
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (typeof record.message === "string") return record.message;
  if (typeof record.error === "string") return record.error;
  if (Array.isArray(record.detail) && typeof record.detail[0] === "string") return record.detail[0];
  return "Request failed.";
}

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(asErrorMessage(payload));
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
