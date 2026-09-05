"""Fast path for messages that don't need the living-guidelines pipeline.

A greeting or a "what can you do?" should not pay for a Fuel IX assistant run that carries
the whole recommendations corpus and does RAG over the knowledge base — that costs ~60s and
comes back in the three-section clinical format, which is the wrong shape for "hi". This
module decides, locally and for free, whether a message can be answered from a canned reply
instead.

The medical guard is checked FIRST and vetoes every other intent. The asymmetry is
deliberate: a false negative costs the user some latency, a false positive answers a real
clinical question with a canned brush-off. When in doubt this module returns ``None`` and
the caller falls through to the full pipeline.
"""

import re
from typing import Dict, List, Optional

from core.audience import normalize_text as _normalize
from core.fuelix_chat import fuelix_chat_completion


SMALLTALK_MODEL = "gpt-4.1-mini"

# A message longer than this is never treated as undirected small talk. Greetings and thanks
# are short; anything wordier is likely a real question even if it dodges the medical terms.
SMALLTALK_MAX_WORDS = 8

# The model returns this verbatim when it judges a "small talk" message to actually be a
# health question, so the caller can fall through to the real pipeline.
ESCALATE_SENTINEL = "ESCALATE"


# `_normalize` lives in core.audience so that module can stay a leaf (nothing in core imports
# into it) while both it and this module match against the same accent-free, punctuation-free
# form. Apostrophes and hyphens become spaces there, so "qu'est-ce que" normalizes to
# "qu est ce que" and every pattern below is written that way.


# Accent-free, lowercase. Liberal on purpose — every hit here routes to the slow-but-correct
# path, so over-matching is the safe direction.
_MEDICAL_TERMS = [
    # English
    "concussion", "concussed", "head", "brain", "skull", "neck", "symptom", "headache",
    "migraine", "dizzy", "dizziness", "nausea", "vomit", "sleep", "insomnia", "rest",
    "recovery", "recover", "return to play", "return to sport", "return to school",
    "return to learn", "injury", "injured", "hit", "blow", "impact", "unconscious",
    "consciousness", "amnesia", "memory", "concentration", "cognitive", "light sensitivity",
    "photophobia", "noise", "screen", "exercise", "activity", "exertion", "treatment",
    "diagnosis", "diagnose", "assessment", "screening", "doctor", "physician", "clinician",
    "nurse", "emergency", "hospital", "medication", "medicine", "drug", "dose", "pain",
    "balance", "vision", "blurry", "fatigue", "mood", "irritab", "anxiety", "depression",
    "suicid", "self harm", "patient", "child", "children", "kid", "teen", "adolescent",
    "youth", "athlete", "player", "helmet", "sport", "protocol", "guideline", "recommendation",
    "evidence", "imaging", "scan", "mri", "scat", "symptoms",
    # "care" alone is too broad — it would veto the "take care" farewell.
    "warning sign", "warning signs", "red flag", "danger", "urgent", "safe to",
    "when can", "how long", "should i", "risk", "health", "medical", "clinical",
    "urgent care", "medical care", "health care", "healthcare",
    # French (accent-stripped)
    "commotion", "cerebrale", "cerebral", "tete", "cerveau", "crane", "cou", "symptome",
    "mal de tete", "etourdi", "etourdissement", "vertige", "nausee", "vomir", "vomissement",
    "sommeil", "dormir", "repos", "recuperation", "retour au jeu", "retour au sport",
    "retour a l ecole", "retour a l apprentissage", "ecole", "blessure", "blesse", "coup",
    "choc", "inconscient", "connaissance", "amnesie", "memoire", "concentration",
    "lumiere", "bruit", "ecran", "exercice", "activite", "effort", "traitement",
    "diagnostic", "evaluation", "depistage", "medecin", "infirmier", "urgence", "hopital",
    "medicament", "douleur", "equilibre", "vision", "floue", "fatigue", "humeur",
    "anxiete", "depression", "suicide", "automutilation", "enfant", "ado", "adolescent",
    "jeune", "athlete", "joueur", "casque", "protocole", "ligne directrice",
    "lignes directrices", "recommandation", "donnees probantes", "imagerie",
    "signe d alerte", "signes d alerte", "drapeau rouge", "danger", "urgent",
    "quand puis je", "combien de temps", "dois je", "risque", "soins", "sante", "securitaire",
]

_MEDICAL_RE = re.compile(
    r"(?:^|\s)(?:" + "|".join(re.escape(term) for term in _MEDICAL_TERMS) + r")",
)

# Whole-message matches. "hi" fast-paths; "hi, what dose of..." does not.
_GREETING_RE = re.compile(
    r"^(?:"
    r"(?:hi|hello|hey|yo|hiya|howdy|greetings)(?: there| again| everyone)?"
    r"|good (?:morning|afternoon|evening|day)"
    r"|(?:bonjour|bonsoir|salut|coucou|allo|allo)(?: a tous| tout le monde| a toi)?"
    r")$"
)

_THANKS_RE = re.compile(
    r"^(?:"
    r"(?:ok |okay |great |perfect |awesome )?"
    r"(?:thanks|thank you|thx|ty|cheers)(?: so much| a lot| very much| again| for the help)?"
    r"|(?:ok |super |merci et )?merci(?: beaucoup| bien| infiniment| encore| a vous)?"
    r"|(?:c est )?(?:parfait|super|genial|nickel)(?: merci)?"
    r")$"
)

_FAREWELL_RE = re.compile(
    r"^(?:"
    r"(?:bye|goodbye|good bye|see you|see ya|cya|take care|good night)(?: later| soon| then)?"
    r"|(?:au revoir|a bientot|a plus|a demain|bonne journee|bonne soiree|bonne nuit)"
    r")$"
)

# Substring matches — "so, what can you do?" should count.
_CAPABILITY_PATTERNS = [
    r"\bwhat (?:can|do) you do\b",
    r"\bwhat are you\b",
    r"\bwho are you\b",
    r"\bwhat can i ask\b",
    r"\bwhat do you know\b",
    r"\bhow (?:do you|does this|does it) work\b",
    r"\bhow can you help\b",
    r"\bwhat is this\b",
    r"\bwhat s this\b",
    r"\bwhat are you for\b",
    r"\bque peux tu faire\b",
    r"\bque pouvez vous faire\b",
    r"\bqui es tu\b",
    r"\bqui etes vous\b",
    r"\bqu est ce que tu (?:peux faire|fais)\b",
    r"\bqu est ce que vous (?:pouvez faire|faites)\b",
    r"\bcomment ca marche\b",
    r"\bcomment tu marches\b",
    r"\ba quoi sers tu\b",
    r"\ba quoi servez vous\b",
    r"\btu sers a quoi\b",
    r"\bcomment (?:tu peux|pouvez vous) m aider\b",
]
_CAPABILITY_RE = re.compile("|".join(_CAPABILITY_PATTERNS))

# "help"/"aide" alone is a capability question; inside a sentence it usually isn't.
_BARE_HELP_RE = re.compile(r"^(?:help|aide|au secours|menu|info|infos)$")

# Small talk is a POSITIVE allowlist, not "short and free of medical words". The denylist
# version let "What are the warning signs?" through — a real clinical question with none of
# the guarded terms in it. Anything not listed here falls through to the full pipeline.
_SMALLTALK_PATTERNS = [
    r"^how (?:are|is|s) (?:you|u|it going|things|your day)\b",
    r"^how are you doing\b",
    r"^hope (?:you|your)\b",
    r"^(?:what s|whats|wat) up\b",
    r"^sup$",
    r"^(?:comment )?(?:ca|ça) va\b",
    r"^comment (?:vas tu|allez vous)\b",
    r"^(?:tu vas|vous allez) bien\b",
    r"^quoi de neuf\b",
    r"\b(?:nice|good|lovely|beautiful|great) weather\b",
    r"\bbeau temps\b",
    r"^(?:lol|haha|hehe|cool|nice|great|awesome|super|parfait|genial|ok|okay|d accord)$",
    r"^(?:test|testing|test test|just testing|juste un test)$",
    r"^(?:i am|i m|im) (?:good|fine|ok|okay|well|great)\b",
    r"^(?:bien|tres bien|ca va bien)(?: merci)?$",
    r"^(?:good|fine|not bad|pas mal)(?: thanks| merci)?$",
]
_SMALLTALK_RE = re.compile("|".join(_SMALLTALK_PATTERNS))

CANNED_INTENTS = ("greeting", "thanks", "farewell", "capability")


def _has_medical_signal(normalized: str) -> bool:
    return bool(_MEDICAL_RE.search(" " + normalized))


def detect_simple_intent(message: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Classify ``message`` as a simple non-clinical intent, or ``None`` to use the full pipeline.

    ``history`` is the conversation so far. Mid-conversation, undirected small talk is
    suppressed: "yes", "tell me more", "et les enfants ?" are continuations of a clinical
    thread, not chit-chat. Explicit greetings/thanks/farewells/capability questions still
    fast-path at any point in the conversation.
    """
    normalized = _normalize(message)
    if not normalized:
        return None

    # First and vetoing: anything clinical goes to the real pipeline.
    if _has_medical_signal(normalized):
        return None

    if _CAPABILITY_RE.search(normalized) or _BARE_HELP_RE.match(normalized):
        return "capability"
    if _GREETING_RE.match(normalized):
        return "greeting"
    if _THANKS_RE.match(normalized):
        return "thanks"
    if _FAREWELL_RE.match(normalized):
        return "farewell"

    # Mid-conversation, undirected small talk is suppressed: "yes", "ok", "tell me more" are
    # continuations of a clinical thread, not chit-chat. Explicit intents above still apply.
    if history:
        return None

    if len(normalized.split()) <= SMALLTALK_MAX_WORDS and _SMALLTALK_RE.search(normalized):
        return "smalltalk"

    return None


# Role labels mirror lib/i18n/*.ts so the canned copy reads like the rest of the UI.
_ROLE_LABELS = {
    "en": {
        "Healthcare Professional": "healthcare professional",
        "Parent or Caregiver": "parent or caregiver",
        "Youth": "young person",
        "Teacher": "teacher",
        "Coach": "coach",
        "patient": "patient",
    },
    "fr": {
        "Healthcare Professional": "professionnel de la santé",
        "Parent or Caregiver": "parent ou proche aidant",
        "Youth": "jeune",
        "Teacher": "enseignant",
        "Coach": "entraîneur",
        "patient": "patient",
    },
}


def _role_label(user_type: Optional[str], lang: str) -> str:
    table = _ROLE_LABELS.get(lang, _ROLE_LABELS["en"])
    return table.get(user_type or "patient", table["patient"])


# `{role}` is the only placeholder. Capability copy is hand-written rather than generated:
# what a medical assistant claims it can do should not be improvised by a model.
CANNED_REPLIES = {
    "greeting": {
        "en": (
            "Hello! I'm ConcussCare. I can answer questions about pediatric concussion based "
            "on the Living Guideline for Pediatric Concussion. What would you like to know?"
        ),
        "fr": (
            "Bonjour ! Je suis ConcussCare. Je réponds aux questions sur les commotions "
            "cérébrales pédiatriques à partir des lignes directrices évolutives. Que "
            "souhaitez-vous savoir ?"
        ),
    },
    "thanks": {
        "en": (
            "You're welcome! If you have any other questions about concussion, feel free to ask."
        ),
        "fr": (
            "Je vous en prie ! Si vous avez d'autres questions sur les commotions cérébrales, "
            "n'hésitez pas à les poser."
        ),
    },
    "farewell": {
        "en": "Take care! Come back any time you have a question about concussion.",
        "fr": (
            "Prenez soin de vous ! Revenez quand vous voulez si vous avez une question sur "
            "les commotions cérébrales."
        ),
    },
    "capability": {
        "en": (
            "I'm ConcussCare, an assistant for pediatric concussion care. I answer questions "
            "using the Living Guideline for Pediatric Concussion and the supporting research "
            "literature, with answers written for you as a {role}.\n\n"
            "You can ask me about things like:\n"
            "- Recognizing concussion and what warning signs need urgent care\n"
            "- Diagnosis and assessment\n"
            "- Symptom management and recovery\n"
            "- Return to school, learning, activity, and sport\n\n"
            "I'm not a substitute for medical advice, diagnosis, or treatment. If you need "
            "urgent care, call 911 or go to the nearest emergency department."
        ),
        "fr": (
            "Je suis ConcussCare, un assistant pour les soins liés aux commotions cérébrales "
            "pédiatriques. Je réponds aux questions à partir des lignes directrices évolutives "
            "sur les commotions cérébrales pédiatriques et de la littérature scientifique, avec "
            "des réponses adaptées à votre rôle de {role}.\n\n"
            "Vous pouvez me poser des questions sur :\n"
            "- La reconnaissance d'une commotion et les signes d'alerte nécessitant des soins urgents\n"
            "- Le diagnostic et l'évaluation\n"
            "- La gestion des symptômes et le rétablissement\n"
            "- Le retour à l'école, à l'apprentissage, à l'activité et au sport\n\n"
            "Je ne remplace pas un avis médical, un diagnostic ou un traitement. Si vous avez "
            "besoin de soins urgents, composez le 911 ou rendez-vous au service d'urgence le "
            "plus proche."
        ),
    },
}


def canned_reply(intent: str, lang: Optional[str], user_type: Optional[str] = None) -> Optional[str]:
    by_lang = CANNED_REPLIES.get(intent)
    if not by_lang:
        return None
    template = by_lang.get(lang if lang in ("en", "fr") else "en", by_lang["en"])
    return template.replace("{role}", _role_label(user_type, lang if lang in ("en", "fr") else "en"))


def generate_smalltalk_reply(
    message: str,
    user_type: Optional[str] = None,
    lang: Optional[str] = None,
) -> Optional[str]:
    """Answer a short non-clinical message with one cheap stateless completion.

    Returns ``None`` when the model escalates, errors, or comes back empty — the caller must
    then fall through to the full pipeline. No RAG, no assistant, no thread, no polling.
    """
    language_name = "French" if lang == "fr" else "English"
    prompt = f"""You are ConcussCare, an assistant that answers questions about pediatric concussion using the Living Guideline for Pediatric Concussion. You are talking to a {user_type or "patient"}.

The user said: "{message}"

Reply in {language_name}, in one or two short sentences. Choose exactly one behaviour:
- If this is conversational (a greeting, small talk, a pleasantry), reply warmly and briefly, then invite a concussion-related question. Do not give any medical information.
- If this is a question about some other topic, unrelated to concussion or health, say politely that you can only answer questions about concussion based on the living guideline recommendations.
- If this is actually a health, medical, or concussion question, reply with the single word {ESCALATE_SENTINEL} and nothing else.

Do not use headings, bullet points, or citations. Reply with the message text only."""

    try:
        raw = fuelix_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=SMALLTALK_MODEL,
            timeout_seconds=20,
        )
    except Exception:
        return None

    reply = (raw or "").strip()
    if not reply or ESCALATE_SENTINEL in reply.upper():
        return None
    return reply
