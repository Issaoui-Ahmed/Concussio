"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { apiFetch, ApiListResponse, DataItem, toDate, toLabel } from "../_lib";
import { FuelIxTabs } from "../_components/FuelIxTabs";

const TOOL_OPTIONS = [
  "image_generation",
  "search_internet",
  "generate_ui",
  "javascript",
  "reasoning",
  "datetime",
  "file_upload",
  "vision",
];

type CopilotPayload = {
  name: string;
  model: string;
  description: string;
  instructions: string;
  metadata?: Record<string, unknown>;
  temperature?: number;
  top_p?: number;
  tools: Array<{ type: string }>;
  tool_resources?: { file_search: { vector_store_ids: string[] } };
};

function parseJson(value: string): Record<string, unknown> | undefined {
  if (!value.trim()) return undefined;
  return JSON.parse(value) as Record<string, unknown>;
}

export default function FuelIxCopilotsPage() {
  const [copilots, setCopilots] = useState<DataItem[]>([]);
  const [vectorStores, setVectorStores] = useState<DataItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [model, setModel] = useState("claude-sonnet-4-5");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [metadataText, setMetadataText] = useState("");
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");
  const [tools, setTools] = useState<string[]>([]);
  const [vectorStoreIds, setVectorStoreIds] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);

  const resetForm = () => {
    setName("");
    setModel("claude-sonnet-4-5");
    setDescription("");
    setInstructions("");
    setMetadataText("");
    setTemperature("");
    setTopP("");
    setTools([]);
    setVectorStoreIds("");
    setEditingId(null);
  };

  const refreshData = useCallback(async (manual: boolean) => {
    if (manual) setIsRefreshing(true);
    try {
      const [copilotRes, vectorRes] = await Promise.all([
        apiFetch<ApiListResponse>("/api/fuelix/copilots"),
        apiFetch<ApiListResponse>("/api/fuelix/vector-stores"),
      ]);
      setCopilots(copilotRes.items ?? []);
      setVectorStores(vectorRes.items ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load copilots.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refreshData(false);
  }, [refreshData]);

  const buildPayload = (): CopilotPayload => {
    const ids = vectorStoreIds
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    return {
      name: name.trim(),
      model: model.trim(),
      description: description.trim(),
      instructions: instructions.trim(),
      metadata: parseJson(metadataText),
      temperature: temperature ? Number(temperature) : undefined,
      top_p: topP ? Number(topP) : undefined,
      tools: tools.map((type) => ({ type })),
      tool_resources: ids.length ? { file_search: { vector_store_ids: ids } } : undefined,
    };
  };

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setBusyKey("create");
    setError(null);
    setSuccess(null);
    try {
      await apiFetch("/api/fuelix/copilots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      setSuccess("Copilot created.");
      resetForm();
      await refreshData(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create copilot.");
    } finally {
      setBusyKey(null);
    }
  };

  const startEdit = (item: DataItem) => {
    setEditingId(toLabel(item.id));
    setName(toLabel(item.name));
    setModel(toLabel(item.model));
    setDescription(toLabel(item.description) === "n/a" ? "" : toLabel(item.description));
    setInstructions(toLabel(item.instructions) === "n/a" ? "" : toLabel(item.instructions));
    const metadata = item.metadata;
    setMetadataText(
      metadata && typeof metadata === "object" ? JSON.stringify(metadata, null, 2) : ""
    );
    setTemperature(
      typeof item.temperature === "number" ? String(item.temperature) : ""
    );
    setTopP(typeof item.top_p === "number" ? String(item.top_p) : "");
    const rawTools = Array.isArray(item.tools) ? item.tools : [];
    const nextTools = rawTools
      .map((tool) => {
        if (!tool || typeof tool !== "object") return null;
        const value = (tool as Record<string, unknown>).type;
        return typeof value === "string" ? value : null;
      })
      .filter((value): value is string => Boolean(value));
    setTools(nextTools);
    const resources =
      item.tool_resources && typeof item.tool_resources === "object"
        ? (item.tool_resources as Record<string, unknown>)
        : null;
    const fs = resources?.file_search;
    const fsObj = fs && typeof fs === "object" ? (fs as Record<string, unknown>) : null;
    const ids = Array.isArray(fsObj?.vector_store_ids)
      ? (fsObj?.vector_store_ids as unknown[])
          .map((value) => (typeof value === "string" ? value : ""))
          .filter(Boolean)
      : [];
    setVectorStoreIds(ids.join(", "));
    setError(null);
    setSuccess(null);
  };

  const handleUpdate = async (event: FormEvent) => {
    event.preventDefault();
    if (!editingId) return;
    setBusyKey(`update-${editingId}`);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`/api/fuelix/copilots/${editingId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      setSuccess("Copilot updated.");
      resetForm();
      await refreshData(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update copilot.");
    } finally {
      setBusyKey(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this copilot?")) return;
    setBusyKey(`delete-${id}`);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`/api/fuelix/copilots/${id}`, { method: "DELETE" });
      setSuccess("Copilot deleted.");
      if (editingId === id) resetForm();
      await refreshData(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete copilot.");
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#F7F7F9] p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Copilots</h1>
              <p className="text-sm text-gray-600">Create, edit, and delete assistants.</p>
            </div>
            <button
              onClick={() => void refreshData(true)}
              disabled={isRefreshing}
              className="inline-flex items-center gap-2 rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white hover:bg-[#002a52] disabled:opacity-60"
            >
              {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </button>
          </div>
          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </div>
          )}
          {success && (
            <div className="mt-4 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {success}
            </div>
          )}
        </section>

        <FuelIxTabs />

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              {editingId ? "Edit Copilot" : "Create Copilot"}
            </h2>
            <form
              onSubmit={editingId ? handleUpdate : handleCreate}
              className="mt-4 space-y-2"
            >
              <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <input required value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <input required value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <textarea required value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Instructions" className="h-28 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <div className="grid grid-cols-2 gap-2">
                <input value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="Temperature (0-2)" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                <input value={topP} onChange={(e) => setTopP(e.target.value)} placeholder="Top P (0-1)" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </div>
              <input value={vectorStoreIds} onChange={(e) => setVectorStoreIds(e.target.value)} placeholder="Vector store IDs for file_search (comma separated)" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <textarea value={metadataText} onChange={(e) => setMetadataText(e.target.value)} placeholder='Metadata JSON (optional)' className="h-20 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <div className="grid grid-cols-2 gap-1 text-xs text-gray-700">
                {TOOL_OPTIONS.map((tool) => (
                  <label key={tool} className="inline-flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={tools.includes(tool)}
                      onChange={(e) =>
                        setTools((prev) =>
                          e.target.checked
                            ? [...prev, tool]
                            : prev.filter((entry) => entry !== tool)
                        )
                      }
                    />
                    {tool}
                  </label>
                ))}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  disabled={Boolean(busyKey)}
                  className="rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {busyKey?.startsWith("update-")
                    ? "Updating..."
                    : busyKey === "create"
                    ? "Creating..."
                    : editingId
                    ? "Update copilot"
                    : "Create copilot"}
                </button>
                {editingId && (
                  <button
                    type="button"
                    onClick={resetForm}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel edit
                  </button>
                )}
              </div>
            </form>

            {vectorStores.length > 0 && (
              <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
                <p className="font-semibold text-gray-800">Available vector store IDs:</p>
                <p className="mt-1 break-all">
                  {vectorStores.map((store) => toLabel(store.id)).join(", ")}
                </p>
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Existing Copilots</h2>
            {isLoading ? (
              <div className="mt-4 text-center text-gray-500">
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-[#00417d]" />
              </div>
            ) : copilots.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500">No copilots found.</p>
            ) : (
              <div className="mt-4 space-y-2">
                {copilots.map((item, index) => {
                  const id = toLabel(item.id);
                  return (
                    <article key={`${id}-${index}`} className="rounded-lg border border-gray-200 p-3 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-gray-900">{toLabel(item.name)}</p>
                          <p className="truncate text-xs text-gray-500">{id}</p>
                          <p className="mt-1 text-xs text-gray-600">Model: {toLabel(item.model)}</p>
                          <p className="text-xs text-gray-600">Created: {toDate(item.created_at)}</p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => startEdit(item)}
                            className="inline-flex items-center gap-1 rounded-md border border-blue-200 px-2 py-1 text-xs text-blue-700 hover:bg-blue-50"
                          >
                            <Pencil className="h-3 w-3" />
                            Edit
                          </button>
                          <button
                            onClick={() => void handleDelete(id)}
                            disabled={busyKey === `delete-${id}`}
                            className="inline-flex items-center gap-1 rounded-md border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-60"
                          >
                            {busyKey === `delete-${id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                            Delete
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
