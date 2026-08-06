# ConcussCare 2.0 — Bilingual Rework: Implementation Plan

The agreed design and build order. Supersedes the earlier `FRENCH_2.0_GAP_ANALYSIS.md`, which
described the pre-rework state and has been deleted now that it no longer matches the code —
recover it from git history if the original 13-point request needs citing.

> **Status: phases 0–5 implemented and verified.** Deterministic heading normalization and
> drift logging were deliberately skipped (see end of Phase 0). Remaining blockers are the
> French logo asset and client sign-off on the French disclaimer copy in Appendix A.
> Outstanding items are listed in §4.

---

## 1. Product behaviour (agreed)

| Concern | Decision |
|---|---|
| Language control | A single **global** EN/FR toggle. One locale for the entire app. |
| Scope | Everything outside `/admin`: navbar, sidebar, chat chrome, disclaimer, About, Sources. |
| Admin | **Untouched.** English only, no provider, no toggle. |
| Startup | App and disclaimer always open in **English**. |
| Disclaimer | Shown once per browser session, has its own EN/FR toggle. The language it is accepted in becomes the app locale. |
| Existing chat | Switching the locale re-renders **assistant answers and follow-up prompts** in the new language. |
| User messages | **Never translated.** Always shown verbatim as typed. |
| Session titles | **Never translated.** Unchanged behaviour (truncated first user message). |
| Auto-detect | The detected language of each user question **flips the global toggle**, which switches the whole app. |
| Manual toggle | Also sets the global locale. Effective until the next confidently-detected message. |

### Precedence rule (the one thing that could surprise a user)

> The locale is set by whichever happened most recently: a manual toggle, or a **confidently**
> detected user message. Ambiguous or very short input (`ok`, `merci`, `thanks`, `?`) never
> changes the locale.

Confidence gating is not optional. Without it, short chit-chat causes locale churn and silently
overrides a toggle the user just set.

---

## 2. Architecture

### 2.1 The core change: un-fuse three concepts

Today `Session.displayLang` conflates three separate things. Splitting them is what makes most
of this plan fall out for free:

| Concept | Home after the rework | Cost |
|---|---|---|
| **UI locale** | `LanguageProvider` context (global) | Free — dictionary lookup |
| **Message source language** | `Message.lang`, set at creation, immutable | Free — known, never detected after the fact |
| **Display language** | *Derived from the app locale.* Not stored. | LLM call only on cache miss |

`Session.displayLang` is **deleted**.

### 2.2 Locale transport: React Context, not locale routing

Rejecting `next-intl` / `app/[locale]/` deliberately. Locale routing earns its keep with SSR and
shareable localized URLs; this app is a client-rendered chat whose state lives in `localStorage`
and whose content comes from an LLM. Routing would mean restructuring the route tree, carving out
an admin exception, and forcing a **full navigation on every toggle — losing chat scroll position
and in-flight requests**. Context gives an instant, state-preserving switch.

Hand-rolled, no dependency, but **typed**: `en.ts` is the source of truth for the key union and
`fr.ts` is declared `Record<keyof typeof en, string>`, so a missing French string is a compile
error rather than a silent fallback to the key name.

### 2.3 Admin isolation via route groups

`ChatMessage` is shared with `AdminCompareChatInterface.tsx:419` and `BatchInterface.tsx:328`, so
the moment it calls `useT()` admin inherits localization unless this is handled structurally.

```
app/layout.tsx              → <html>, <body>, fonts, globals.css ONLY
app/(public)/layout.tsx     → LanguageProvider + Navbar(public) + DisclaimerModal
app/(public)/page.tsx  about/  sources/
app/admin/layout.tsx        → Navbar(admin). No provider.
```

`useT()` falls back to the English dictionary when no provider sits above it. Admin is then
English **by construction**, not by a conditional someone has to remember. This also fixes the
existing bug where the disclaimer pops up on `/admin` (it is currently mounted in the root layout
at `app/layout.tsx:34`).

### 2.4 Cost model

| | Today | After |
|---|---|---|
| Per turn | **4 LLM calls** — chat + translate(user msg) + followups + translate(followups) | **2** — chat + followups |
| Toggle, 10-msg chat | up to 20 sequential HTTP calls | **1 batched call** |

Two things produce the saving: user messages are never translated, and follow-ups are generated
directly in the locale instead of being generated then translated. Translation now happens *only*
on a locale change, only for assistant content, and only on cache miss.

---

## 3. Build phases

Phase 0 is independent and shippable today. Phases 1–5 are sequential.

### Phase 0 — Heading consistency + backend language plumbing

*Fixes the `Recommandations des Living Guidelines` drift. No UI change.*

**0a. Prompt fix — `core/prompts.py`**

`core/prompts.py:88-91` currently puts the French headings in **parentheses, as a gloss**:

```
**Living Guidelines Recommendations:** (French: **Recommandations des lignes directrices évolutives :**)
```

A model reads a parenthetical as explanatory context, not a mandate — and since every other
instruction says to preserve proper nouns, "Living Guideline" is treated as a brand name.

Restructure into two mutually exclusive templates (EN block / FR block), each with a
verbatim-copy instruction — *"emit this exact string, character for character; do not translate,
adapt, abbreviate, or re-order it"* — plus an explicit negation of the observed failure:
**never write "Living Guideline" or "Living Guidelines" inside a French heading.**

Canonical strings:

| Section | English | French |
|---|---|---|
| 1 | `**Summary:**` | `**Résumé :**` |
| 2 | `**Living Guidelines Recommendations:**` | `**Recommandations des lignes directrices évolutives :**` |
| 3 | `**Information From the Literature:**` | `**Informations tirées de la littérature :**` |

**0b. Translator glossary — `core/translator.py`**

`core/translator.py:41-42` currently instructs *"Keep proper nouns, author names, in-text citation
keys … and tool names unchanged."* This is not drift — the translator is **complying** with an
instruction that tells it to leave "Living Guidelines" in English.

Add a bidirectional glossary (the three headings above, plus Living Guideline → lignes directrices
évolutives, plus any tool names with official French equivalents) and state precedence explicitly:
**the glossary overrides the preserve-proper-nouns rule.**

**0c. `lang` parameter through the API**

- `core/prompts.py` — `build_generator_prompt(query, user_type, lang)` and
  `build_fuelix_assistant_instructions(user_type)`: replace the "detect the language" block
  (`prompts.py:68-79`) with "write your complete response in `{lang}`". Generation becomes
  deterministic instead of the model re-detecting independently of the UI.
- `api/chat.py` — add `lang: Optional[Literal["en","fr"]]` to `ChatRequest`, thread to the prompt.
- `api/followups.py` + `core/generator.py` — same. `generate_follow_ups` currently has **no
  language instruction at all** (`generator.py:122-137`); French output there is incidental.
  Localize `FALLBACK_FOLLOW_UPS` (`generator.py:19-23`).

**0d. Push to Fuel IX** ⚠️

The assistant instructions live on the **remote Fuel IX assistant objects**, not in the repo.
Editing `prompts.py` changes nothing in production until pushed:

```
python api/update_fuelix_instructions.py            # dry run (default)
python api/update_fuelix_instructions.py --execute  # patches 6 assistants
```

The script patches the `instructions` field only — model, vector stores (`tool_resources`), and
metadata are untouched. It affects all six assistants in `ASSISTANT_SPECS`
(`api/rebuild_fuelix_assistants.py:29-37`). **This mutates live remote state — I will run the dry
run, show you the diff, and confirm before running `--execute`.**

*Explicitly out of scope, per your call:* deterministic heading normalization and drift logging.
If drift survives 0a+0b, that is the next lever — a `normalize_headings(text, lang)` pass anchored
to heading positions, called from both `fuelix_chat.py:331` and the return of `translate_texts`.

---

### Phase 1 — i18n foundation + admin isolation

**New**
- `lib/i18n/en.ts` — dictionary; source of truth for the key union.
- `lib/i18n/fr.ts` — `Record<keyof typeof en, string>`.
- `lib/i18n/LanguageProvider.tsx` — context, `useLocale()`, `useT()` with interpolation
  (needed for `Message as {userType}...` and `Thinking… {n}s`). EN fallback when no provider.
- `lib/i18n/detect.ts` — client-side EN/FR detector returning `{lang, confident}`. Diacritic
  density + stopword frequency, ~30 lines, **no LLM call**.

**Restructure** — route groups per §2.3. `app/batch/` is an empty directory; delete it.

**Locale persistence** — `sessionStorage`, not `localStorage`. Because the disclaimer reappears
each browser session and always opens in English, a locale persisted across sessions would
contradict its own default.

**`<html lang>`** — no cookie, no SSR hydration work needed: the app always boots English, so
SSR-rendering `lang="en"` is correct *by definition*. A client effect updates
`document.documentElement.lang` on toggle.

### Phase 2 — Extract strings to the dictionaries

Mechanical; the type checker enforces completeness. Full inventory:

| File | Strings |
|---|---|
| `components/Navbar.tsx:20-23` | Chatbot, About us, Source of information |
| `components/Navbar.tsx:31` | logo asset path (EN/FR variants) |
| `components/Sidebar.tsx:42,53,58` | New chat, Your conversations, No conversations yet. |
| `components/ChatInterface.tsx:494-495` | ConcussCare + welcome tagline |
| `components/ChatInterface.tsx:523` | Thinking… {n}s |
| `components/ChatInterface.tsx:546-550` | 5 user-type **labels** |
| `components/ChatInterface.tsx:559` | Message as {userType}… |
| `components/ChatInterface.tsx:417` | "Sorry, error occurred." |
| `components/ChatInterface.tsx:28-32` | `DEFAULT_FOLLOW_UPS` — pads to 3 with English **even in a French chat** |
| `components/ChatMessage.tsx:118,121,127` | You, ConcussCare, Translating…, Ask a follow up |
| `app/(public)/about/page.tsx` | whole page |
| `app/(public)/sources/page.tsx` | whole page |

⚠️ **User-type values are load-bearing.** `<option value="Healthcare Professional">`
(`ChatInterface.tsx:546`) is simultaneously the display label *and* the routing key into
`ASSISTANT_ENV_BY_USER_TYPE` (`core/fuelix_chat.py:48-55`) and the prompt branches
(`core/prompts.py:20-63`). **Keep the English string as the wire value; translate only the label.**
Zero backend change.

### Phase 3 — Disclaimer

Rewrite `components/DisclaimerModal.tsx`:
- EN/FR toggle in the header; body from the dictionaries.
- Opens in English every time; accepting commits the locale to the provider.
- `sessionStorage` gate replaces `useState(true)` (`DisclaimerModal.tsx:6`), which currently
  re-shows the modal on every page load.
- Fix the stray `"` at `DisclaimerModal.tsx:47`.

French copy in Appendix A. ⚠️ **This is my translation of a medical/legal notice — get client
sign-off before production.**

### Phase 4 — Global toggle, `displayLang` removal, resolver fix

- New `components/LanguageToggle.tsx`, mounted in the **public** navbar only. Always visible —
  the current one only appears once a chat has messages (`ChatInterface.tsx:457`).
- Delete `Session.displayLang` (`Sidebar.tsx:18`) and every read/write:
  `ChatInterface.tsx:106`, `:220`, `:282`, `:467`, `:504`.
- Remove the `displayLang` prop from `ChatMessage`; it reads the locale from context.
- **Resolver fix** — `ChatMessage.tsx:78` currently does `translations?.[displayLang] ?? content`,
  which can show a *round-trip translation* of text already in the right language. Replace with
  `msg.lang === locale ? msg.content : msg.translations?.[locale] ?? msg.content`.
- **Migration** — bump to `concussio_sessions_v2`. Keep `messages` and their `translations` cache
  (still valid); drop `displayLang`.

### Phase 5 — Lazy batched translation + auto-detect

**Translation**
- Delete eager translation of user messages entirely (`translateMessageContent` at
  `ChatInterface.tsx:204`, called at `:362`).
- Delete eager translation of follow-ups (`translateMessageFollowUps`, `:224`) — they are now
  generated in the locale by Phase 0c.
- Rewrite `ensureSessionTranslated` (`:236`), which today reads `sessions` from a **stale closure**
  and fires N parallel `patchMessage` calls:
  - **Batch** — `/api/translate` already accepts an array. One request for the whole session,
    chunked by ~12k characters with index mapping preserved. `translate_texts` already raises on
    a length mismatch (`translator.py:107`).
  - **Dedupe** — in-flight map keyed `${messageId}:${lang}`.
  - **Guard stale results** — discard any response whose target ≠ the locale at resolution time.
    Toggling EN→FR→EN quickly currently interleaves writes.

**Auto-detect**
- Run `detect()` on submit, **before** the request fires. If confident and different from the
  current locale, set the locale immediately — so the chrome and `Thinking… {n}s` are already
  correct while the answer generates. Detecting from the response instead would flip the UI
  *after* the answer lands.
- A locale flip from auto-detect triggers the **same** backfill path as a manual toggle. One code
  path.
- Send the resolved `lang` with the `/api/chat` and `/api/followups` requests, and stamp it on the
  assistant message as `Message.lang` — no post-hoc detection needed.

---

### Phase 6 — French resource links (client points 12–13)

*Prerequisite, done first: the corpus URLs were stale. See `CORPUS_LINK_AUDIT.md` — 40% of the
141 unique URLs in `all_rec_markdown.md` did not resolve cleanly, and 79 occurrences were
repaired before any French pairing was attempted. Mapping to stale English URLs would have
baked the staleness in.*

**The rule: the model never produces a French URL.** It always emits the English one it has;
the *display* layer swaps it. Asking the model would mean hallucinated links — the French slugs
are long enough to mangle (`/outil-10-1-algorithme-de-gestion-des-troubles-de-la-vision-…`), and
a dead link in a clinical tool is worse than a working English one.

**Why the display layer, not generation.** One assistant message renders in EN or FR depending
on the locale (`ChatMessage.tsx:89-93`), and `core/translator.py:82` deliberately leaves URLs
untouched. Localizing at generation time would leave French links behind when a French answer is
toggled to English. Link language must follow the locale being *rendered*.

**New**
- `lib/i18n/resourceLinks.ts` — the EN→FR table plus `localizeLink()` / `normalizeUrl()`.
  25 English keys → 15 French resources. Keys are corpus URLs, with live-site aliases included
  because the RAG vector store may emit either form. Normalization absorbs the corpus's
  http/https, `www.`, and trailing-slash inconsistency.
- `components/ResourceLink.tsx` — the `a` renderer.

**Changed** — `ChatMessage.tsx` passes `components={{ a: ResourceLink }}` to `ReactMarkdown`.
Only the `href` and (where an official French title exists) the link text change; the answer
body is never string-substituted, so there is no way to corrupt generated prose.

**Behaviour**

| Locale | Mapped resource | Unmapped resource |
|---|---|---|
| EN | unchanged | unchanged |
| FR | French URL + official French title | English URL, marked `(en anglais)` |

An `ALREADY_FRENCH` set prevents the marker appearing on resources that are *already* French in
the corpus (the INESSS pamphlet, the Nunavut sheet) — otherwise a French document would be
labelled as English.

**Deliberately unmapped** (falls back to English rather than guess):
- Child SCOAT6 — `/scoat-enfant-fr/` returns 404; no French version exists.
- CATT return-to-sport — the French index labels "Retour au sport" but points it at the
  return-to-*activity* file, so there is no unambiguous French document.
- 5P Score Calculator — `/fr/scorecalculator` soft-404s to the site root.

**Verification** — all 45 URLs in the table confirmed live; 18 behavioural tests on
`localizeLink()`; production build clean. ⚠️ *Not* verified in a running browser: the dev server
would not stay up in this environment.

**Admin is unaffected** by construction — `app/admin/` mounts no `LanguageProvider`, so
`useLocale()` returns `"en"` and `localizeLink` is a no-op there (§2.3).

---

## 4. Out of scope (flagged, not planned)

- **French logo asset.** `fr.ts` points `nav.logo` at `/logo-fr.png`; drop the client's French
  mark at `public/logo-fr.png` and it is picked up with no code change. Match the English
  mark's proportions (`logo.png` is 392×104, ~3.8:1); the navbar box is `w-48 h-12` with
  `object-contain`, so exact pixel dimensions do not matter. **Until that file exists the
  French navbar logo 404s.** No French variant of `logo-icon-v2.png` is needed — it is the
  wordless brain icon.
- ~~**French resource URLs** (client points 12–13).~~ **Implemented — see Phase 6 below.**
- **No conversational memory.** `provider_mode: "fuelix"` is hardcoded (`ChatInterface.tsx:380`);
  that path opens a new thread per message (`fuelix_chat.py:303`) and `api/chat.py:150-165` never
  forwards `history`. The bot cannot handle "what about for a 10-year-old?" follow-ups. Separate,
  larger issue.
- **French typography in follow-ups.** `_clean_follow_up` (`generator.py:59`) appends `?` with no
  preceding narrow no-break space.
- **Static metadata.** `<title>`/`description` (`app/layout.tsx:17-20`) stay English unless a
  `document.title` effect is added. Low value.

---

## Appendix A — French disclaimer copy (draft, needs client sign-off)

**Avis de non-responsabilité**

> Ce robot conversationnel s'appuie sur les lignes directrices évolutives sur les commotions
> cérébrales pédiatriques. Il vise à faciliter le partage d'information auprès des professionnels
> de la santé, des familles et des autres parties prenantes concernées par les commotions
> cérébrales pédiatriques. Il ne remplace pas un avis médical, un diagnostic ou un traitement. Il
> n'est pas destiné à l'autodiagnostic.

> **Si vous avez besoin de soins médicaux urgents, composez le 911 ou rendez-vous au service
> d'urgence le plus proche.**

> Les recommandations reflètent les meilleures données probantes disponibles au moment de leur
> élaboration. De nouvelles données peuvent les modifier. Les professionnels de la santé doivent
> exercer leur jugement clinique et tenir compte des préférences du patient ainsi que des
> ressources locales.

> L'équipe des lignes directrices évolutives sur les commotions cérébrales pédiatriques, les
> bailleurs de fonds, les collaborateurs et les partenaires ne peuvent être tenus responsables de
> tout préjudice ou de toute perte découlant de l'utilisation ou de la mauvaise utilisation de ce
> robot conversationnel.

> Toute adaptation doit comporter la mention : « Adapté des lignes directrices évolutives sur les
> commotions cérébrales pédiatriques », avec ou sans autorisation, selon le cas.

Button: **J'ai compris**

*Note: "robot conversationnel" is the OQLF-standard term, appropriate for a Canadian audience;
"agent conversationnel" is an acceptable alternative. The English source has a stray trailing
`"` in the final paragraph (`DisclaimerModal.tsx:47`) which is dropped here.*
