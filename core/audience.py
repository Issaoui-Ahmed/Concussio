"""Who may be shown which resources.

Rule 3 of the response-consistency round: community users -- patients, parents/caregivers,
youth, teachers, coaches -- must never be handed clinician-facing assessment tools, while
healthcare professionals get the full set.

The split is enforced TWICE, on purpose. `core.prompts` tells each assistant what it may
name; `scrub_clinician_resources` below removes what it named anyway. Prompt-only was not a
real option here: all six assistants carry the WHOLE recommendations corpus in their
instructions, and that corpus lists SCAT6/SCOAT6/PECARN/CATCH2 inside the very
recommendations a parent is most likely to ask about (1.2, 1.4, 2.1). Asking a model to read
those lines and then not repeat them is precisely the instruction that was already being
followed inconsistently.

Scope note: this strips named clinician TOOLS, not guideline references. Deep links into
`/domain/N/#rec-NNN` stay, because every audience gets a "Living Guidelines Recommendations"
section and stripping the recommendations out of it would break the answer format.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Set, Tuple

# Everything that is not explicitly clinical is treated as community. An unknown or missing
# user type therefore gets the RESTRICTED set, which is the safe direction to fail in: the
# cost of withholding a clinician tool from a clinician is an incomplete answer, the cost of
# handing SCAT6 to a 14-year-old is the thing the client asked us to prevent.
CLINICAL_ALIASES = frozenset({"healthcare professional", "doctor"})


def is_clinical_audience(user_type: str | None) -> bool:
    return (user_type or "").strip().lower() in CLINICAL_ALIASES


def is_community_audience(user_type: str | None) -> bool:
    return not is_clinical_audience(user_type)


def normalize_text(text: str) -> str:
    """Casefold, strip accents, drop punctuation, collapse whitespace.

    Accents are stripped so one accent-free pattern matches both "évaluation" and
    "evaluation"; every pattern written against this is therefore accent-free. Shared with
    ``core.routing``, which uses it for the small-talk fast path.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_accents.casefold()
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


# --- Per-turn rule triggers ------------------------------------------------------------
#
# The assistant instructions already describe when Rules 1, 2 and 4 fire and let the model
# judge it. These patterns add a second, deterministic signal on the turn itself, appended to
# the user message as a one-line reminder. Belt and braces: the complaint that produced these
# rules was that a correctly-instructed model applied them inconsistently, and a reminder
# sitting in the current turn is far harder to lose than a clause in a very long system prompt.
#
# Over-firing costs a paragraph the user did not strictly need; under-firing costs the rule.

# Diagnosis / initial medical assessment / acute management. Clinical audiences only.
_CLINICAL_TRIGGER_PATTERNS = (
    r"\bdiagnos",
    r"\bassess",
    r"\bevaluat",
    r"\bexamin",
    r"\bwork ?up\b",
    r"\binitial (?:visit|presentation|management|care)\b",
    r"\bfirst visit\b",
    r"\bacute (?:management|care|concussion|phase|presentation)\b",
    r"\bmanage (?:an? )?acute\b",
    r"\bimaging\b",
    r"\bneuroimaging\b",
    r"\bct\b",
    r"\bmri\b",
    r"\bred flag",
    r"\bemergency department\b",
    r"\bclinical history\b",
    r"\bphysical exam",
    r"\brule out\b",
    r"\bdifferential\b",
    r"\bpresents with\b",
    r"\bjust (?:sustained|had|hit)\b",
    r"\bscreening\b",
    r"\bhistory taking\b",
    # French. These must stay at PARITY with the English list above: a concept covered in one
    # language and not the other produces exactly the bug QA found here -- "What clinical
    # history should I take?" fired the rule, "Quelle anamnèse clinique dois-je recueillir ?"
    # did not, and the French answer came back missing most of the mandatory block.
    r"\bdiagnostic",
    r"\bdiagnostiqu",
    r"\bevaluations?\b",
    r"\bevaluer\b",
    r"\bexamens?\b",
    r"\bbilans?\b",
    r"\banamnese\b",                    # clinical history
    r"\bhistoire (?:clinique|medicale)\b",
    r"\binterrogatoire\b",
    r"\b(?:premiere|initiale?) (?:consultation|visite|evaluation)\b",
    r"\b(?:consultation|visite) initiale\b",
    r"\bexclure\b",                     # rule out
    r"\beliminer\b",
    r"\bse presente\b",                 # presents with
    r"\bprise en charge\b",
    r"\baigu",
    r"\bimagerie\b",
    r"\btomodensitometrie\b",
    r"\birm\b",
    r"\burgences?\b",                   # service/salle d'urgence, or bare "urgence"
    # French plurals are their own trap: "drapeaux rouges" does not start with "drapeau rouge",
    # so a singular-only pattern silently misses the plural form people actually type.
    r"\bdrapeaux? rouges?",
    r"\bsignes? d alerte",
    r"\bantecedent",
    r"\bdepistage\b",
)

# Suspected / possible concussion or head injury. Community audiences only.
_COMMUNITY_TRIGGER_PATTERNS = (
    r"\bsuspect",
    r"\bpossible concussion\b",
    r"\bmight have\b",
    r"\bmay have\b",
    r"\bthink (?:he|she|they|my|i) \w+",
    r"\bhead injur(?:y|ies)\b",
    r"\bhead trauma\b",
    r"\bhit (?:his|her|their|my|the) head\b",
    r"\bbump(?:ed)? (?:his|her|their|my|the) head\b",
    r"\bblow to the head\b",
    r"\bknocked\b",
    r"\bconcussed\b",
    r"\bhow (?:do|would) i know\b",
    r"\bwarning sign",
    r"\bred flag",
    r"\bsigns? of (?:a )?concussion\b",
    r"\bsymptoms? of (?:a )?concussion\b",
    r"\brecogni[sz]e\b",
    # French
    r"\bsuspicion\b",
    r"\bcommotion possible\b",
    r"\bpeut etre une commotion\b",
    r"\bblessures? a la tete\b",
    r"\bcoups? a la tete\b",
    r"\btraumatismes? craniens?\b",
    r"\bs est cogne",
    r"\bcogne la tete\b",
    r"\bcomment savoir\b",
    # See the plural note on the clinical patterns above.
    r"\bsignes? d alerte",
    r"\bdrapeaux? rouges?",
    r"\bsignes? d une commotion\b",
    r"\bsymptomes? d une commotion\b",
    r"\breconnaitre\b",
)

_CLINICAL_TRIGGER_RE = re.compile("|".join(_CLINICAL_TRIGGER_PATTERNS))
_COMMUNITY_TRIGGER_RE = re.compile("|".join(_COMMUNITY_TRIGGER_PATTERNS))

TRIGGER_DIAGNOSIS_ASSESSMENT = "diagnosis_assessment"
TRIGGER_SUSPECTED_CONCUSSION = "suspected_concussion"


def detect_content_triggers(message: str, user_type: str | None) -> Set[str]:
    """Which mandatory-content rules this turn should be reminded about.

    Returns a set so callers can test membership without caring about ordering, and so an
    empty set reads naturally as "nothing to add".
    """
    normalized = normalize_text(message)
    if not normalized:
        return set()

    if is_clinical_audience(user_type):
        if _CLINICAL_TRIGGER_RE.search(normalized):
            return {TRIGGER_DIAGNOSIS_ASSESSMENT}
        return set()

    if _COMMUNITY_TRIGGER_RE.search(normalized):
        return {TRIGGER_SUSPECTED_CONCUSSION}
    return set()


# --- The denylist ----------------------------------------------------------------------
#
# Matched against URLs only. Language-independent, which matters because a French answer
# still emits ENGLISH urls -- the French swap happens at render time in ResourceLink.tsx --
# so one fragment covers both languages.
#
# "algorithm" is deliberately broad: every clinical algorithm tool on the site carries it in
# the slug, and no community resource does (the community page lists only
# /patient_information_sheet/, /resource-for-{parents,teachers,coaches}/ and /recognition/).
# "algorithym" is not a typo here -- it is a typo in Tool 2.4's real URL.
_CLINICIAN_URL_FRAGMENTS = (
    "pedsconcussion.com/scat",            # SCAT6 and Child SCAT6
    "pedsconcussion.com/scoat",           # SCOAT6 and Child SCOAT6
    "pedsconcussion.com/diagnostic_criteria",
    "pedsconcussion.com/pecarn-head",
    # Bare "physical-examination", not the full slug: the site has at least two of these
    # (the core neurological/cervical exam and Tool 15.2's virtual physical examination), and
    # a slug-exact fragment caught only the first. No community resource carries the phrase.
    "physical-examination",
    "pedsconcussion.com/vce-manual",
    "catch2",
    "canadian-assessment-of-tomography",
    "ace_v2",                             # CDC Acute Concussion Evaluation
    "archives-pmr.org",                   # the ACRM criteria paper
    "heads-up/hcp",                       # CDC Heads Up for Health Care Professionals
    "bjsm.bmj.com",
    "algorithm",
    "algorithme",
    "algorithym",
)

# Matched against the visible text, for tools named without a link.
_CLINICIAN_NAME_PATTERNS = (
    r"\bSCAT\s?6\b",
    r"\bSCOAT\s?6\b",
    r"\bSport Concussion (?:Office )?Assessment Tool\b",
    r"\bPCSI\b",
    r"\bPost-?Concussion Symptom Inventory\b",
    r"\bPECARN\b",
    r"\bCATCH\s?2\b",
    r"\bCanadian Assessment of Tomography\b",
    r"\bACRM\b",
    r"\bAmerican Congress of Rehabilitation Medicine\b",
    r"\bAcute Concussion Evaluation\b",
    r"\bLiving Guideline Core Physical Examination\b",
    r"\bVirtual Concussion Exam\b",
    r"\bExamen virtuel des commotions\b",
    # An unlinked algorithm tool, e.g. "Tool 6.1: Post-Concussion Headache Algorithm".
    r"\bTool\s+\d+(?:\.\d+)?\b[^\n]{0,80}?\b(?:Algorithm|Algorithme)\b",
    r"\bOutil\s+\d+(?:\.\d+)?\b[^\n]{0,80}?\b(?:Algorithm|Algorithme)\b",
)

# "ACE" only as a bare uppercase acronym. Case-insensitively it would match "place",
# "faced", "ace" and most of the French verb "acer" family.
_CLINICIAN_CASE_SENSITIVE_PATTERNS = (r"\bACE\b",)

_NAME_RE = re.compile("|".join(_CLINICIAN_NAME_PATTERNS), re.IGNORECASE)
_CASE_SENSITIVE_RE = re.compile("|".join(_CLINICIAN_CASE_SENSITIVE_PATTERNS))

# Crisis content is NEVER removed, whatever else it happens to name.
#
# Found in QA: asked about self-harm, the assistant answered with a bullet reading "**Get
# urgent help now.** ... active suicidal thoughts need immediate emergency department care
# (Tool 8.1 - Post-Concussion Mental Health Considerations Algorithm: <url>)". That bullet is
# crisis guidance that happens to cite an algorithm, and the scrub deleted it whole. Letting a
# tool name survive inside a safeguard is a far smaller harm than deleting the safeguard, so
# this veto is absolute.
#
# The markers are deliberately narrow -- "emergency department" alone is not one, or every
# imaging-decision bullet would claim the exemption and Rule 3 would leak through it.
_SAFEGUARD_PATTERNS = (
    # "suicid" covers suicide/suicidal/suicidaire in both languages.
    r"\bsuicid",
    r"\bself[- ]harm\b",
    r"\bhurting (?:yourself|myself|himself|herself|themselves)\b",
    r"\bhurt (?:yourself|myself|himself|herself|themselves)\b",
    r"\bkill (?:yourself|myself|himself|herself|themselves)\b",
    r"\bcrisis\b",
    r"\b911\b",
    r"\bmental health (?:emergency|crisis)\b",
    # French
    r"\bautomutilation\b",
    r"\bse faire du mal\b",
    r"\bfaire du mal\b",
    r"\bcrise\b",
    r"\burgence en sant[ée] mentale\b",
)
_SAFEGUARD_RE = re.compile("|".join(_SAFEGUARD_PATTERNS), re.IGNORECASE)

# Markdown link targets plus bare urls.
_URL_RE = re.compile(r"\]\(\s*(<?[^)\s]+>?)[^)]*\)|(https?://[^\s<>\)\]]+)", re.IGNORECASE)

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_LEAD_IN_RE = re.compile(r":\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Dropping a line's FIRST sentence can leave the next one starting on a conjunction that no
# longer refers to anything: "I can't send the SCOAT6. But I can share youth-friendly tools."
# becomes "But I can share youth-friendly tools." Found in QA on a question that asked for two
# forbidden tools by name.
_DANGLING_CONJUNCTION_RE = re.compile(
    r"^(?P<prefix>\s*(?:[-*+]|\d+[.)])?\s*(?:\*{1,2}|_{1,2})?)"
    r"(?:But|However|And|Instead|Mais|Cependant|Toutefois|Par contre|Et)\b[,]?\s+",
    re.IGNORECASE,
)


def _mend_dangling_conjunction(text: str) -> str:
    """Drop a now-meaningless leading conjunction and recapitalize."""
    match = _DANGLING_CONJUNCTION_RE.match(text)
    if not match:
        return text
    prefix = match.group("prefix")
    rest = text[match.end():]
    if not rest:
        return text
    return prefix + rest[0].upper() + rest[1:]


def _urls_in(text: str) -> List[str]:
    found: List[str] = []
    for match in _URL_RE.finditer(text):
        target = match.group(1) or match.group(2) or ""
        target = target.strip("<>")
        if target:
            found.append(target.lower())
    return found


def carries_safeguard(text: str) -> bool:
    """True when this fragment carries crisis guidance and must never be removed."""
    return bool(_SAFEGUARD_RE.search(text))


def _is_clinician_only(text: str) -> bool:
    """True when this fragment names or links a clinician-only resource.

    The safeguard veto is checked FIRST and outranks every denylist entry.
    """
    if carries_safeguard(text):
        return False
    for url in _urls_in(text):
        if any(fragment in url for fragment in _CLINICIAN_URL_FRAGMENTS):
            return True
    return bool(_NAME_RE.search(text) or _CASE_SENSITIVE_RE.search(text))


def _filter_line(line: str) -> Tuple[str | None, List[str]]:
    """Filter one line. Returns the line to keep (or None to drop it) and what was removed.

    A list item is dropped whole -- tools are listed one per bullet, so the bullet IS the
    unit. Prose is filtered a sentence at a time instead, because a paragraph usually
    carries clinical guidance that stays valid once the tool name is gone.
    """
    if not line.strip() or _HEADING_RE.match(line):
        return line, []

    if _LIST_ITEM_RE.match(line):
        if _is_clinician_only(line):
            return None, [line.strip()]
        return line, []

    sentences = _SENTENCE_SPLIT_RE.split(line)
    kept = [s for s in sentences if not _is_clinician_only(s)]
    removed = [s.strip() for s in sentences if _is_clinician_only(s)]
    if not kept:
        return None, removed
    if not removed:
        return line, []

    rebuilt = " ".join(kept)
    # Only mend when the line's OPENING sentence went; a conjunction mid-line still refers to
    # the sentence before it.
    if _is_clinician_only(sentences[0]):
        rebuilt = _mend_dangling_conjunction(rebuilt)
    return rebuilt, removed


def _drop_orphaned_lead_ins(original: List[str], kept: List[str | None]) -> None:
    """Blank out "Tools to consider:" when every tool under it was removed.

    Mutates ``kept`` in place. Without this the answer ends on a colon introducing nothing.
    """
    for index, line in enumerate(original):
        if kept[index] is None or not _LEAD_IN_RE.search(line):
            continue

        had_items = False
        has_survivor = False
        for offset in range(index + 1, len(original)):
            if not original[offset].strip():
                if had_items:
                    break
                continue
            if not _LIST_ITEM_RE.match(original[offset]):
                break
            had_items = True
            if kept[offset] is not None:
                has_survivor = True
                break

        if had_items and not has_survivor:
            kept[index] = None


def scrub_clinician_resources(answer: str) -> Tuple[str, List[str]]:
    """Remove clinician-only tools from an answer bound for a community user.

    Returns the cleaned answer and the fragments that were removed, so a caller can log how
    often the prompt alone failed to hold the line.
    """
    if not answer:
        return answer, []

    original = answer.splitlines()
    kept: List[str | None] = []
    removed: List[str] = []

    for line in original:
        filtered, dropped = _filter_line(line)
        kept.append(filtered)
        removed.extend(dropped)

    if not removed:
        return answer, []

    _drop_orphaned_lead_ins(original, kept)

    cleaned = "\n".join(line for line in kept if line is not None)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip(), removed
