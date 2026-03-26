"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Pencil, RefreshCw, Trash2, Upload } from "lucide-react";
import { apiFetch, ApiListResponse, DataItem, toDate, toLabel } from "../_lib";
import { FuelIxTabs } from "../_components/FuelIxTabs";

type VectorStoreFileList = {
  object?: string;
  data?: DataItem[];
};

function parseJson(value: string): Record<string, unknown> | undefined {
  if (!value.trim()) return undefined;
  return JSON.parse(value) as Record<string, unknown>;
}

function asNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

export default function FuelIxVectorStoresPage() {
  const [vectorStores, setVectorStores] = useState<DataItem[]>([]);
  const [storeFiles, setStoreFiles] = useState<Record<string, DataItem[]>>({});
  const [selectedFiles, setSelectedFiles] = useState<Record<string, File[]>>({});

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [metadataText, setMetadataText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const resetForm = () => {
    setName("");
    setMetadataText("");
    setEditingId(null);
  };

  const refreshStores = useCallback(async (manual: boolean) => {
    if (manual) setIsRefreshing(true);
    try {
      const response = await apiFetch<ApiListResponse>("/api/fuelix/vector-stores");
      setVectorStores(response.items ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load vector stores.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refreshStores(false);
  }, [refreshStores]);

  const loadStoreFiles = async (storeId: string) => {
    setBusyKey(`files-${storeId}`);
    try {
      const [payload, filesCatalog] = await Promise.all([
        apiFetch<VectorStoreFileList>(`/api/fuelix/vector-stores/${storeId}/files`),
        apiFetch<ApiListResponse>("/api/fuelix/files?limit=100").catch(() => ({ items: [] })),
      ]);

      const files = payload.data ?? [];
      const catalogItems = filesCatalog.items ?? [];
      const namesById = new Map<string, { filename?: string; alias_id?: string }>();

      for (const item of catalogItems) {
        const id = toLabel(item.id);
        if (id === "n/a") continue;
        const filename = asNonEmptyString(item.filename);
        const aliasId = asNonEmptyString(item.alias_id);
        if (filename || aliasId) {
          namesById.set(id, { filename, alias_id: aliasId });
        }
      }

      const unresolvedIds: string[] = [];
      let filesWithNames = files.map((item) => {
        const fileId = toLabel(item.id);
        if (fileId === "n/a") return item;
        const fromCatalog = namesById.get(fileId);
        if (fromCatalog) {
          return { ...item, ...fromCatalog };
        }
        unresolvedIds.push(fileId);
        return item;
      });

      if (unresolvedIds.length > 0) {
        const fallbackResults: Array<{ fileId: string; filename?: string; alias_id?: string } | null> = [];
        for (const fileId of unresolvedIds) {
          let resolved: { fileId: string; filename?: string; alias_id?: string } | null = null;
          for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
              const fileDetails = await apiFetch<DataItem>(`/api/fuelix/files/${fileId}`);
              const filename = asNonEmptyString(fileDetails.filename);
              const aliasId = asNonEmptyString(fileDetails.alias_id);
              if (filename || aliasId) {
                resolved = { fileId, filename, alias_id: aliasId };
              }
              break;
            } catch {
              if (attempt === 1) break;
            }
          }
          fallbackResults.push(resolved);
        }

        const fallbackMap = new Map<string, { filename?: string; alias_id?: string }>();
        for (const row of fallbackResults) {
          if (!row) continue;
          fallbackMap.set(row.fileId, { filename: row.filename, alias_id: row.alias_id });
        }

        filesWithNames = filesWithNames.map((item) => {
          const fileId = toLabel(item.id);
          if (fileId === "n/a") return item;
          const fromFallback = fallbackMap.get(fileId);
          return fromFallback ? { ...item, ...fromFallback } : item;
        });
      }

      setStoreFiles((prev) => ({ ...prev, [storeId]: filesWithNames }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load store files.");
    } finally {
      setBusyKey(null);
    }
  };

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setBusyKey("create-store");
    setError(null);
    setSuccess(null);
    try {
      await apiFetch("/api/fuelix/vector-stores", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          metadata: parseJson(metadataText),
        }),
      });
      setSuccess("Vector store created.");
      resetForm();
      await refreshStores(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create vector store.");
    } finally {
      setBusyKey(null);
    }
  };

  const handleUpdate = async (event: FormEvent) => {
    event.preventDefault();
    if (!editingId) return;
    setBusyKey(`update-${editingId}`);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`/api/fuelix/vector-stores/${editingId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          metadata: parseJson(metadataText),
        }),
      });
      setSuccess("Vector store updated.");
      resetForm();
      await refreshStores(false);
      await loadStoreFiles(editingId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update vector store.");
    } finally {
      setBusyKey(null);
    }
  };

  const startEdit = (store: DataItem) => {
    setEditingId(toLabel(store.id));
    setName(toLabel(store.name) === "n/a" ? "" : toLabel(store.name));
    const metadata = store.metadata;
    setMetadataText(metadata && typeof metadata === "object" ? JSON.stringify(metadata, null, 2) : "");
    setError(null);
    setSuccess(null);
  };

  const handleDeleteStore = async (storeId: string) => {
    if (!window.confirm("Delete this vector store?")) return;
    setBusyKey(`delete-${storeId}`);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`/api/fuelix/vector-stores/${storeId}`, { method: "DELETE" });
      setSuccess("Vector store deleted.");
      setStoreFiles((prev) => {
        const next = { ...prev };
        delete next[storeId];
        return next;
      });
      if (editingId === storeId) resetForm();
      await refreshStores(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete vector store.");
    } finally {
      setBusyKey(null);
    }
  };

  const handleUploadToStore = async (storeId: string) => {
    const files = selectedFiles[storeId] ?? [];
    if (files.length === 0) {
      setError("Choose one or more local files first.");
      return;
    }

    setBusyKey(`upload-${storeId}`);
    setError(null);
    setSuccess(null);
    try {
      let uploadedCount = 0;
      const failedNames: string[] = [];

      for (const file of files) {
        const formData = new FormData();
        formData.set("file", file);
        formData.set("purpose", "assistants");

        try {
          await apiFetch(`/api/fuelix/vector-stores/${storeId}/upload-file`, {
            method: "POST",
            body: formData,
          });
          uploadedCount += 1;
        } catch {
          failedNames.push(file.name);
        }
      }

      if (failedNames.length > 0) {
        const preview = failedNames.slice(0, 3).join(", ");
        setSuccess(
          `${uploadedCount} uploaded, ${failedNames.length} failed.${preview ? ` Failed: ${preview}` : ""}`,
        );
      } else {
        setSuccess(`${uploadedCount} file(s) uploaded and attached to vector store.`);
      }

      setSelectedFiles((prev) => ({ ...prev, [storeId]: [] }));
      await loadStoreFiles(storeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload files to vector store.");
    } finally {
      setBusyKey(null);
    }
  };

  const handleRemoveStoreFile = async (storeId: string, fileId: string) => {
    if (!window.confirm("Remove this file from the vector store?")) return;
    setBusyKey(`remove-file-${storeId}-${fileId}`);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`/api/fuelix/vector-stores/${storeId}/files/${fileId}`, { method: "DELETE" });
      setSuccess("File removed from vector store.");
      await loadStoreFiles(storeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove vector store file.");
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
              <h1 className="text-2xl font-bold text-gray-900">Vector Stores</h1>
              <p className="text-sm text-gray-600">Create, edit, delete, and upload local files directly to stores.</p>
            </div>
            <button
              onClick={() => void refreshStores(true)}
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
              {editingId ? "Edit Vector Store" : "Create Vector Store"}
            </h2>
            <form
              onSubmit={editingId ? handleUpdate : handleCreate}
              className="mt-4 space-y-2"
            >
              <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <textarea value={metadataText} onChange={(e) => setMetadataText(e.target.value)} placeholder='Metadata JSON (optional)' className="h-24 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <div className="flex items-center gap-2 pt-1">
                <button
                  disabled={Boolean(busyKey)}
                  className="rounded-lg bg-[#00417d] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {busyKey?.startsWith("update-")
                    ? "Updating..."
                    : busyKey === "create-store"
                    ? "Creating..."
                    : editingId
                    ? "Update vector store"
                    : "Create vector store"}
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
          </section>

          <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Existing Vector Stores</h2>
            {isLoading ? (
              <div className="mt-4 text-center text-gray-500">
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-[#00417d]" />
              </div>
            ) : vectorStores.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500">No vector stores found.</p>
            ) : (
              <div className="mt-4 space-y-3">
                {vectorStores.map((store, index) => {
                  const storeId = toLabel(store.id);
                  const files = storeFiles[storeId] ?? [];
                  return (
                    <article key={`${storeId}-${index}`} className="rounded-lg border border-gray-200 p-3 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-gray-900">{toLabel(store.name)}</p>
                          <p className="truncate text-xs text-gray-500">{storeId}</p>
                          <p className="mt-1 text-xs text-gray-600">Created: {toDate(store.created_at)}</p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => startEdit(store)}
                            className="inline-flex items-center gap-1 rounded-md border border-blue-200 px-2 py-1 text-xs text-blue-700 hover:bg-blue-50"
                          >
                            <Pencil className="h-3 w-3" />
                            Edit
                          </button>
                          <button
                            onClick={() => void handleDeleteStore(storeId)}
                            disabled={busyKey === `delete-${storeId}`}
                            className="inline-flex items-center gap-1 rounded-md border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-60"
                          >
                            {busyKey === `delete-${storeId}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                            Delete
                          </button>
                        </div>
                      </div>

                      <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                        <p className="text-xs font-semibold text-gray-700">Upload files from local machine</p>
                        <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                          <input
                            type="file"
                            multiple
                            onChange={(e) =>
                              setSelectedFiles((prev) => ({
                                ...prev,
                                [storeId]: Array.from(e.target.files ?? []),
                              }))
                            }
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs"
                          />
                          <button
                            onClick={() => void handleUploadToStore(storeId)}
                            disabled={busyKey === `upload-${storeId}`}
                            className="inline-flex items-center justify-center gap-1 rounded-lg bg-[#00417d] px-3 py-2 text-xs font-medium text-white hover:bg-[#002a52] disabled:opacity-60"
                          >
                            {busyKey === `upload-${storeId}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                            Upload selected
                          </button>
                        </div>
                        {(selectedFiles[storeId]?.length ?? 0) > 0 && (
                          <p className="mt-1 text-xs text-gray-600">
                            Selected: {selectedFiles[storeId].length} file(s)
                          </p>
                        )}
                      </div>

                      <div className="mt-3">
                        <button
                          onClick={() => void loadStoreFiles(storeId)}
                          disabled={busyKey === `files-${storeId}`}
                          className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                        >
                          {busyKey === `files-${storeId}` ? "Loading files..." : "Load attached files"}
                        </button>
                        {files.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {files.map((fileItem, i) => {
                              const fileId = toLabel(fileItem.id);
                              const filename = asNonEmptyString(fileItem.filename);
                              const externalFileId = asNonEmptyString(fileItem.externalFileId);
                              const displayName = filename ?? externalFileId ?? fileId;
                              return (
                                <div key={`${fileId}-${i}`} className="flex items-center justify-between rounded border border-gray-200 bg-white px-2 py-1 text-xs">
                                  <div className="min-w-0">
                                    <p className="truncate font-medium text-gray-700">
                                      {displayName}
                                    </p>
                                    {filename && (
                                      <p className="truncate text-gray-500">{fileId}</p>
                                    )}
                                    <p className="truncate text-gray-500">Status: {toLabel(fileItem.status)}</p>
                                  </div>
                                  <button
                                    onClick={() => void handleRemoveStoreFile(storeId, fileId)}
                                    disabled={busyKey === `remove-file-${storeId}-${fileId}`}
                                    className="rounded border border-red-200 px-2 py-1 text-red-700 hover:bg-red-50 disabled:opacity-60"
                                  >
                                    {busyKey === `remove-file-${storeId}-${fileId}` ? "..." : "Remove"}
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
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
