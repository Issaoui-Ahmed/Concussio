# Archive

Retired code, kept readable on disk for reference. **Nothing here is imported, built, routed,
or deployed** — `archive/` is excluded from `tsconfig.json` and from ESLint, and Next.js only
routes files under `app/`, so the `.tsx` files here cannot become pages.

Treat these files as frozen. If something in here turns out to be needed again, move it back
into the live tree rather than importing across the boundary.

## `openai/` — retired 2026-07-31

The app now runs entirely on Fuel IX. These files were the last code that called
`api.openai.com` directly and the UI built to A/B the two providers against each other.

| File | Was | Why it went |
|---|---|---|
| `generator_openai.py` | `generate_answer()` from `core/generator.py` | OpenAI Responses API (`gpt-5.4`) with `file_search` over two OpenAI-hosted vector stores. The corpus lives in Fuel IX vector stores now. |
| `chat_openai_compare.py` | The OpenAI + compare plumbing from `api/chat.py` | Built the OpenAI prompt and fanned a query out to both providers so their answers and latency could be compared side by side. |
| `AdminCompareChatInterface.tsx` | `components/AdminCompareChatInterface.tsx` | The side-by-side compare chat with the OpenAI / Fuel IX / Both selector and per-provider live timers. |
| `admin_compare_page.tsx` | `app/admin/page.tsx` | Mounted the compare interface at `/admin`. That route now redirects to `/admin/batch`. |

### What was deleted outright rather than archived

- `core/domain_classifier.py` and `core/retriever.py` — a Supabase domain-retrieval path with
  an OpenAI classifier. Already broken before this cleanup: `domain_classifier.py` imported
  `build_domain_classifier_prompt` from `core/prompts.py`, which does not exist, so importing
  either module raised `ImportError`. Nothing referenced them.
- `api/migrate_openai_vector_stores_to_fuelix.py` — the one-off OpenAI → Fuel IX vector store
  migration. Already executed; its run reports (`api/openai_to_fuelix_vector_store_migration_*.json`)
  are gitignored local artifacts.

All three remain in git history if they are ever needed.

### Not OpenAI, despite the name

Model ids like `gpt-5.2` and `gpt-4.1-mini` still appear throughout `core/` and `api/`. Those
are OpenAI-*branded* models served through Fuel IX's OpenAI-compatible API — they are Fuel IX
calls and were deliberately left alone.
