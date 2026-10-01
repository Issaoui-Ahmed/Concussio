"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n/LanguageProvider";
import { USER_TYPES, chooseUserType, type UserType } from "@/lib/entryFlow";
import { EntryDialog } from "./EntryDialog";

/**
 * Last entry step, after the disclaimer: the visitor picks the user group the chat opens set
 * to. Nothing is preselected, so the group is always a deliberate choice rather than a default
 * nobody noticed.
 */
export function UserTypeModal() {
    const t = useT();
    const [selected, setSelected] = useState<UserType | null>(null);

    return (
        <EntryDialog
            id="user-type"
            title={t("userTypePicker.title")}
            actionLabel={t("userTypePicker.start")}
            actionDisabled={selected === null}
            onAction={() => {
                if (selected) chooseUserType(selected);
            }}
        >
            <p id="user-type-intro">{t("userTypePicker.intro")}</p>
            <div role="radiogroup" aria-labelledby="user-type-title" aria-describedby="user-type-intro" className="grid gap-2 short:gap-1.5 sm:grid-cols-2">
                {USER_TYPES.map(value => (
                    <label
                        key={value}
                        className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 short:py-2 cursor-pointer transition-colors hover:border-[#00417d]/40 has-[:checked]:border-[#00417d] has-[:checked]:bg-[#00417d]/5 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500"
                    >
                        <input
                            type="radio"
                            name="user-type"
                            value={value}
                            checked={selected === value}
                            onChange={() => setSelected(value)}
                            className="h-4 w-4 shrink-0 accent-[#00417d]"
                        />
                        <span className="text-base font-medium text-gray-800">{t(`userType.${value}`)}</span>
                    </label>
                ))}
            </div>
        </EntryDialog>
    );
}
