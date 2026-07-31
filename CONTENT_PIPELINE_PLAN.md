# Automated Bilingual Content Pipeline — Plan

**Goal:** fetch the recommendations *and* the resources, in English *and* French, pair them
automatically, push them into the system, and re-run when the source site changes.

---

## Build status (2026-07-29)

| Stage | Status |
|---|---|
| Fetch — EN tools + FR resources | ✅ built, live-tested (96 EN / 35 FR) |
| Pair — confidence-tiered matcher | ✅ built, cold-start validated |
| Render — `resourceLinks.data.ts` + manifest | ✅ built |
| Gates — fetch-sane, wellformed, blocked, in-sync, liveness | ✅ built, 4/4 green |
| CI — refresh + verify workflows | ✅ built, **never executed on GitHub** |
| Publish — assistant push | ✅ **executed and verified** on 2026-07-29 (6/6 assistants) |
| Publish — vector store sync | ⚠️ **written but UNVERIFIED against the live API** |
| Render — `all_rec_markdown.md` from the scraper | ✅ built, **switched over** |

### The corpus is now live-fetched

Earlier drafts of this plan treated `all_rec_markdown.md` as hand-curated and warned against
regenerating it. **That was wrong** — the file was originally copied from pedsconcussion.com,
so there was never any hand-authored content to lose. Corrected on 2026-07-29 and the
generator built.

The one real obstacle was technical, not editorial: `core.scraper` exposes
`recommendation_text` via `get_text()`, which flattens away every link, image and bold run.
The corpus depends on all three — the tool links are the entire point — so `corpus.py`
converts `recommendation_html` with `markdownify` instead.

**Coverage check before switching over** (generated vs. the committed copy):

| | committed | generated |
|---|---|---|
| Domains | 16 | **18** |
| Numbered recommendations | 112 | **112** (zero missing) |
| URLs | 136 | **146** |

The fresh scrape is a superset: same 112 recommendations, plus two domains and 2025 content
(CoCo detection tool, ACRM diagnostic criteria) that the copy predated.

### URLs are reproduced exactly as published

The corpus does **not** repair link rot. Earlier work fixed 79 stale URLs by hand, but the
site's own HTML still contains the old forms, so a fresh scrape reverts them — and rewriting
them here would mean the corpus no longer matches what pedsconcussion.com actually says.

Link rot in the source is the site owner's to fix. The liveness gate still *reports* dead
links so they can be raised with the client; see `CORPUS_LINK_AUDIT.md`.

### Corpus safety gate

`gate_corpus_sane` is the important one. `core/scraper.py:561` swallows a failed section
fetch into an empty dict, so a network blip or changed selector silently drops a whole
section rather than raising. The gate floors domains (≥12), numbered recommendations (≥90)
and size (≥100k chars), rejects any domain that renders empty, and fails on a >10% drop from
the last good run.

### Full automation (decided 2026-07-29)

The chain runs end to end with no human step: scrape → gates → commit → push to Fuel IX →
verify. The safety mechanism is the gate set, not a reviewer.

This is coherent with the decision that link rot is the site owner's problem: the corpus is a
*mirror*. If pedsconcussion.com publishes something wrong, the chatbot repeats it, and that is
upstream's to fix. What the gates protect against is *our* failure — a broken scrape
misrepresenting a site that is actually fine.

**Residual risk the gates do not cover:** a scraper bug that produces plausible-but-wrong
output (right size, right recommendation count, wrong attribution). The floors catch gross
collapse, not subtle misparsing.

#### The trap this design avoids

Publishing runs **inside** `content-refresh.yml`, not in a separate workflow triggered by the
commit. A commit pushed with the default `GITHUB_TOKEN` does **not** trigger other workflows —
GitHub blocks it to prevent recursion. A split refresh/publish pair would look correct, pass
review, and silently never publish. `content-publish.yml` still exists for human pushes and
manual re-publishing, where the trigger does fire.

#### Required repository secrets

The workflow cannot authenticate without these (values are in the local `.env`):

`FUELIX_API_KEY` · `FUELIX_ASSISTANT_ID_PATIENT` ·
`FUELIX_ASSISTANT_ID_HEALTHCARE_PROFESSIONAL` · `FUELIX_ASSISTANT_ID_PARENT_OR_CAREGIVER` ·
`FUELIX_ASSISTANT_ID_YOUTH` · `FUELIX_ASSISTANT_ID_TEACHER` · `FUELIX_ASSISTANT_ID_COACH`

#### Post-publish verification

`scripts/publish/verify_assistants.py` reads the instructions back off the remote and fails
the run if the corpus did not land. `update_fuelix_instructions.py` reports what it *sent*;
this reports what the assistants actually *have*. It refuses to pass when no assistant ids are
configured, rather than reporting a vacuous success over an empty loop.

---

## 1. The one place I'd push back

You asked for change → automatic background update. I'd build the whole pipeline automatically
and make the **final push a one-click approval**, for one reason:

The corpus is the knowledge base of a clinical decision-support tool. A site redesign that breaks
a CSS selector doesn't throw an error — it silently returns *empty sections*, and the pipeline
would faithfully publish a gutted guideline to all six assistants. This isn't hypothetical: the
existing scraper already carries a hand-written guard for exactly this
(`core/scraper.py:648` — *"extraction returned no links; kept previous cached list"*). Whoever
wrote that had already been bitten.

So: **detection, fetching, pairing and rendering are fully automatic and run unattended. The
merge is a human click.** Everything is prepared for you — you review a diff, not a blank page.

I do propose a **Tier A auto-merge** path (§7) for changes that provably can't alter clinical
meaning, so routine link maintenance needs no human at all.

---

## 2. Current state

| Piece | Exists? | Reality |
|---|---|---|
| `core/scraper.py` | ✅ | Scrapes EN domains + EN tools. Solid: retries, PDF resolution, caching. |
| `api/scraping.py` | ✅ | `/api/scraping` snapshot + tools-as-zip download. |
| `all_rec_markdown.md` | ⚠️ | **Hand-maintained. Nothing connects it to the scraper.** |
| Vector store sync | ❌ | Zip is downloaded and uploaded **by hand**. |
| `lib/i18n/resourceLinks.ts` | ⚠️ | **Hand-built snapshot** (2026-07-29). Static, will rot. |
| French scraping | ❌ | Does not exist. Scraper targets English URLs only. |
| Change detection | ❌ | `ScrapingCache` is **in-memory with a 60s TTL** — a per-request cache, not state. |
| CI | ❌ | No `.github/`. Remote is `github.com/Issaoui-Ahmed/Concussio`. |

**The core disconnect:** the scraper can already read the recommendations, but its output goes to
a *screen*, never to `all_rec_markdown.md`. That gap is the actual work.

---

## 3b. SUPERSEDED — the scheduler moved to Vercel (2026-07-29)

§3 below argued for GitHub Actions. **That decision was reversed**, for one reason §3 did not
account for: GitHub **disables scheduled workflows after 60 days of repository inactivity**
(confirmed in GitHub's docs). For a product handed to a client, that means the automation
silently stops two months after the repo goes quiet. Vercel crons never go dormant.

### What the Vercel design changes

A Vercel function **cannot write files** — serverless filesystems are read-only apart from an
ephemeral `/tmp`. So there is nowhere to commit `all_rec_markdown.md`, which rules out
git-as-change-detector.

**The remote assistants became the state store instead:**

```
scrape guideline -> build instructions in memory -> read what Fuel IX currently has
-> patch only the assistants whose copy differs
```

No database, no token, nothing to rotate. And "has the site changed?" is now answered by
comparing against what is *actually deployed*, which is a more truthful question than diffing
a file in a repo.

Measured: the whole cycle takes **~5.7s** (scrape 18 domains + 6 assistant reads), far inside
the 300s limit. An earlier estimate of ~60s was wrong — the scraper fetches section pages
concurrently.

Verified idempotent: re-running against an already-current Fuel IX reports 6 unchanged, 0
patched. Without that it would rewrite every assistant daily.

### What this costs

- **No git audit trail of corpus changes.** Accepted deliberately; the corpus is a mirror of a
  public site, and the gates still refuse a broken scrape.
- **`resourceLinks.data.ts` cannot be regenerated at runtime.** EN→FR resource pairing stays a
  reviewed, local change via `cli refresh`. It changes rarely; guideline text changes more often.
- The committed `all_rec_markdown.md` will drift from what is deployed. It remains the source
  for local dev and the OpenAI path.

### Security

`/api/cron/refresh` scrapes and then patches six production assistants, so it is gated on
`CRON_SECRET` — Vercel sends it as `Authorization: Bearer $CRON_SECRET`. The endpoint refuses
to run at all when the secret is unset, rather than defaulting to open.

### Remaining GitHub workflow

Only `content-verify.yml` (runs on pull requests). PR-triggered workflows are not subject to
the dormancy rule, and it needs no maintenance.

---

## 3. Where it runs — and why not Vercel *(superseded — see §3b)*

`vercel.json` rewrites all `/api/*` to a single serverless function. That path **cannot** do this:
functions are request-scoped with execution limits, and `ScrapingCache` lives in process memory —
it dies on every cold start and is duplicated across concurrent instances. It can never be the
"last known state".

**Run it in GitHub Actions.** The decisive advantage:

> **Git is the change-detection store.** The committed files *are* the last known state. Scrape →
> render → `git diff`. Non-empty diff = the source changed. No database, no extra infrastructure.

It also gives review, audit trail, blame, and one-command rollback on clinical content — which a
cron job writing to a database does not.

```
.github/workflows/content-refresh.yml   weekly + manual dispatch  → scrape, render, open PR
.github/workflows/content-publish.yml   on merge to main          → push to Fuel IX
```

---

## 4. The pipeline

```
        ┌──────────── FETCH ────────────┐
  EN:   /section/* → domains → recs     │
        /tools-resources/ → tools       │      ┌── PAIR ──┐      ┌── RENDER ──┐     ┌── PUSH ──┐
                                        ├─────▶│  by rec  │─────▶│  corpus.md │────▶│ assistants│
  FR:   /gestion/, /eval-retour/,       │      │  number  │      │  links.ts  │     │ vec store │
        /prevention-et-sport/,          │      │  by tool │      │ manifest   │     │           │
        /biomarqueurs/ → recs           │      │  number  │      └────────────┘     └───────────┘
        /ressources/, /ressources-en-   │      └──────────┘             │
        francais/ → resources           │                          git diff?
        └───────────────────────────────┘                               │
                                                                    open PR
```

### Stage 1 — Fetch

Extend `core/scraper.py` with a French target set. **French recommendations exist** — verified at
`/fr/` — but at different slugs and, critically, **without `#rec-NNN` anchors**:

| | English | French |
|---|---|---|
| Sections | `/section/managing/`, `/domain/acute/` | `/gestion/`, `/eval-retour/`, `/prevention-et-sport/`, `/biomarqueurs/` |
| Rec anchors | `#rec-614` | **none** — numbers are plain text only |
| Resources | `/tools-resources/` | `/ressources/` **and** `/ressources-en-francais/` |

Consequence: a French answer can deep-link to a *domain page* but never to an individual
recommendation. Not a blocker — it constrains what FR links can point at.

### Stage 2 — Pair

**Recommendations: deterministic.** Both languages number recommendations identically
(`1.1a`, `2.1b`, `6.2d`, `14.1`). That number is a language-independent primary key — EN 2.1b ↔ FR
2.1b, no fuzzy matching, no LLM. This is the single biggest reason this project is tractable.

**Resources: confidence-tiered.** No single key works, so score and route by confidence:

| Tier | Rule | Confidence | Action |
|---|---|---|---|
| 1 | Tool number: `Tool 6.1` ↔ `Outil 6.1` | high | auto-accept |
| 2 | Known-pair filename (`INESSS_pamphlet_*` ↔ `INESSS_Depliant_*`) | high | auto-accept |
| 3 | Normalized-title similarity above threshold | medium | **queue for review** |
| 4 | No candidate | — | English fallback, marked `(en anglais)` |

Tier 3 never auto-publishes. Today's hand-built table becomes the **seed + regression fixture**:
the generator must reproduce all 25 existing pairs, or the run fails. That protects the
verification work already done.

**The traps this must survive** — all found by hand today, all now regression cases:
- FR "Retour au sport" points at the return-to-**activity** file → ambiguous, must not auto-pair.
- `/fr/scorecalculator` returns 200 but **soft-404s to the site root** → liveness check must
  detect redirect-to-root, not just status 200.
- Child SCOAT6 has no French version → must resolve to "no pair", not a near-miss.

### Stage 3 — Render

Deterministic emitters, no network:
- `all_rec_markdown.md` (EN) and `all_rec_markdown.fr.md` (FR)
- `lib/i18n/resourceLinks.ts` — generated, same shape as today's hand-built file
- `data/content-manifest.json` — per-unit content hashes, the diffable state record

### Stage 4 — Push (on merge only)

Three sinks, all with existing primitives:

| Sink | Mechanism | Exists |
|---|---|---|
| Assistant instructions ×6 | `api/update_fuelix_instructions.py` | ✅ |
| "Living guideline tools" vector store | `POST /files` + attach (`api/fuelix.py:369`) | ✅ primitives; sync logic is new |
| `resourceLinks.ts` | normal Vercel deploy | ✅ |

Vector store sync must be **idempotent by content hash** — upload changed docs, attach, detach
stale, never re-upload unchanged files.

---

## 5. Safety gates

Every gate is a hard failure that aborts the run and leaves the last good state committed:

1. **Shrink guard** — abort if the corpus loses more than 10% of its recommendations or any
   domain renders empty. This is the site-redesign killer.
2. **Liveness gate** — every emitted URL probed. Redirect-to-root counts as dead (§ the 5P trap).
   Regression on today's baseline: 45/45 table URLs, 85/141 clean corpus URLs.
3. **Pair regression** — all 25 existing EN→FR pairs must be reproduced.
4. **Schema gate** — rendered TS must type-check; rendered markdown must parse.

---

## 6. Change detection

Per-unit content hashes in `data/content-manifest.json`. Each run classifies every unit as
`added` / `removed` / `changed` / `unchanged`, and the PR body is generated from that
classification — so the reviewer sees *"Rec 6.2d text changed; Tool 8.2 URL moved; 1 new FR pair"*,
not a 3,000-line diff.

**Cadence:** weekly, plus manual dispatch. This is a *living* guideline — it updates
occasionally, not daily. Daily runs would mostly produce empty diffs and train people to ignore
the PRs.

---

## 7. Two-speed approval

| | Tier A — auto-merge | Tier B — human review |
|---|---|---|
| What | URL redirects resolved, liveness repairs, no text change | Any recommendation text change, added/removed tools, any new FR pairing |
| Gate | All safety gates pass | All gates pass **+ human approval** |
| Why | Provably cannot alter clinical meaning | Can |

Tier A is what would have kept the corpus from rotting to 40% broken. Tier B is what stops a
scraper bug from silently rewriting medical guidance.

---

## 8. Build phases

| Phase | Work | Size |
|---|---|---|
| 0 | Promote today's throwaway scripts into `scripts/` (liveness audit + table verify) and wire a CI check. **Immediate value — detects rot starting now.** | S |
| 1 | French fetch: FR targets in `core/scraper.py`, FR rec + resource extraction | M |
| 2 | Pairing engine + confidence tiers + regression fixture from today's 25 pairs | M |
| 3 | Renderers + manifest. **Includes reconciling generated vs. hand-curated corpus (§9).** | L |
| 4 | `content-refresh.yml` — scrape, render, diff, open PR with classified changes | M |
| 5 | `content-publish.yml` — assistant push + idempotent vector store sync | M |
| 6 | Tier A auto-merge | S |

Phase 0 is independent and worth doing regardless of whether the rest proceeds.

---

## 9. Risks

**The corpus migration is the dangerous phase, not the scraping.** `all_rec_markdown.md` is
hand-curated: level-of-evidence images, "Online tools to consider" blocks, ordering, and prose
that may not exist on the site. Regenerating it from the scraper **will silently drop whatever
curation isn't reproducible**. Phase 3 must diff generated-vs-current and reconcile item by item
before anything switches over. Budget real time here; this is where the project can quietly go
wrong.

**French generation is a separate, larger decision.** A French corpus does not automatically
improve French answers. Today one assistant serves both languages per user type
(`core/prompts.py:255-266`), answering in French from the *English* corpus. Using a French corpus
means either 12 assistants instead of 6, or moving the corpus out of assistant instructions
entirely. **Recommend deferring** — this plan makes the French corpus *available*; deciding to
generate from it is its own project.

**Scraper fragility is inherent.** Selectors break on redesign. The shrink guard converts that
from silent corruption into a loud failure, but it cannot prevent it.

---

## 10. Decisions taken (2026-07-29)

| Decision | Choice |
|---|---|
| Start point | **Straight to the full pipeline** (no standalone Phase 0) |
| French recommendations | **Out of scope entirely** |
| Tier A auto-merge | **Yes** |

### Consequences of skipping French recommendations

Two follow-on effects worth stating plainly, because they change the shape of the work:

1. **The deterministic pairing key no longer applies.** Recommendation numbers (`2.1b` ↔ `2.1b`)
   were the exact, no-heuristics key — but only for recommendations. With FR recommendations out,
   **everything left to pair is resources**, which is precisely the confidence-tiered fuzzy half.
   The pairing engine is now all hard cases and no easy ones. It stays worthwhile — the resource
   map is what feeds the FR link feature — but the regression fixture (§4 Tier rules) carries
   more weight, since there is no exact-key path to fall back on.

2. **French answers still generate from the English corpus.** Unchanged from today. The `/fr/`
   guideline content stays unused. Revisit only if French answer quality is raised as an issue.

Scope is therefore: **English recommendations + English tools + French *resources*.**

### Still open

- **Cadence** — defaulting to weekly + manual dispatch. Daily produces mostly empty diffs and
  trains reviewers to ignore the PRs.
- **Who reviews Tier B PRs?** A pipeline nobody has agreed to watch is a pipeline that
  auto-merges by neglect. Tier A being automatic makes this *more* important, not less: the
  human-gated queue is now exclusively the changes that alter clinical meaning.
