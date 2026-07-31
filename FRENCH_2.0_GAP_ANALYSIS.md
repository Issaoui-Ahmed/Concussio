# ConcussCare 2.0 — Bilingual (FR/EN) Gap Analysis

Response to Jenny's feedback email. Each of the client's 13 points is assessed against the
current codebase with file/line evidence.

**Summary:** the *generation* layer is already bilingual (the model answers in the user's
language with canonical French headings). Almost everything else — the interface, the
disclaimer, the logo, the resource links, and the language-switching behaviour — is not.

| # | Client request | Status |
|---|---|---|
| 1 | Complete bilingual interface | ❌ Missing |
| 2 | French disclaimer | ❌ Missing |
| 3 | Choose language before accepting disclaimer | ❌ Missing |
| 4 | FR disclaimer → FR interface | ❌ Missing |
| 5 | FR/EN toggle throughout the session | ⚠️ Partial |
| 6 | Translate all interface elements | ❌ Missing |
| 7 | Standardize French subheadings | ⚠️ Partial |
| 8 | French logo | ❌ Missing (asset not in repo) |
| 10 | Respond in the user's language | ✅ Exists (generation) / ⚠️ display can override |
| 11 | Auto-switch when the user changes language | ⚠️ Broken at display layer |
| 12 | Link French resources by default | ❌ Missing |
| 13 | English resources only when no FR equivalent | ❌ Missing |

*(Point 9 "Language behaviour" is a section header for 10–11.)*

---

## What already exists

**1. Model answers in the user's language.**
`core/prompts.py:68-79` has an explicit LANGUAGE block: detect EN or FR from the question,
write the *entire* response in that language — headings, body, safeguard message, and the
two fixed fallback messages (both have French wording supplied). These instructions are
pushed to the Fuel IX assistants via `api/update_fuelix_instructions.py`.

**2. Canonical French section headings are defined.**
`core/prompts.py:88-91` specifies the French headings:
`**Résumé :**`, `**Recommandations des lignes directrices évolutives :**`,
`**Informations tirées de la littérature :**`.

**3. A translation service exists.**
`core/translator.py` + `api/translate.py` expose `POST /api/translate`, which translates a
batch of strings between EN and FR via Fuel IX (`gpt-5.2`), auto-detecting the source
language when no target is given. It preserves Markdown structure and leaves URLs untouched.

**4. A per-conversation EN/FR toggle exists in the chat.**
`components/ChatInterface.tsx:456-477`. Every message is eagerly translated into the other
language and both versions are cached on the message (`translations`,
`followUpTranslations`), so toggling is instant. `ensureSessionTranslated()` backfills
anything missing. `Session.displayLang` (`components/Sidebar.tsx:18`) persists the choice
per chat in localStorage.

**5. Follow-up prompts are translated too.**
`translateMessageFollowUps()` (`ChatInterface.tsx:224`) caches both languages, and
`ChatMessage.tsx:80` renders the version matching `displayLang`.

---

## Gaps, point by point

### 1 + 6 — Complete bilingual interface / translate all interface elements ❌

There is **no i18n infrastructure at all**: no `next-intl`/`react-i18next` in
`package.json`, no locale files, no locale routing, no app-level language state. Every
user-facing string is hardcoded English in JSX. `app/layout.tsx:28` is hardcoded
`<html lang="en">`.

Complete inventory of strings that must be translated:

| File | Strings |
|---|---|
| `app/layout.tsx:17-20,28` | page `<title>`, meta description, `lang` attribute |
| `components/Navbar.tsx:20-23` | "Chatbot", "About us", "Source of information" |
| `components/Sidebar.tsx:42,53,58` | "New chat", "Your conversations", "No conversations yet." |
| `components/ChatInterface.tsx:459` | "Language" label |
| `components/ChatInterface.tsx:494-495` | "ConcussCare" + welcome tagline |
| `components/ChatInterface.tsx:523` | "Thinking… {n}s" |
| `components/ChatInterface.tsx:546-550` | all 5 user-type options (Healthcare Professional, Parent or Caregiver, Youth, Teacher, Coach) |
| `components/ChatInterface.tsx:559` | input placeholder `Message as {userType}...` |
| `components/ChatMessage.tsx:118` | **"You"** (the label Jenny explicitly called out) and "ConcussCare" |
| `components/ChatMessage.tsx:121` | "Translating…" |
| `components/ChatMessage.tsx:127` | "Ask a follow up" |
| `components/DisclaimerModal.tsx:18-56` | entire disclaimer + "I Understand" |
| `app/about/page.tsx` | whole page |
| `app/sources/page.tsx` | whole page |
| `components/ChatInterface.tsx:28-32` | `DEFAULT_FOLLOW_UPS` — English strings used to pad the follow-up list to 3, **even in a French conversation** |
| `core/generator.py:19-23` | `FALLBACK_FOLLOW_UPS` — English strings returned when follow-up generation fails |

Note the user-type dropdown is doubly coupled: the same string is both the UI label and the
routing key into `ASSISTANT_ENV_BY_USER_TYPE` (`core/fuelix_chat.py:48-55`) and the
personalization branches in `core/prompts.py:20-63`. Translating the label naively would
break assistant selection — the value must stay a stable English key with a separate
display label.

### 2 — French disclaimer ❌

`components/DisclaimerModal.tsx` is a single hardcoded English block (5 paragraphs). No
French copy exists anywhere in the repo. **We need the client's approved French disclaimer
text** — this should not be machine-translated, since it is a legal/medical notice.

Two additional defects in the same component:
- Acceptance is **not persisted** (`useState(true)`, line 6) — the modal reappears on every
  full page load. Points 3 and 4 require remembering the choice, so this must be fixed.
- Stray trailing `"` in the last paragraph (line 47).
- It is mounted in `app/layout.tsx:34`, so it also appears on `/admin` routes.

### 3 + 4 — Language choice at the disclaimer, and it carries into the interface ❌

Neither exists. The disclaimer has no language control, and there is nowhere for its choice
to go: **language state today lives only on individual chat sessions**
(`Session.displayLang`), created after the first message. There is no application-level
locale.

Required: a global locale provider (React Context + a `localStorage` key such as
`concussio_lang`) that the disclaimer sets, the navbar toggle mutates, and every component
reads. This is the single largest architectural piece of 2.0 and blocks 1, 3, 4, 5, and 6.

### 5 — FR/EN toggle throughout the session ⚠️ Partial

The existing toggle falls short in four ways:

1. **It only appears once a chat has messages** — `messages.length > 0`
   (`ChatInterface.tsx:457`). On the landing screen and after "New chat" there is no toggle.
2. **It only translates chat content**, not a single element of the interface chrome.
3. **It is scoped to one conversation.** Starting a new chat resets to English
   (`displayLang: Lang = currentSession?.displayLang ?? "en"`, line 106).
4. **It doesn't exist outside the chat** — About and Sources pages have no toggle.

Jenny asks for it "throughout the session," which means it belongs in the navbar as a global
control.

### 7 — Standardize French subheadings ⚠️ Partial

The canonical headings *are* specified in `core/prompts.py:88-91`, so a natively-French
answer is usually correct. The drift Jenny observed
("recommandations des **Living Guidelines**") has two likely sources, and both need fixing:

- **The translator has no glossary.** `core/translator.py:35-48` instructs the model to
  "Keep proper nouns, author names, in-text citation keys … and tool names unchanged." A
  translating model can reasonably read "Living Guideline" as a proper noun and leave it in
  English. Any English answer viewed through the FR toggle goes through this path.
- **No post-processing.** Nothing normalizes headings after generation or translation.

Fix: add an explicit FR/EN term glossary to the translator system prompt (Living Guideline →
lignes directrices évolutives, plus tool names), and add a deterministic heading-normalization
pass applied to both generated and translated French text.

### 8 — French logo ❌

The attached French logo **is not in the repository** — `public/` contains only `logo.png`
and `logo-icon-v2.png`. We need the asset file from the client. The logo is referenced in
three places, all hardcoded:
`components/Navbar.tsx:31` (`/logo.png`), `components/ChatInterface.tsx:488` and
`components/ChatMessage.tsx:107` (`/logo-icon-v2.png`).

### 10 — Respond in the language the user is using ✅ generation / ⚠️ display

Generation is correct (see "What already exists" #1). The problem is the **display layer can
override it**: the rendered text is `translations?.[displayLang] ?? content`
(`ChatMessage.tsx:78`). If `displayLang` is `"en"` and the user writes in French, the model
answers in French and the UI then shows the *English translation* of that answer.

### 11 — Automatically switch languages mid-conversation ⚠️ Broken

**This is a concrete bug.** `ChatInterface.tsx:220`:

```ts
setSessions(prev => prev.map(s => (s.id === sessionId && !s.displayLang ? { ...s, displayLang: src } : s)));
```

The `!s.displayLang` guard means the display language is locked to whatever was detected on
the **first** message. A user who starts in English and switches to French mid-chat keeps
seeing English. The detected source language of each new message needs to update
`displayLang` (with the caveat that an *explicit* manual toggle should probably win over
auto-detection until the user switches input language again — worth confirming with the
client which takes precedence).

On the backend side, auto-switching works by default because Fuel IX calls are stateless:
`generate_fuelix_answer()` (`core/fuelix_chat.py:294-340`) opens a **new thread per message**
and `api/chat.py:150-165` never forwards `history` in fuelix mode. Each message's language is
therefore detected independently. (Separately: this also means the bot has **no conversational
memory** in the mode the app actually uses — `provider_mode: "fuelix"` is hardcoded at
`ChatInterface.tsx:380`. Worth flagging to the client as its own issue.)

### 12 + 13 — Link French resources by default, English only as fallback ❌

Nothing in the system is aware that French resources exist. Evidence:

- `all_rec_markdown.md` — the guideline corpus injected into every prompt
  (`core/prompts.py:99`) — contains **312 `pedsconcussion.com` URLs, all English**. Zero
  French URLs anywhere in the repo (`ressources`, `/fr/` return no matches).
- `core/prompts.py:96` instructs: "Everytime a tool is mentioned, include its link right
  after the mention" — so it emits whatever English URL it has.
- `core/translator.py:41` explicitly instructs "Keep links and URLs unchanged," so even a
  fully French answer keeps English links.
- The Fuel IX vector stores ("Living guideline tools", "Key papers to include") are the
  English document sets.

The French site does not use a mechanical URL pattern we could derive — it mixes
`/fr/<page>/` with fully French slugs. Confirmed examples from
<https://pedsconcussion.com/ressources/>:

| English | French |
|---|---|
| `/tool-2-6-post-concussion-information-sheet/` | `/fiche-dinformation-post-commotion/` |
| `/return-to-activity-sport-school/` | `/retour-aux-activites-sport-lecole/` |
| `/crt6/` | `/reconnaissance/` |
| (parent guide) | `/fr/parents/` |
| (coach guide) | `/fr/entraineur/` |
| (teacher guide) | `/fr/enseignants/` |
| Tool 6.1 headache algorithm | `/outil-6-1-algorithme-de-gestion-des-maux-de-tete-post-commotions-cerebrales/` |

Required: an explicit **EN→FR URL mapping table** built from the client's resource list,
applied as a post-processing substitution on French answers, plus a prompt rule stating that
when no French equivalent exists the English link is used (ideally marked as such, e.g.
"(en anglais)"). A mapping table is the only reliable approach — the model must not be
allowed to guess French URLs, or it will hallucinate dead links.

---

## Additional issues found (not in the email, worth raising)

1. **Disclaimer acceptance is not persisted** — reappears on every page load
   (`DisclaimerModal.tsx:6`). Blocks points 3–4.
2. **Every message is translated twice** — each turn fires an extra LLM call to pre-translate
   into the other language (`translateMessageContent`, `ChatInterface.tsx:204`). Doubles cost
   and latency. With a proper locale system, translation is only needed when the user actually
   toggles.
3. **No conversation history in the live provider** (see §11) — the chatbot cannot handle
   "what about for a 10-year-old?" style follow-ups.
4. **Follow-up generation has no language instruction** —
   `core/generator.py:118-133` builds an English prompt; French output is incidental, not
   guaranteed. Fallbacks are hardcoded English.
5. **French typography** — `_clean_follow_up` (`core/generator.py:54-60`) appends `?` with no
   preceding space; French convention is a narrow no-break space before `?` and `:`.
6. **Admin tooling is English-only** (`AdminCompareChatInterface.tsx`, `BatchInterface.tsx`) —
   presumably out of scope, but confirm with the client.

---

## Suggested build order

1. **Locale foundation** (blocks almost everything): `LanguageProvider` context +
   `localStorage`, a `t()` helper and `locales/en.json` + `locales/fr.json`, dynamic
   `<html lang>`. *(Large)*
2. **Bilingual disclaimer with language selection** — EN shown first with a "Français"
   option; choosing FR swaps the text and sets the app locale; persist acceptance. *(Medium —
   needs the client's approved French copy)*
3. **Global FR/EN toggle in the navbar**, always visible, driving both the interface and the
   chat `displayLang`. *(Medium)*
4. **Translate all interface strings** into the locale files, keeping user-type values as
   stable English keys. *(Medium)*
5. **Fix auto-switching** — remove the `!s.displayLang` lock so a mid-conversation language
   change is followed. *(Small)*
6. **Heading standardization** — translator glossary + deterministic normalization pass.
   *(Small)*
7. **French resource mapping** — EN→FR URL table + substitution + "English fallback only"
   prompt rule. *(Medium — needs the client's full resource list)*
8. **French logo** — swap by locale in the three reference sites. *(Small — needs the asset)*

## Blockers — what we need from the client

- The **approved French disclaimer text** (should not be machine-translated).
- The **French logo file** (referenced as "attached" in the email but not in the repo).
- The **full EN→FR resource mapping**, or confirmation that we should build it ourselves
  from <https://pedsconcussion.com/ressources/> for their review.
- A decision on **manual toggle vs. auto-detect precedence**: if a user manually selects
  English and then types in French, which wins?
- Confirmation on whether the **About / Sources / admin pages** are in scope.
