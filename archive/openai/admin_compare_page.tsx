// ARCHIVED 2026-07-31 — was app/admin/page.tsx.
//
// Mounted the OpenAI-vs-Fuel IX compare chat at /admin. Retired when the app moved to Fuel IX
// only; /admin now redirects to /admin/batch. The import below points at the sibling archived
// file so this stays coherent — it is not built or routed. See ../README.md.

import { AdminCompareChatInterface } from "./AdminCompareChatInterface";

export default function AdminHome() {
  return (
    <main className="h-full">
      <AdminCompareChatInterface />
    </main>
  );
}
