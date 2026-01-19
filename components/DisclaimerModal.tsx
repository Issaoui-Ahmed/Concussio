"use client";

import { useState } from "react";

export function DisclaimerModal() {
    const [isOpen, setIsOpen] = useState(true);

    const handleAccept = () => {
        setIsOpen(false);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
                <div className="p-6 overflow-y-auto">
                    <h2 className="text-xl font-bold mb-4 text-gray-900">Disclaimer</h2>
                    <div className="space-y-4 text-gray-700 text-sm leading-relaxed">
                        <p>
                            This chatbot is based on the Living Guideline for Pediatric
                            Concussion. It is intended to support information sharing for care
                            providers, families, and other interest holders involved in
                            pediatric concussion. It does not replace medical advice,
                            diagnosis, or treatment. It is not intended for self diagnosis.
                        </p>

                        <p className="font-semibold text-red-600">
                            If you need urgent medical care, call 911 or go to the nearest
                            emergency department.
                        </p>
                        <p>
                            The recommendations reflect the best available evidence at the
                            time of development. New evidence may change these
                            recommendations. Healthcare professionals should use their
                            clinical judgment and consider patient preferences and local
                            resources.
                        </p>
                        <p>
                            The Living Guideline for Pediatric Concussion team, funders,
                            contributors, and partners are not responsible for any harm or
                            loss resulting from the use or misuse of this chatbot.
                        </p>
                        <p>
                            Any adaptations must include the statement: “Adapted from the
                            Living Guideline for Pediatric Concussion,” with or without
                            permission, as applicable."
                        </p>
                    </div>
                </div>
                <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end">
                    <button
                        onClick={handleAccept}
                        className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                        I Understand
                    </button>
                </div>
            </div>
        </div>
    );
}
