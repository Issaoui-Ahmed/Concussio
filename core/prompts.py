from pathlib import Path


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
{language_line}
Answer this current question using the living guideline recommendations in your instructions and any available knowledge base. Resolve any pronouns or references in the current question against the conversation above. Use the cannot-be-answered fallback only if the current question cannot be answered from those recommendations.
"""
