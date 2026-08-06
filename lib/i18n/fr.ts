import type { TranslationKey } from "./en";

// Typed as Record<TranslationKey, string>: omitting a key is a compile error.
export const fr: Record<TranslationKey, string> = {
    // The brand name is not translated, so "meta.title" matches the English — same convention
    // as "chat.welcomeTitle" and "message.assistant".
    "meta.title": "ConcussCare",
    "meta.description": "Assistant en soins des commotions cérébrales",

    "nav.chatbot": "Robot conversationnel",
    "nav.about": "À propos",
    "nav.sources": "Sources d'information",
    "nav.logo": "/logo-fr.png",
    "nav.logoAlt": "Logo ConcussCare",
    "nav.languageLabel": "Langue",

    "sidebar.newChat": "Nouvelle conversation",
    "sidebar.yourConversations": "Vos conversations",
    "sidebar.noConversations": "Aucune conversation pour l'instant.",
    "sidebar.deleteChat": "Supprimer la conversation",

    "chat.welcomeTitle": "ConcussCare",
    "chat.welcomeTagline":
        "Votre assistant de confiance pour les lignes directrices sur les commotions cérébrales et le soutien aux patients.",
    "chat.thinking": "Réflexion en cours... {seconds} s",
    "chat.inputPlaceholder": "Écrire en tant que {userType}...",
    "chat.send": "Envoyer",
    "chat.errorGeneric": "Désolé, une erreur est survenue.",

    "userType.Healthcare Professional": "Professionnel de la santé",
    "userType.Parent or Caregiver": "Parent ou proche aidant",
    "userType.Youth": "Jeune",
    "userType.Teacher": "Enseignant",
    "userType.Coach": "Entraîneur",

    "message.you": "Vous",
    "message.assistant": "ConcussCare",
    "message.translating": "Traduction en cours…",
    "message.askFollowUp": "Poser une question complémentaire",

    "followUps.default.1": "Pouvez-vous expliquer cela plus simplement ?",
    "followUps.default.2": "Que dois-je faire en premier ?",
    "followUps.default.3": "Quels signes d'alerte doivent m'amener à consulter d'urgence ?",

    "disclaimer.title": "Avis de non-responsabilité",
    "disclaimer.p1":
        "Ce robot conversationnel s'appuie sur les lignes directrices évolutives sur les commotions cérébrales pédiatriques. Il vise à faciliter le partage d'information auprès des professionnels de la santé, des familles et des autres parties prenantes concernées par les commotions cérébrales pédiatriques. Il ne remplace pas un avis médical, un diagnostic ou un traitement. Il n'est pas destiné à l'autodiagnostic.",
    "disclaimer.p2":
        "Si vous avez besoin de soins médicaux urgents, composez le 911 ou rendez-vous au service d'urgence le plus proche.",
    "disclaimer.p3":
        "Les recommandations reflètent les meilleures données probantes disponibles au moment de leur élaboration. De nouvelles données peuvent les modifier. Les professionnels de la santé doivent exercer leur jugement clinique et tenir compte des préférences du patient ainsi que des ressources locales.",
    "disclaimer.p4":
        "L'équipe des lignes directrices évolutives sur les commotions cérébrales pédiatriques, les bailleurs de fonds, les collaborateurs et les partenaires ne peuvent être tenus responsables de tout préjudice ou de toute perte découlant de l'utilisation ou de la mauvaise utilisation de ce robot conversationnel.",
    "disclaimer.p5":
        "Toute adaptation doit comporter la mention : « Adapté des lignes directrices évolutives sur les commotions cérébrales pédiatriques », avec ou sans autorisation, selon le cas.",
    "disclaimer.accept": "J'ai compris",

    "about.title": "À propos de nous",
    "about.p1":
        "Bienvenue sur ConcussCare, votre assistant de confiance pour les lignes directrices sur les commotions cérébrales et le soutien aux patients.",
    "about.p1.brand": "ConcussCare",
    "about.p2":
        "Notre mission est de combler l'écart entre des lignes directrices médicales complexes et des conseils accessibles et concrets destinés aux professionnels de la santé, aux parents, aux enseignants et aux entraîneurs. Nous utilisons l'intelligence artificielle pour fournir des réponses immédiates et fiables, fondées sur les normes les plus récentes en matière de commotions cérébrales pédiatriques.",
    "about.p3":
        "ConcussCare est conçu pour vous aider à traverser le processus de rétablissement en toute confiance, en veillant à ce que chaque décision s'appuie sur des protocoles médicaux vérifiés.",

    "sources.title": "Sources d'information",
    "sources.intro":
        "L'information fournie par ConcussCare repose sur les recherches cliniques les plus récentes et sur des lignes directrices normalisées pour la prise en charge des commotions cérébrales pédiatriques.",
    "sources.primaryHeading": "Sources principales",
    "sources.item1.label":
        "Lignes directrices évolutives sur les commotions cérébrales pédiatriques :",
    "sources.item1.body":
        "Notre système s'appuie principalement sur l'ensemble des lignes directrices PedsConcussion, ce qui garantit le respect des pratiques fondées sur les données probantes les plus récentes.",
    "sources.item2.label": "Littérature médicale vérifiée :",
    "sources.item2.body":
        "Nous mettons continuellement à jour notre base de connaissances avec des études évaluées par les pairs et des énoncés de consensus provenant d'organisations de premier plan en médecine du sport et en neurologie.",
    "sources.disclaimerLabel": "Avis de non-responsabilité :",
    "sources.disclaimerBody":
        "Bien que ConcussCare fournisse des conseils fondés sur des protocoles médicaux reconnus, il ne remplace pas un diagnostic ou un traitement médical professionnel. Consultez toujours un professionnel de la santé qualifié pour obtenir un avis médical personnalisé.",
};
