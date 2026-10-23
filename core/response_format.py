"""Audience-specific output contract shared by prompts and deterministic formatting.

The model supplies clinical content and literature metadata. This layer repairs presentation
without inventing evidence grades, document URLs, or bibliographic metadata.
"""

import re

from core.audience import is_clinical_audience, normalize_text
from core.response_resources import LINK_RE, response_tools, tool_number, url_key


EVIDENCE_URL = "https://pedsconcussion.com/about/levels-of-evidence/"
DISCLAIMERS = {
    "en": {
        False: "This information is based on the Living Guideline for Pediatric Concussion (pedsconcussion.com), which is written for healthcare providers. It does not replace a medical assessment. If you have concerns about a child or youth, contact their healthcare provider. In an emergency, call 911.",
        True: "This information is based on the Living Guideline for Pediatric Concussion (pedsconcussion.com) and should be used alongside clinical judgement and patient preferences.",
    },
    "fr": {
        False: "Ces informations sont basées sur les lignes directrices évolutives sur les commotions cérébrales pédiatriques (pedsconcussion.com), qui sont destinées aux professionnels de la santé. Elles ne remplacent pas une évaluation médicale. Si vous avez des préoccupations concernant un enfant ou un jeune, contactez son professionnel de la santé. En cas d’urgence, composez le 911.",
        True: "Ces informations sont basées sur les lignes directrices évolutives sur les commotions cérébrales pédiatriques (pedsconcussion.com) et doivent être utilisées avec le jugement clinique et les préférences du patient.",
    },
}
EVIDENCE_DEFINITIONS = {
    "en": {
        False: ("Strong research evidence", "Some research evidence, but limited", "Based mainly on expert agreement"),
        True: ("Consistent, good-quality, patient-oriented evidence", "Inconsistent or limited-quality patient-oriented evidence", "Consensus, usual practice, opinion, or weaker-level evidence"),
    },
    "fr": {
        False: ("Données de recherche solides", "Quelques données de recherche, mais limitées", "Basé principalement sur l’accord des experts"),
        True: ("Données probantes cohérentes, de bonne qualité et axées sur les patients", "Données probantes incohérentes ou de qualité limitée, axées sur les patients", "Consensus, pratique courante, opinion ou données probantes de moindre niveau"),
    },
}
EMERGENCY_TEXT = {
    "en": "Call 911 for a seizure, loss of consciousness, or rapidly increasing confusion. Also contact the parent or caregiver.",
    "fr": "Composez le 911 en cas de convulsion, de perte de connaissance ou de confusion qui augmente rapidement. Contactez également le parent ou le proche aidant.",
}

# Verified against the publisher and PubMed (PMID 36662524). Only complete a citation when
# this specific author/year is actually cited; never insert an unrelated paper into an answer.
VAUGHAN_DOI = "https://doi.org/10.1001/jamanetworkopen.2022.51839"
VAUGHAN_REFERENCE = (
    "Vaughan, C. G., Ledoux, A.-A., Sady, M. D., Tang, K., Yeates, K. O., Sangha, G., "
    "Osmond, M. H., Freedman, S. B., Gravel, J., Gagnon, I., Craig, W., Burns, E., "
    "Boutis, K., Beer, D., Gioia, G., & Zemek, R., for the PERC 5P Concussion Team. (2023). "
    "Association between early return to school following acute concussion and symptom burden "
    "at 2 weeks postinjury. *JAMA Network Open, 6*(1), e2251839. "
    f"[https://doi.org/10.1001/jamanetworkopen.2022.51839]({VAUGHAN_DOI})"
)
VAUGHAN_RE = re.compile(r"\bVaughan\b[^\n]{0,100}?\b2023\b", re.I)
RECOMMENDATION_RE = re.compile(
    r"\b(?P<label>Recommendations?|Recommandations?)\s+(?P<number>\d{1,2}\.\d{1,2}(?:\.\d+)?[a-z]?)\b", re.I
)
AUTHOR_YEAR_RE = re.compile(r"\b[A-ZÀ-Ý][\wÀ-ÿ’'-]+(?:[^()\n]{0,80}?)\b(?:19|20)\d{2}[a-z]?\b")
INTERNAL_LABEL = r"(?:<<\s*)?copilot(?:\s*>>)?\s+knowledge\s+base\s+citations"
INTERNAL_HEADING_RE = re.compile(rf"^\s*(?:\#{{1,6}}\s*)?[*_]*\s*{INTERNAL_LABEL}\s*[*_:]*\s*$", re.I)
INTERNAL_INLINE_RE = re.compile(
    rf"(?:[*_]{{1,3}})?{INTERNAL_LABEL}\s*[*_:]*\s*(?:[-–—]\s*)?(?:\[\d+\](?:\s*[,;]\s*\[\d+\])*)?", re.I
)
EVIDENCE_RE = re.compile(r"(?:levels? of evidence|niveaux? de (?:preuve|données probantes))\s*[:：]?\s*[*_]*\s*[ABC]\b|\b(?:level|niveau)\s+[*_]*[ABC]\b|(?:level|niveau)[- ]?[ABC]\.png", re.I)
RED_FLAG_RE = re.compile(r"\bred flags?\b|\bwarning signs?\b|\bseizures?\b|loss of consciousness|rapidly (?:increasing|worsening) confusion|\bsignes? d[’' ]alerte\b|\bdrapeaux? rouges?\b|\bconvulsions?\b|perte de (?:connaissance|conscience)", re.I)
FOOTER_HEADING_RE = re.compile(
    r"^\s*(?:\#{1,6}\s+|\*\*|__)?(?P<name>Sources|References|Références|"
    r"Level of Evidence legend|Levels? of Evidence|Légende (?:des niveaux? de preuve|du niveau de preuve)|"
    r"Niveaux? de preuve|Disclaimer|Avertissement)\s*[:：]?\s*(?:\*\*|__)?\s*$", re.I
)


def response_language(answer: str, lang: str | None = None) -> str:
    if lang in ("en", "fr"):
        return lang
    words = set(normalize_text(answer).split())
    return "fr" if len(words & {"bonjour", "vous", "votre", "une", "les", "des", "pour", "commotion", "resume"}) >= 2 else "en"


def evidence_legend(user_type: str | None, lang: str) -> str:
    title = "Level of Evidence legend" if lang == "en" else "Légende des niveaux de preuve"
    definitions = EVIDENCE_DEFINITIONS[lang][is_clinical_audience(user_type)]
    return f"**[{title}]({EVIDENCE_URL}):**\n\n" + "\n".join(
        f"- {letter} = {definition}" for letter, definition in zip("ABC", definitions)
    )


def build_response_presentation_directive(user_type: str | None) -> str:
    clinical = is_clinical_audience(user_type)
    citation_rule = (
        "Keep linked recommendation citations and APA 7 author-year citations inline. Also give full literature references in Sources."
        if clinical else
        "For this non-clinician audience, keep the body readable: move recommendation citations, numeric citation markers, and literature author-year attributions into Sources at the end. Do not put a citation in each bullet. Keep useful, directly linked tools in the body, and include their links in Sources. Preserve the evidence grades of cited recommendations in Sources."
    )
    return f"""RESPONSE PRESENTATION — applies to this answer, including any fallback or conversational reply.
These rules replace any older instruction about not linking recommendations or only using in-text references.
- Use the exact English heading **Living Guideline Recommendations:** (singular Guideline).
- Never show internal retrieval markers, file IDs, raw filenames, or strings such as copilot knowledge base citations - [3].
- Every recommendation number must be a Markdown link to its pedsconcussion.com/domain/N/ page, using its published anchor if available. Link EVERY occurrence, including in Sources. Do not invent anchors.
- Every tool mention must use its human-readable published title as a Markdown link to the actual document URL in the supplied material. Never use a filename as the label. For example: [Tool 12.2: Letter of Accommodation from the Concussion Care Team to the School](https://pedsconcussion.com/wp-content/uploads/2019/07/Tool-12.2-Template-for-Concussion-Team_Letter-to-the-Child_Adolescent_School.pdf).
- {citation_rule}
- Every paper cited in Information From the Literature must have a full reference in Sources: authors, year, article title, journal, volume/issue, pages or article number, and a DOI hyperlink. Use only verified metadata from the retrieved paper or the reference below. Never invent a DOI or a reference; omit a paper if its identity cannot be established. Omit the literature section if no relevant paper is available.
- If Vaughan et al. (2023) on early return to school is cited, use this full reference: {VAUGHAN_REFERENCE}
- When listing red flags, say plainly: {EMERGENCY_TEXT['en']} Translate that instruction for French answers. This is in addition to any other urgent-care guidance.
- End in this order: Sources (when sources were cited), Level of Evidence legend (only when the answer cites an evidence level), then the audience-specific disclaimer as the FINAL line. Do not add text after the disclaimer. Do not duplicate the footer.
- In English use this legend:\n{evidence_legend(user_type, 'en')}
- In French use this legend:\n{evidence_legend(user_type, 'fr')}
- English final disclaimer: {DISCLAIMERS['en'][clinical]}
- French final disclaimer: {DISCLAIMERS['fr'][clinical]}
"""


def strip_internal_citations(answer: str) -> str:
    """Remove provider artifacts without consuming the medical text after an inline marker."""
    cleaned = []
    internal_block = False
    file_search_block = False
    for line in answer.splitlines():
        if re.match(r"^\s*(?:#{1,6}\s*)?[*_]*\s*(?:File Search Results|Résultats de recherche de fichiers)\b", line, re.I):
            file_search_block = True
            continue
        if file_search_block:
            if re.match(r"^\s*(?:#{1,6}\s+|\*\*[^*]+:\*\*)", line):
                file_search_block = False
            else:
                continue
        if INTERNAL_HEADING_RE.match(line):
            internal_block = True
            continue
        if internal_block and (not line.strip() or re.match(r"\s*(?:[-*+]\s*)?\[\d+\]\s+", line)):
            continue
        internal_block = False
        cleaned.append(INTERNAL_INLINE_RE.sub("", line))
    text = "\n".join(cleaned)
    text = re.sub(r"【[^】]*(?:†|:)[^】]*】|(?:filecite|cite)[^]*", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split_footer(answer: str) -> tuple[str, list[str]]:
    body, sources = [], []
    section = "body"
    for line in answer.splitlines():
        # Our linked legend heading is also recognized on a second formatting pass.
        plain = LINK_RE.sub(lambda m: m[1], line)
        heading = FOOTER_HEADING_RE.match(plain)
        if heading:
            name = normalize_text(heading['name'])
            section = "sources" if name in {"sources", "references"} else "footer"
            continue
        # Only a main content heading ends an out-of-order footer. Sources may contain
        # subheadings such as "Tools" or "Recommendations (with Levels of Evidence)".
        if section != "body" and re.match(
            r"^\s*(?:#{1,6}\s+|\*\*)(?:Summary|Résumé|Living Guideline Recommendations|"
            r"Recommandations des lignes directrices évolutives|Information From the Literature|"
            r"Informations tirées de la littérature)\s*[:：]\s*(?:\*\*)?\s*$", line, re.I,
        ):
            section = "body"
        if line.strip().startswith(("This information is based on the Living Guideline", "Ces informations sont basées sur les lignes directrices")):
            continue
        if section == "sources":
            if line.strip():
                sources.append(re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip())
        elif section == "body":
            body.append(line)
    return "\n".join(body).strip(), sources


def _link_resources(text: str, tools: dict) -> str:
    by_url = {url_key(tool.url): tool for tool in tools.values()}
    # The corpus commonly places the tool number outside the linked title.
    text = re.sub(
        r"\b(?:Tool|Outil)\s+\d{1,2}\.\d{1,2}\s*[:–—-]?\s*(\[[^\]\n]+\]\(https?://[^\s)]+\))",
        r"\1", text, flags=re.I,
    )

    def recommendation_link(match):
        number = match['number']
        domain = number.split('.')[0]
        return f"[{match[0]}](https://pedsconcussion.com/domain/{domain}/)"

    def outside_links(fragment):
        # Expand grouped references so each recommendation, including suffixes, is linked.
        # This runs before the single-reference substitution below.
        grouped = r"\b(Recommendations?|Recommandations?)\s+(\d{1,2}\.\d{1,2}[a-z]?(?:\s*(?:,\s*(?:and\s+|et\s+)?|and\s+|et\s+)\d{1,2}\.\d{1,2}[a-z]?)+)"
        def expand_group(match):
            label = "Recommandation" if match[1].lower().startswith("recommand") else "Recommendation"
            return ", ".join(f"{label} {n}" for n in re.findall(r"\d{1,2}\.\d{1,2}[a-z]?", match[2]))
        fragment = re.sub(grouped, expand_group, fragment, flags=re.I)
        fragment = RECOMMENDATION_RE.sub(recommendation_link, fragment)
        # Consume a known public title or a raw filename, preserving surrounding prose.
        pattern = r"\b(?:Tool|Outil)\s+\d{1,2}\.\d{1,2}\b"
        def replace_tool(match):
            tool = tools.get(tool_number(match[0]))
            return f"[{tool.label}]({tool.url})" if tool else match[0]
        for tool in tools.values():
            fragment = re.sub(
                rf"\b(?:Tool|Outil)\s+{re.escape(tool.number)}\s*[:–—-]\s*(?:Template:\s*)?{re.escape(tool.title)}",
                f"Tool {tool.number}", fragment, flags=re.I,
            )
        fragment = re.sub(
            r"(\b(?:Tool|Outil)\s+\d{1,2}\.\d{1,2})\s*[-:–—]\s*(?=[^\s\n]*[_-])[^\s\n,;()]+",
            lambda m: m[1] + ("." if m[0].endswith(".") else ""), fragment, flags=re.I,
        )
        return re.sub(pattern, replace_tool, fragment, flags=re.I)

    parts, end = [], 0
    for match in LINK_RE.finditer(text):
        parts.append(outside_links(text[end:match.start()]))
        tool = by_url.get(url_key(match[2])) or tools.get(tool_number(match[1]))
        if tool:
            parts.append(f"[{tool.label}]({tool.url})")
        elif RECOMMENDATION_RE.fullmatch(match[1]):
            # A supplied deep link is retained when it belongs to the correct domain.
            number = RECOMMENDATION_RE.fullmatch(match[1])['number']
            expected = f"https://pedsconcussion.com/domain/{number.split('.')[0]}/"
            target = match[2] if match[2].startswith(expected) else expected
            parts.append(f"[{match[1]}]({target})")
        else:
            parts.append(match[0])
        end = match.end()
    parts.append(outside_links(text[end:]))
    return "".join(parts)


def _community_citations(body: str, sources: list[str]) -> str:
    # Only remove citation-shaped parentheses, never parenthetical medical explanations.
    def move_parenthetical(match):
        content = match[1]
        if RECOMMENDATION_RE.search(content) or AUTHOR_YEAR_RE.search(content):
            sources.append(content)
            # A citation can share parentheses with a medical instruction. Keep that
            # instruction in the body while moving only its attribution to Sources.
            remainder = LINK_RE.sub(lambda m: "" if RECOMMENDATION_RE.fullmatch(m[1]) else m[0], content)
            remainder = re.sub(
                r"(?:Levels? of Evidence|Niveaux? de preuve)\s*:?\s*[*_]*[ABC](?:\s*[/,]\s*[ABC])*[*_]*",
                "", remainder, flags=re.I,
            )
            if RECOMMENDATION_RE.search(content):
                remainder = re.sub(r"\b(?:see|voir|and|et)\b", "", remainder, flags=re.I)
                remainder = remainder.strip(" ,;:.*")
                if remainder:
                    return f"({remainder})"
            return ""
        return match[0]

    # Markdown URLs contain parentheses, so match links atomically inside citation brackets.
    body = re.sub(r"\(((?:\[[^\]\n]+\]\([^\n)]+\)|[^()\n])+)\)", move_parenthetical, body)
    # Standalone recommendation labels are citations; a named tool remains an actionable link.
    def move_link(match):
        if RECOMMENDATION_RE.fullmatch(match[1]) or AUTHOR_YEAR_RE.search(match[1]) or match[1].isdigit():
            sources.append(match[0])
            return ""
        return match[0]
    body = LINK_RE.sub(move_link, body)
    body = re.sub(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\](?!\()", "", body)
    # Narrative citations retain a grammatical subject when the author/year moves below.
    def move_narrative(match):
        sources.append(match[0].strip())
        return "The study " if response_language(body) == "en" else "L’étude "
    body = re.sub(r"\b[A-ZÀ-Ý][\wÀ-ÿ’'-]+(?: et al\.)?\s*\((?:19|20)\d{2}[a-z]?\)\s*", move_narrative, body)
    body = re.sub(r"\b(?:See|see|According to|As recommended in|Voir|voir|Selon)\s*(?=[,.;:]|$)", "", body, flags=re.M)
    body = re.sub(r"(?m)^(\s*(?:[-*+]\s+)?)\s*(?:\*\*\s*\*\*)?\s*[:;,]\s*", r"\1", body)
    body = re.sub(r"[ \t]+([.,;])", r"\1", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    return "\n".join(line for line in body.splitlines() if not re.fullmatch(r"\s*[-*+]\s*", line)).strip()


def format_response(answer: str, user_type: str | None, lang: str | None = None) -> str:
    lang = response_language(answer, lang)
    clinical = is_clinical_audience(user_type)
    answer = strip_internal_citations(answer).replace("Living Guidelines Recommendations", "Living Guideline Recommendations")
    has_evidence = bool(EVIDENCE_RE.search(answer))
    cited_vaughan = bool(VAUGHAN_RE.search(answer))
    body, sources = _split_footer(answer)
    tools = response_tools() if re.search(r"\b(?:Tool|Outil)\b|pedsconcussion.com", body + "\n".join(sources), re.I) else {}
    body = _link_resources(body, tools)
    sources = [_link_resources(source, tools) for source in sources]
    if not clinical:
        body = _community_citations(body, sources)
        # Direct tool links belong in Sources as well as beside the useful action.
        sources.extend(m[0] for m in LINK_RE.finditer(body) if tool_number(m[1]))
    if cited_vaughan:
        sources = [s for s in sources if not VAUGHAN_RE.search(s) and VAUGHAN_DOI not in s]
        sources.append(VAUGHAN_REFERENCE)

    if RED_FLAG_RE.search(body):
        # One explicit instruction covers all three conditions, even if an older assistant
        # merely said to contact a caregiver or visit the emergency department.
        if EMERGENCY_TEXT[lang] not in body:
            body += "\n\n" + EMERGENCY_TEXT[lang]

    unique_sources = list(dict.fromkeys(source.strip() for source in sources if source.strip()))
    parts = [body]
    if unique_sources:
        parts.append("**Sources:**\n\n" + "\n".join(f"- {source}" for source in unique_sources))
    if has_evidence:
        parts.append(evidence_legend(user_type, lang))
    parts.append(DISCLAIMERS[lang][clinical])
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()
