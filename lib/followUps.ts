import type { UserType } from "./entryFlow";
import type { Locale } from "./i18n/LanguageProvider";
import { en } from "./i18n/en";
import { fr } from "./i18n/fr";

const DICTIONARIES = { en, fr };
const COMPREHENSION_USER_TYPES: ReadonlySet<UserType> = new Set([
    "Youth",
    "Parent or Caregiver",
    "Teacher",
    "Coach",
]);

export function normalizeFollowUps(items: string[], userType: UserType, lang: Locale): string[] {
    const dictionary = DICTIONARIES[lang];
    const firstFollowUp = COMPREHENSION_USER_TYPES.has(userType)
        ? dictionary["followUps.comprehension"]
        : null;
    const defaults = [
        firstFollowUp ?? dictionary["followUps.default.1"],
        dictionary["followUps.default.2"],
        dictionary["followUps.default.3"],
    ];
    const candidates = firstFollowUp ? [firstFollowUp, ...items] : items;
    const deduped = Array.from(new Set(candidates.map(item => item.trim()).filter(Boolean)));
    for (const fallback of defaults) {
        if (deduped.length >= 3) break;
        if (!deduped.includes(fallback)) deduped.push(fallback);
    }
    return deduped.slice(0, 3);
}

/** Keep the fixed copy exact when switching languages, without a model translation. */
export function localizeFixedFollowUp(question: string, locale: Locale): string | null {
    if (question === en["followUps.comprehension"] || question === fr["followUps.comprehension"]) {
        return DICTIONARIES[locale]["followUps.comprehension"];
    }
    return null;
}
