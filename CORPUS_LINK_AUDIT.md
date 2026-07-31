# Corpus Link Audit — `all_rec_markdown.md`

Every URL in the guideline corpus was probed against the live web on **2026-07-29**.
463 URL occurrences, 141 unique. **56 of 141 (40%) did not resolve cleanly.**

This document records what was repaired, what was deliberately left alone, and what
needs a decision from the guideline authors.

> ⚠️ **This file feeds the Fuel IX assistant instructions.** Editing the corpus changes
> nothing in production until the assistants are re-pushed —
> `python api/update_fuelix_instructions.py --execute` (see §4).

---

## 1. Repaired — 28 unique URLs, 79 occurrences

All replacement targets were confirmed to return 200 before being written.

### pedsconcussion.com structural moves (61 occurrences)

The site reorganized its URL scheme. Four rules covered almost everything:

| Old | New | Occ. |
|---|---|---|
| `/domain/2/#rec-*` | `/domain/acute/#rec-*` | 32 |
| `/section/b/#domain-*` | `/section/managing/#domain-*` | 13 |
| `/tool-2-6-post-concussion-information-sheet/` | `/patient_information_sheet/` | 10 |
| `/domain/5/#rec-*` | `/domain/sport_considerations/#rec-*` | 3 |
| `Tool-12.1-Concussion-Implications-...pdf` | `2022/06/Tool-12.1-Academic-accomodations.pdf` | 3 |

### Third-party moves (16 occurrences)

| Old | New |
|---|---|
| `http://www.5pconcussion.com/en/scorecalculator` | `https://` (was plain HTTP) |
| `hollandbloorview.ca/concussionhandbook` | `hollandbloorview.ca/concussion-handbook` |
| `parachutecanada.org/injury-topics/item/2587` | `parachute.ca/en/injury-topics/concussion-ed-app/` |
| `parachutecanada.org/downloads/.../Medical-Assessment-Letter_Parachute.pdf` | `parachute.ca/wp-content/uploads/2019/09/Medical-Assessment-Letter.pdf` |
| `cma.ca/scaling-virtual-care-...` | `cma.ca/latest-stories/scaling-virtual-care-...` |
| `cma.ca/sites/default/files/pdf/Patient-Virtual-Care-Guide-E.pdf` | `digitallibrary.cma.ca/link/digitallibrary57` |
| `ama-assn.org/practice-management/digital/...` | `.../digital-health/...` |
| `cdc.gov/traumaticbraininjury/pdf/tbi_patient_instructions-a.pdf` | `cdc.gov/traumatic-brain-injury/media/pdfs/2024/05/patient_discharge_instructions_eng-508.pdf` |
| `www.ichd-3.org/` | `ichd-3.org/` |

### Malformed in the corpus itself (2 occurrences)

These never worked — they are authoring errors, not link rot:

- `…/scoat-child/https://pedsconcussion.com/scoat-child/` — URL pasted twice inside one link
- `…/section/sports/pedsconcussion.com/return-to-activity-sport-school/` — two paths concatenated

---

## 2. Deliberately NOT changed

### Permalinks that redirect to a dated PDF (11 unique, 18 occ.)

`/crt6/` → `/wp-content/uploads/2023/09/CRT6.pdf`, and similar for `/scat/`,
`/phq-9_english/`, `/gad-7_english/`, `/cheo-sleep-for-youth-handout/`, `/dsm5_*`,
`/headache-diary-*`, `/tool-15-1-*`, `/tool-15-2-*`.

**These are correct as-is.** The permalink is the site's own stable short link and
returns 200; the dated `/wp-content/uploads/YYYY/MM/` path changes every time the file
is re-uploaded. Rewriting them would make the corpus rot *faster*.

### DOI links

`https://doi.org/10.1016/j.jclinepi.2010.04.026` resolves to an Elsevier URL. A DOI is a
permanent identifier by design — the redirect is the feature, not staleness.

### Bot-blocked, verified alive (4 unique, 10 occ.)

These return 403/429 to scripts but were confirmed working in a real browser:

- `bjsm.bmj.com/content/57/11/695` (429 rate-limit; also listed on the live tools index)
- `cdc.gov/heads-up/guidelines/returning-to-school.html`
- `cdc.gov/heads-up/hcp/training/index.html`

CDC returns 403 to *every* scripted request, including its current URLs — so a 403 from
this host is never evidence of a dead link.

---

## 3. Needs an author decision — 13 items

Left untouched per instruction. Each needs someone who knows the clinical intent.

| URL (abbreviated) | Occ. | Problem | Suggested successor |
|---|---|---|---|
| `healthmeasures.net/…/obtain-administer-measures` | 4 | 404, site reorganized | no clean 1:1 — needs a choice |
| `parinc.com/Products/Pkey/70` | 2 | redirects to a literal `/404` page | unknown product |
| `…/Tool-2.5-Four-Ps-…-draft.pdf` | 2 | 404 (note **"draft"** in filename) | `/tool-2-5-four-ps-prioritize-plan-pace-and-position/` ✅ live |
| `physiotherapyalberta.ca/…/guide_telerehabilitation.pdf` | 2 | org renamed to CPTA, doc gone | none found |
| `test-parachutedev.pantheonsite.io/…` | 1 | ⚠️ **staging host** leaked into the corpus | Parachute return-to-sport resource |
| `parachutecanada.org/…/Concussion-Parents-Caregivers.pdf` | 1 | 404 | `parachute.ca/…/Concussion-Guide-for-Parents-and-Caregivers.pdf` ✅ live |
| `thechildren.com/…/concussion_kit-brochure_web_spread.pdf` | 1 | 404 | `montrealchildrenshospital.ca/…/2023-10-ConcussionKit-Brochure_EN_WEB.pdf` ✅ live |
| `thechildren.com/…/md_discharge_form_web.pdf` | 1 | 404 | `montrealchildrenshospital.ca/…/2023-09_pads-dischargeforms_web_en.pdf` ✅ live |
| `braininjuryguidelines.org/concussion/` | 1 | soft-404 | `concussionsontario.org/` ✅ live |
| `childrensnational.org/…/10gioiapeds-pcp-handout.pdf` | 1 | 502 from host | may be transient — re-check |
| `archives-pmr.org/article/S0003-9993(23` | 1 | URL **truncated at the `(`** when authored | full article id unknown |
| `cdc.gov/headsup/schools/parents.html` | 1 | confirmed 404 in browser | `cdc.gov/heads-up/guidelines/returning-to-school.html` ✅ live |

### Mislabeled link (not a dead link)

**[`all_rec_markdown.md:152`](all_rec_markdown.md:152)** —

```
[After a Concussion: Return to Sport Strategy](https://www.cdc.gov/heads-up/guidelines/returning-to-school.html) (Parachute Canada)
```

A **Parachute return-to-sport** label pointing at a **CDC return-to-school** page. The
target resolves fine, so no automated check catches this. Either the label or the URL is
wrong, and only an author can say which.

This was found incidentally. **A systematic label-vs-target sweep has not been done** and
is worth scheduling — link rot is detectable, mislabeling is not.

---

## 4. Deployment

The corpus reaches production by two different routes:

| Path | How the corpus is read | Picks up this fix |
|---|---|---|
| OpenAI (`generate_answer`) | `build_generator_prompt()` reads the file per request | ✅ immediately |
| **Fuel IX (the mode the app actually uses)** | baked into remote assistant `instructions` | ❌ **only after a push** |

`components/ChatInterface.tsx` hardcodes `provider_mode: "fuelix"`, so the live app uses
the second path. To deploy:

```bash
python api/update_fuelix_instructions.py            # dry run — shows the diff
python api/update_fuelix_instructions.py --execute  # patches 6 assistants
```

Separately, the **"Living guideline tools" vector store** holds its own copy of the
English tool documents. Those were not in scope here and may contain the same stale URLs.
