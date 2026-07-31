"use client";

import React from "react";
import { useLocale } from "@/lib/i18n/LanguageProvider";
import { localizeLink } from "@/lib/i18n/resourceLinks";
import { useResourceMap } from "@/lib/i18n/resourceLinkStore";

type AnchorProps = React.ComponentPropsWithoutRef<"a">;

/**
 * Anchor renderer for assistant markdown.
 *
 * In French, a link whose English URL has a verified French equivalent is swapped for it —
 * href and, where an official French title exists, the visible text. A link with no French
 * equivalent keeps its English URL and renders as an ordinary link.
 *
 * In English this is a plain <a>; `localizeLink` returns the href untouched.
 */
export function ResourceLink({ href, children, ...rest }: AnchorProps) {
    const { locale } = useLocale();
    // Self-updating map from /api/resource-links, falling back to the bundled data.
    const resourceMap = useResourceMap();
    const link = localizeLink(href, locale, resourceMap);

    return (
        <a {...rest} href={link.href}>
            {link.title ?? children}
        </a>
    );
}
