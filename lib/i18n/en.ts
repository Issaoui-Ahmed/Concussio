// English is the source of truth for the key set. `fr.ts` is typed as
// Record<TranslationKey, string>, so a missing French string is a compile error rather than a
// silent fallback to the key name.
export const en = {
    // Document-level. Applied to <title> and <meta name="description"> by LanguageProvider,
    // because `metadata` in app/layout.tsx is resolved on the server, where the locale (which
    // lives in sessionStorage) is not knowable.
    "meta.title": "ConcussCare",
    "meta.description": "Concussion healthcare assistant",

    "nav.chatbot": "Chatbot",
    "nav.about": "About us",
    "nav.sources": "Source of information",
    "nav.logo": "/logo.png",
    "nav.logoAlt": "ConcussCare Logo",
    "nav.languageLabel": "Language",

    "sidebar.newChat": "New chat",
    "sidebar.yourConversations": "Your conversations",
    "sidebar.noConversations": "No conversations yet.",
    "sidebar.deleteChat": "Delete conversation",
    // Labels for the drawer that replaces the sidebar below md.
    "sidebar.open": "Open conversations",
    "sidebar.close": "Close conversations",

    "chat.welcomeTitle": "ConcussCare",
    "chat.welcomeTagline":
        "Your trusted assistant for concussion healthcare guidelines and patient support.",
    "chat.thinking": "Thinking... {seconds}s",
    "chat.inputPlaceholder": "Message as {userType}...",
    "chat.send": "Send",
    "chat.errorGeneric": "Sorry, an error occurred.",

    "userType.Healthcare Professional": "Healthcare Professional",
    "userType.Parent or Caregiver": "Parent or Caregiver",
    "userType.Youth": "Youth",
    "userType.Teacher": "Teacher",
    "userType.Coach": "Coach",

    "message.you": "You",
    "message.assistant": "ConcussCare",
    "message.translating": "Translating…",
    "message.askFollowUp": "Ask a follow up",

    "followUps.default.1": "Can you explain that in simpler terms?",
    "followUps.default.2": "What should I do first?",
    "followUps.default.3": "What warning signs mean I should seek urgent care?",

    // The three screens a visitor passes through, in order: password gate, demo notice,
    // disclaimer.
    "gate.title": "Password Required",
    "gate.intro":
        "This prototype of the Pediatric Concussion Chatbot is open for testing by invitation only. Enter the password you were given to continue.",
    "gate.passwordLabel": "Password",
    "gate.submit": "Continue",
    "gate.checking": "Checking…",
    "gate.incorrect": "Incorrect password. Please try again.",
    "gate.unconfigured":
        "No password is configured on the server, so the chatbot cannot be unlocked. Set DEMO_PASSWORD in the deployment environment and redeploy.",

    // The second gate, /admin only. Kept in the dictionaries like everything else even though
    // admin mounts no LanguageProvider and therefore always renders the English side.
    "adminGate.title": "Admin Password Required",
    "adminGate.intro":
        "The admin tools rerun the content pipeline and edit the Fuel IX resources behind the chatbot. They ask for their own password, separate from the one that opened the prototype.",
    "adminGate.passwordLabel": "Admin password",
    "adminGate.unconfigured":
        "No admin password is configured on the server, so the admin tools cannot be unlocked. Set ADMIN_PASSWORD in the deployment environment and redeploy.",

    "demo.title": "Demo/Testing Version",
    "demo.p1":
        "You are about to use a prototype of the Pediatric Concussion Chatbot for testing and evaluation purposes.",
    "demo.p2": "Please keep this link and the password confidential.",
    "demo.p3":
        "Please do not enter any personal or identifying information, including real names, addresses, schools, teams, healthcare providers, or other information that could identify you or another person. Please use fictional examples if needed.",
    "demo.p4":
        "The chatbot is being evaluated and its responses may be incomplete or incorrect. It is intended for testing only and is not a substitute for medical care, diagnosis, or advice from a healthcare professional.",
    "demo.p5":
        "By continuing, you acknowledge that you are entering a demo/testing version of the chatbot.",
    "demo.continue": "Continue to Disclaimer",

    "disclaimer.title": "Disclaimer",
    "disclaimer.p1":
        "This chatbot is based on the Living Guideline for Pediatric Concussion. It is intended to support information sharing for care providers, families, and other interest holders involved in pediatric concussion. It does not replace medical advice, diagnosis, or treatment. It is not intended for self diagnosis.",
    "disclaimer.p2":
        "If you need urgent medical care, call 911 or go to the nearest emergency department.",
    "disclaimer.p3":
        "The recommendations reflect the best available evidence at the time of development. New evidence may change these recommendations. Healthcare professionals should use their clinical judgment and consider patient preferences and local resources.",
    "disclaimer.p4":
        "The Living Guideline for Pediatric Concussion team, funders, contributors, and partners are not responsible for any harm or loss resulting from the use or misuse of this chatbot.",
    "disclaimer.p5":
        "Any adaptations must include the statement: “Adapted from the Living Guideline for Pediatric Concussion,” with or without permission, as applicable.",
    "disclaimer.accept": "I Understand",

    "about.title": "About Us",
    "about.p1":
        "Welcome to ConcussCare, your trusted assistant for concussion healthcare guidelines and patient support.",
    "about.p1.brand": "ConcussCare",
    "about.p2":
        "Our mission is to bridge the gap between complex medical guidelines and accessible, actionable advice for healthcare professionals, parents, teachers, and coaches. We leverage advanced AI to provide immediate, reliable answers based on the latest pediatric concussion standards.",
    "about.p3":
        "ConcussCare is designed to help you navigate the recovery process with confidence, ensuring that every decision is informed by verified medical protocols.",

    "sources.title": "Source of Information",
    "sources.intro":
        "The information provided by ConcussCare is grounded in the latest clinical research and standardized guidelines for pediatric concussion management.",
    "sources.primaryHeading": "Primary Sources",
    "sources.item1.label": "Living Guideline for Pediatric Concussion Care:",
    "sources.item1.body":
        "Our system is primarily trained on the comprehensive PedsConcussion guidelines, ensuring adherence to the most current evidence-based practices.",
    "sources.item2.label": "Verified Medical Literature:",
    "sources.item2.body":
        "We continuously update our knowledge base with peer-reviewed studies and consensus statements from leading sports medicine and neurology organizations.",
    "sources.disclaimerLabel": "Disclaimer:",
    "sources.disclaimerBody":
        "While ConcussCare provides guidance based on established medical protocols, it is not a substitute for professional medical diagnosis or treatment. Always consult with a qualified healthcare provider for individual medical advice.",
} as const;

export type TranslationKey = keyof typeof en;
