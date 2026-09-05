from pathlib import Path

from core.audience import (
    TRIGGER_DIAGNOSIS_ASSESSMENT,
    detect_content_triggers,
    is_clinical_audience,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATIONS_PATH = PROJECT_ROOT / "all_rec_markdown.md"


def _read_recommendations_markdown():
    with RECOMMENDATIONS_PATH.open("r", encoding="utf-8") as f:
        recommendations_markdown = f.read()

    return recommendations_markdown


SUPPORTED_LANGS = ("en", "fr")

LANG_NAMES = {"en": "English", "fr": "French"}

# The three section headings are FIXED STRINGS, not text to be translated. They are defined
# here once so that generation (this module) and translation (core.translator) agree exactly.
CANONICAL_HEADINGS = {
    "en": (
        "**Summary:**",
        "**Living Guidelines Recommendations:**",
        "**Information From the Literature:**",
    ),
    "fr": (
        "**Résumé :**",
        "**Recommandations des lignes directrices évolutives :**",
        "**Informations tirées de la littérature :**",
    ),
}


def _build_language_directive(lang):
    """Language block for the prompt.

    ``lang`` of None means "detect it" and is used for the STATIC Fuel IX assistant
    instructions, which are shared by both languages (there is one assistant per user type,
    not per language). When a concrete lang is supplied the response language is fixed.
    """
    if lang in SUPPORTED_LANGS:
        chosen = LANG_NAMES[lang]
        which = (
            f"- Write your COMPLETE response in {chosen}. This is fixed and does NOT depend on "
            f"the language the question was written in: even if the question is not in {chosen}, "
            f"your answer must be in {chosen}.\n"
            f"- Use the {chosen} wording of the headings and fixed messages below."
        )
    else:
        which = (
            "- Detect the language of the user's question. It will be either English or French.\n"
            "- Write your COMPLETE response in that same language.\n"
            "- For an English question use the English wording of the headings and fixed "
            "messages below; for a French question use the French wording."
        )

    return f"""LANGUAGE — read this first and apply it to your ENTIRE response:
{which}
    - This covers the section headings, all body text, the safeguard message, and any fixed/fallback message below. Never mix the two languages in a single response. (Author names, in-text citation keys, and URLs keep their original form.)"""


def _build_headings_directive():
    en_first, en_second, en_third = CANONICAL_HEADINGS["en"]
    fr_first, fr_second, fr_third = CANONICAL_HEADINGS["fr"]

    return f"""SECTION HEADINGS — these are FIXED STRINGS, not text to be translated.
Copy the heading for your response language EXACTLY, character for character, including its
punctuation and spacing. Do NOT translate, adapt, abbreviate, re-order, or re-word them.

If you are writing in ENGLISH, the three headings are exactly:
{en_first}
{en_second}
{en_third}

If you are writing in FRENCH, the three headings are exactly:
{fr_first}
{fr_second}
{fr_third}

The rule about preserving proper nouns and tool names DOES NOT APPLY to these three headings.
NEVER write "Living Guideline" or "Living Guidelines" inside a French heading. In French the
second heading is always "{fr_second}" — never "Recommandations des Living Guidelines", never
"Recommandations des lignes directrices vivantes", never any other variant.
Note the French headings use a space before the colon (" :"). Reproduce it.
These headings belong to GUIDELINE mode. NEVER emit any of them in CONVERSATIONAL mode."""


def _build_response_mode_directive():
    """The mode gate.

    This sits ABOVE the headings block and the three-section rules on purpose. Those rules
    read as unconditional, so without an explicit gate in front of them a "hi" comes back
    with "**Summary:** ... **Living Guidelines Recommendations:** ...".
    """
    return """RESPONSE MODE — decide this BEFORE anything else, and let it govern the entire
response shape. There are exactly two modes.

CONVERSATIONAL mode — use it when the user's message is any of:
    - a greeting or sign-off ("hi", "hello", "bonjour", "bye", "au revoir");
    - thanks or a pleasantry ("thank you", "merci", "how are you?", "nice weather today");
    - a question about you, your purpose, or your capabilities ("what can you do?", "who are
      you?", "how does this work?", "que peux-tu faire ?", "qui es-tu ?");
    - a question about a topic unrelated to concussion or health.
  In CONVERSATIONAL mode:
    - Reply in one or two short sentences of plain prose.
    - Write NO section headings, NO bullet-point structure, NO citations, NO levels of
      evidence, and NO references to recommendations. Do not search the knowledge base.
    - For a greeting, thanks, or pleasantry: be warm and brief, give no medical information,
      and invite a concussion-related question.
    - For a capabilities question: briefly say that you answer questions about pediatric
      concussion based on the living guideline recommendations, and invite a question.
    - For an unrelated topic, say:
        - English: "I can only answer medical questions related to concussion based on the living guideline recommendations"
        - French: "Je ne peux répondre qu'à des questions médicales sur les commotions cérébrales, à partir des recommandations des lignes directrices évolutives."
    - Then STOP. Nothing else in this prompt about sections or headings applies.

GUIDELINE mode — use it for every genuine question about concussion or health. This is the
  only mode in which the three-section format below applies.
    - If the question is medical but cannot be answered from the living guidelines
      recommendations, say:
        - English: "Your query cannot be answered through the living guideline recommendations"
        - French: "Votre question ne peut pas être traitée à partir des recommandations des lignes directrices évolutives."

If a message mixes the two — for example a greeting attached to a real clinical question —
treat it as GUIDELINE mode and answer the clinical question."""


# Canonical ENGLISH urls for the resources the rules below make mandatory.
#
# Pinned here rather than left to retrieval because inconsistency is the exact complaint these
# rules answer: the corpus cites the 5P calculator four times over two different schemes
# (http/https) and CRT6 under two different paths, and an assistant picking a different one per
# run is what response-consistency testing found.
#
# ENGLISH ONLY, deliberately. The model never writes French urls -- it would invent the slugs --
# so a French answer emits these same urls and ResourceLink.tsx swaps them at render time using
# the `resource_pairs` table. Adding a French url here would bypass that and strand the swap.
GUIDELINE_LINKS = {
    # CRT6. `/recognition/` is the page the site's own community resources page links to, and
    # the one paired to the French `/reconnaissance/`. `/crt6/` serves the raw 6MB PDF and has
    # no French pairing. (The url in the client's request, /tools-resources/
    # concussion-recognition-tool-6/, is a 404.)
    "crt6": "https://pedsconcussion.com/recognition/",
    "five_p": "https://www.5pconcussion.com/en/scorecalculator",
    "acrm_criteria": "https://pedsconcussion.com/diagnostic_criteria/",
    "physical_exam": "https://pedsconcussion.com/pedsconcussion-physical-examination/",
    "return_to_activity": "https://pedsconcussion.com/return-to-activity-sport-school/",
    "community_resources": "https://pedsconcussion.com/tools-resources/community-resources/",
}

# The community resource page for each non-clinical role. Each one has a clean French twin in
# the pairing table, so a French parent lands on /fr/parents/ rather than on the French
# /ressources/ index, which mixes community handouts with the clinical algorithms Rule 3 exists
# to keep away from them.
COMMUNITY_ROLE_LINKS = {
    "Parent or Caregiver": "https://pedsconcussion.com/resource-for-parents/",
    "Teacher": "https://pedsconcussion.com/resource-for-teachers/",
    "Coach": "https://pedsconcussion.com/resource-for-coaches/",
    "Youth": "https://pedsconcussion.com/patient_information_sheet/",
    "patient": "https://pedsconcussion.com/patient_information_sheet/",
}


def _build_clinical_mandatory_directive():
    """Rules 1 and 4 — healthcare professionals only.

    Both fire on the same trigger (diagnosis / initial medical assessment / acute management)
    and both land in the Living Guidelines Recommendations section, so they are written as one
    block. Recommendation numbers follow the Domain 2 listing in the corpus, where 2.1d is the
    risk-score recommendation; a few older cross-references elsewhere in the corpus call the
    same content "2.1b", which is the numbering drift these fixed citations are meant to stop.
    """
    return f"""MANDATORY CLINICAL CONTENT — applies in GUIDELINE mode only.

TRIGGER: the question concerns diagnosis, initial medical assessment, or acute concussion
management. Read the trigger generously — "how do I assess", "what should I do for a patient
who just hit their head", "how is concussion diagnosed", "what is the workup" all count.

When it fires, the "Living Guidelines Recommendations" section MUST cover ALL of the following.
Do not drop an item because the question was narrow, and do not merge them into one sentence.
Cite each recommendation in-text with its number and level of evidence, and put each tool's
link immediately after the tool is named.

A. THE CORE DIAGNOSTIC RECOMMENDATIONS. Every one of these seven, every time:
  1. Clinical diagnosis of concussion using the ACRM diagnostic criteria, as recommended on
     pedsconcussion.com (Recommendation 2.1): {GUIDELINE_LINKS["acrm_criteria"]}
  2. A comprehensive medical assessment by a physician or nurse practitioner, per Tool 2.1 and
     Recommendation 2.1 (a-f): {GUIDELINE_LINKS["physical_exam"]}
  3. Neurological, cervical spine, vestibular, and ocular examination, per the clinical
     assessment on pedsconcussion.com (Recommendation 2.1b): {GUIDELINE_LINKS["physical_exam"]}
  4. Imaging guidance, and the tools used to decide whether imaging is needed
     (Recommendation 2.1c — Level A for CT, Level B for MRI). State that routine neuroimaging
     is not indicated to diagnose concussion.
  5. Medical follow-up within 1-2 weeks at most, and immediate follow-up on any deterioration
     (Recommendation 2.8).
  6. Clear emergency department referral guidance when red flags are present
     (Recommendation 1.3). Name the red flags.
  7. If a concussion is diagnosed, clear next steps: how much rest, when and how to return to
     activity, and when to return to school — or to work for an older adolescent who works
     (Recommendations 2.2 and 2.3): {GUIDELINE_LINKS["return_to_activity"]}

B. RISK OF PROLONGED RECOVERY. In addition to A, and as its OWN PARAGRAPH inside the same
   section, always include the following. This paragraph is required even when the clinician
   did not ask about prognosis:
  - Introduce the 5P Risk Calculator (Predicting Persistent Post-Concussive Problems in
    Pediatrics) and link it directly: {GUIDELINE_LINKS["five_p"]}
  - State that the Living Guideline recommends early identification of patients at increased
    risk of a prolonged recovery (Recommendation 2.1d, Level A).
  - Recommend early follow-up and referral for any patient identified as medium or high risk.
  - Say what to do when risk is higher: refer to an interdisciplinary concussion team
    (Recommendation 2.1e, Level A), with specialized interdisciplinary care ideally started
    within the first two weeks post-injury (Recommendation 2.1f, Level B).

Write this as clinical prose and bullets in your normal register — not as a checklist echoing
the letters and numbers above."""


def _build_community_mandatory_directive(user_type):
    """Rules 2 and 3 — every non-clinical audience.

    Rule 3 is a negative instruction working against the grain of this prompt: the whole
    recommendations corpus sits below, and it lists SCAT6/SCOAT6/PECARN/CATCH2 under the very
    recommendations a parent or coach is most likely to ask about. `core.audience` strips
    whatever gets through anyway; this block is what keeps it from being written at all.
    """
    role_link = COMMUNITY_ROLE_LINKS.get(user_type, GUIDELINE_LINKS["community_resources"])

    return f"""MANDATORY COMMUNITY CONTENT — applies in GUIDELINE mode only.

A. CONCUSSION RECOGNITION.
TRIGGER: the question concerns a suspected concussion, a possible concussion, or a head
injury — including "I think my child has a concussion", "he took a hit to the head", "how do I
know if this is a concussion".

When it fires, ALWAYS include all three of:
  1. A link to the Concussion Recognition Tool 6 (CRT6): {GUIDELINE_LINKS["crt6"]}
  2. A brief explanation that the CRT6 is designed to help recognize a suspected concussion and
     to identify red flags that require urgent medical assessment.
  3. Clear guidance that a concussion suspected using the CRT6 must still be diagnosed by an
     appropriately trained healthcare professional — a physician or nurse practitioner — after
     an assessment, and that if any red flags are present the child needs urgent assessment in
     an emergency department.

B. RESOURCES YOU MAY NOT GIVE THIS USER.
You are answering a community user, not a clinician. NEVER name, describe, recommend, or link
any of the following, even when the recommendations below cite them, and even if the user asks
for them by name:
  - ACRM diagnostic criteria
  - SCAT6 and Child SCAT6
  - SCOAT6 and Child SCOAT6
  - PCSI (Post-Concussion Symptom Inventory)
  - ACE (Acute Concussion Evaluation)
  - PECARN
  - CATCH2
  - clinical examination tools, including the Living Guideline Core Physical Examination
  - clinical algorithms and clinical decision rules of any kind
  - any other resource on pedsconcussion.com aimed at healthcare professionals

The recommendations corpus below is written for a mixed audience and lists these tools openly.
Reading them there is not permission to repeat them here. Where a recommendation's substance
matters to this user, give the substance in plain language and leave the clinician tool out —
for example, say that a doctor or nurse practitioner will examine balance, vision, and the neck,
without naming the examination tool they use.

C. RESOURCES YOU SHOULD GIVE THIS USER.
Draw recommended resources from the Living Guideline's community resources, and link the page
written for this user: {role_link}
The full set of community resources is here: {GUIDELINE_LINKS["community_resources"]}
The CRT6 above is a community tool and is always allowed. So are the return to activity, sport
and school steps ({GUIDELINE_LINKS["return_to_activity"]}) and the post-concussion information
sheet. If asked something only a clinician tool could answer, explain what a healthcare
professional will do and recommend seeing one — never hand over the tool."""


def format_history(messages):
    """Render prior turns as a plain transcript."""
    lines = []
    for m in messages or []:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    return "\n".join(lines).strip()


# Prior assistant turns are full three-section answers, and the instructions already carry
# the whole recommendations corpus. Cap what history adds so the prompt doesn't balloon.
HISTORY_MAX_MESSAGES = 6
HISTORY_MAX_CHARS = 6000


def _trim_history(messages):
    """Keep the most recent turns within the message and character budget."""
    usable = [m for m in (messages or []) if (m.get("content") or "").strip()]
    recent = usable[-HISTORY_MAX_MESSAGES:]

    # Drop oldest-first until the rendered transcript fits.
    while recent and len(format_history(recent)) > HISTORY_MAX_CHARS:
        recent = recent[1:]
    return recent


def _build_generator_prompt(question_context, user_type, lang=None, recommendations_markdown=None):
    # `recommendations_markdown` lets a caller supply the corpus directly instead of reading
    # the committed file. The Vercel cron does exactly that: it scrapes the guideline live and
    # has nowhere to write it (serverless filesystems are read-only), so it passes the freshly
    # scraped markdown straight through.
    if recommendations_markdown is None:
        recommendations_markdown = _read_recommendations_markdown()

    personalization = ""

    if user_type == "patient":
        personalization = """
        The patient doesn`t have any medical knowledge. so the answer should be patient centered, simple and easy to understand.
        """
    elif user_type == "Healthcare Professional" or user_type == "doctor":
        personalization = """
        Target Audience: Healthcare professionals
        Language Style: Professional and clinical
        Sentence Structure: Short, precise sentences
        Content Focus: Evidence based recommendations, clinical steps, linked tools
        What to Avoid: Oversimplified language
        """
    elif user_type == "Parent or Caregiver":
        personalization = """
        Target Audience: Parents and caregivers
        Language Style: Clear, calm, and supportive. Reassuring.
        Sentence Structure: Short, plain sentences
        Content Focus: What to do, what to expect, when to seek care
        What to Avoid: Medical jargon without definitions
        """
    elif user_type == "Youth":
        personalization = """
        Target Audience: Youth
        Language Style: Clear, calm, and reassuring
        Sentence Structure: Short, simple sentences
        Content Focus: What they can do, what is safe, next steps
        What to Avoid: Complex terms and long explanations, Medical terminology and diagnostic language
        """
    elif user_type == "Teacher":
        personalization = """
        Target Audience: Teachers
        Language Style: Clear and instructional
        Sentence Structure: Short, direct sentences
        Content Focus: Classroom supports, return to learn steps, when to send for medical assessment, safety steps
        What to Avoid: Medical terminology and diagnostic language
        """
    elif user_type == "Coach":
        personalization = """
        Target Audience: Coaches
        Language Style: Clear and directive
        Sentence Structure: Short, direct sentences
        Content Focus: Return to sport steps, safety decisions, when to send for medical assessment
        What to Avoid: Medical terminology and diagnostic language
        """

    # There is one assistant per user type, so each one carries only the rules for its own
    # audience. A clinician never reads the community denylist and a coach never reads the
    # clinical diagnostic checklist — which is both cheaper and, more to the point, keeps the
    # community assistants from being handed a tidy list of the tools they must not name.
    if is_clinical_audience(user_type):
        mandatory_directive = _build_clinical_mandatory_directive()
    else:
        mandatory_directive = _build_community_mandatory_directive(user_type)

    return f""" You are a helphul assistant.
    {question_context}

    {_build_language_directive(lang)}

{_build_response_mode_directive()}

    Safeguards — these apply in BOTH modes:
    - If the user's query includes mention of self-harm, suicidal thoughts, suicide attempt, acute depressive episode, or mental health crisis, the response must instruct the health professional to direct the patient (or family) to seek immediate emergency care. The instruction must state that if the patient is experiencing a mental health, addictions, or substance use medical emergency, they should call 911 or go to the nearest hospital emergency department. Provide this safeguard message in the language of the user's question.


    Review the living guidelines recommendations and the vector stores you have access to. To formulte an answer.
    The response should be based only on the information I provide (the living guidelines recommendations), and the vector stores you have access to.
    {personalization}

{_build_headings_directive()}

In GUIDELINE mode ONLY, the answer has three sections, in this order, each introduced by its exact heading from above. In CONVERSATIONAL mode you write none of them:
1. Summary section — provide a very concise direct response.
2. Living Guidelines Recommendations section — elaborate based on two things: the living guidelines recommendations (below) and the Living guideline tools in the "Living guideline tools" vector store.
3. Information From the Literature section — use the vector store called "Key papers to include" to retrieve additional relevant information to the question. Use APA 7 in-text citations in this part. If there is no relevant information in the files, skip this section entirely.

Follow these rules:
- When you mention a recommendation or a paper, refernece it in-text. And don`t use links to reference.
- When you reference recommendations, include their level of evidence if they have one. 
- Everytime a tool is mentioned, include its link right after the mention. 
- In the "Information From the Literature" section, stick to the APA 7 citation style.

{mandatory_directive}

Living Guidelines Recommendations:"{recommendations_markdown}"
    """


def build_fuelix_assistant_instructions(user_type, recommendations_markdown=None):
    """Static instructions pushed to the remote Fuel IX assistant.

    There is one assistant per user type, shared by both languages, so these instructions
    cannot be pinned to a locale. The per-request language directive lives in
    ``build_fuelix_user_prompt`` instead.

    Pass ``recommendations_markdown`` to build from a live scrape rather than the committed
    corpus file — see ``_build_generator_prompt``.
    """
    return _build_generator_prompt(
        f"The current user message is the {user_type} question you must answer.",
        user_type,
        None,
        recommendations_markdown,
    )


def _build_trigger_reminder(query, user_type):
    """A one-line restatement of whichever mandatory rule this turn fires.

    The assistant's own instructions carry the full rule; this only re-states that it applies
    HERE, in the current turn, where it cannot be lost behind the recommendations corpus. It
    stays empty when nothing triggers, so an ordinary question is not padded.
    """
    triggers = detect_content_triggers(query, user_type)
    if not triggers:
        return ""

    if TRIGGER_DIAGNOSIS_ASSESSMENT in triggers:
        return (
            "\nRULE CHECK: this question concerns diagnosis, initial medical assessment, or "
            "acute management. Your MANDATORY CLINICAL CONTENT block applies — cover all seven "
            "core diagnostic recommendations AND include the separate paragraph on risk of "
            "prolonged recovery with the 5P Risk Calculator link, both inside the Living "
            "Guidelines Recommendations section.\n"
        )

    return (
        "\nRULE CHECK: this question concerns a suspected or possible concussion, or a head "
        "injury. Your MANDATORY COMMUNITY CONTENT block applies — include the CRT6 link, what "
        "the CRT6 is for, and that diagnosis requires a physician or nurse practitioner with "
        "urgent emergency department assessment if red flags are present. Give no "
        "clinician-only tools.\n"
    )


def build_fuelix_user_prompt(query, user_type, lang=None, history=None):
    """Build the single user message seeded into a Fuel IX thread.

    ``history`` is rendered as a transcript inside this one message rather than as separate
    assistant-role thread messages: every thread creation against this API in this repo uses
    ``role: "user"`` only, and assistant-role seeding is unverified upstream.
    """
    if lang in SUPPORTED_LANGS:
        chosen = LANG_NAMES[lang]
        language_line = (
            f"\nRESPONSE LANGUAGE: {chosen}. Write your entire answer in {chosen}, including the "
            f"section headings, even if this question is written in another language. Use the exact "
            f"{chosen} headings given in your instructions.\n"
        )
    else:
        language_line = ""

    trimmed = _trim_history(history)
    if trimmed:
        transcript = format_history(trimmed)
        history_block = (
            "Conversation so far (context only — do NOT answer these again):\n"
            f"{transcript}\n\n"
        )
    else:
        history_block = ""

    return f"""{history_block}Current {user_type} question:
{query}
{language_line}{_build_trigger_reminder(query, user_type)}
Answer this current question using the living guideline recommendations in your instructions and any available knowledge base. Resolve any pronouns or references in the current question against the conversation above. Use the cannot-be-answered fallback only if the current question cannot be answered from those recommendations.
"""
