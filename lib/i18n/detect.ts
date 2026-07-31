import type { Locale } from "./LanguageProvider";

// Client-side EN/FR detection. Runs on submit, before the request fires, so the chrome is
// already correct while the answer generates. No LLM call.
//
// Confidence gating is load-bearing: without it, short chit-chat ("ok", "merci", "thanks")
// flips the locale and silently undoes a toggle the user just set.

const FRENCH_STOPWORDS = new Set([
    "le", "la", "les", "un", "une", "des", "du", "de", "au", "aux", "ce", "cet", "cette", "ces",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "mon", "ma", "mes", "son",
    "sa", "ses", "leur", "leurs", "notre", "nos", "votre", "vos", "est", "sont", "etre", "avoir",
    "a", "ai", "as", "ont", "pour", "avec", "dans", "sur", "sans", "sous", "chez", "vers",
    "entre", "depuis", "que", "qui", "quoi", "dont", "quand", "comment", "pourquoi", "quel",
    "quelle", "quels", "quelles", "combien", "ne", "pas", "plus", "moins", "tres", "peut",
    "peux", "puis", "dois", "doit", "faire", "fait", "apres", "avant", "aussi", "meme", "donc",
    "mais", "ou", "et", "si", "y", "en", "ça", "cela", "tout", "toute", "tous", "toutes",
    "encore", "toujours", "jamais", "beaucoup", "trop", "bien",
]);

const ENGLISH_STOPWORDS = new Set([
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for", "with",
    "without", "from", "by", "about", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "can", "could", "should", "would", "will", "shall", "may",
    "might", "must", "i", "you", "he", "she", "we", "they", "it", "my", "your", "his", "her",
    "our", "their", "its", "what", "how", "why", "when", "where", "which", "who", "whom", "this",
    "that", "these", "those", "there", "then", "than", "not", "no", "yes", "after", "before",
    "also", "very", "more", "less", "much", "many", "some", "any",
]);

// Characters that essentially only appear in French here. A single one in a real word is a
// strong signal, so it is weighted heavily.
const FRENCH_DIACRITICS = /[àâäçéèêëîïôöùûüÿœæ]/i;

// Words that are common function words in BOTH languages ("a" is the English article and the
// French verb avoir; likewise "on", "si", "en"...). They carry no signal, so they must not
// vote — otherwise unaccented French like "Mon fils a mal a la tete" scores as English.
const AMBIGUOUS_WORDS = new Set(
    [...FRENCH_STOPWORDS].filter(word => ENGLISH_STOPWORDS.has(word))
);

export interface DetectionResult {
    lang: Locale;
    confident: boolean;
}

export function detectLanguage(text: string): DetectionResult {
    const normalized = (text || "").toLowerCase();
    const tokens = normalized.match(/[a-zàâäçéèêëîïôöùûüÿœæ']+/gi) ?? [];

    // Too short to judge. "ok", "merci", "thanks" land here on purpose.
    if (tokens.length < 3) {
        return { lang: "en", confident: false };
    }

    let frenchScore = 0;
    let englishScore = 0;

    for (const token of tokens) {
        if (FRENCH_DIACRITICS.test(token)) frenchScore += 3;
        if (AMBIGUOUS_WORDS.has(token)) continue;
        if (FRENCH_STOPWORDS.has(token)) frenchScore += 1;
        if (ENGLISH_STOPWORDS.has(token)) englishScore += 1;
    }

    const margin = Math.abs(frenchScore - englishScore);

    // Require both a winner and a clear margin. Medical vocabulary overlaps heavily between
    // the two languages ("concussion", "protocol", "symptomes"), so function words and
    // diacritics carry the signal, not content words.
    if (margin < 2) {
        return { lang: frenchScore > englishScore ? "fr" : "en", confident: false };
    }

    return {
        lang: frenchScore > englishScore ? "fr" : "en",
        confident: true,
    };
}
