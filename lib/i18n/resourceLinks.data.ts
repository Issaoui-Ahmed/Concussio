// GENERATED FILE - DO NOT EDIT.
//
// Rendered from data/resource-pairs.json by scripts/content_pipeline/render.py, which is
// itself a snapshot of the last good scrape of pedsconcussion.com. No URL below is written by
// hand. To pick up a listing change, re-scrape:
//     python -m scripts.content_pipeline.cli refresh
//
// This is the OFFLINE FALLBACK only. At runtime /api/resource-links re-derives the same map
// from the live listings, so what ships here matters just when that endpoint is unreachable.
//
// The resolution logic lives in ./resourceLinks.ts and is hand-written; only the data below
// is generated.


export interface FrenchResource {
    url: string;
    title?: string;
}

/** English URL -> verified French equivalent. */
export const RESOURCES: Record<string, FrenchResource> = {
    "https://pedsconcussion.com/tool-10-1post-concussion-vision-vestibular-and-oculomotor-disturbances-algorithm/": {
        url: "https://pedsconcussion.com/outil-10-1-algorithme-de-gestion-des-troubles-de-la-vision-des-troubles-vestibulaires-et-des-troubles-oculomoteurs/",
        title: "Algorithme de gestion des troubles de la vision, des troubles vestibulaires et des troubles oculomoteurs après une commotion cérébrale",
    },
    "https://pedsconcussion.com/tool-12-1-concussion-implications-and-interventions-for-the-classroom/": {
        url: "https://pedsconcussion.com/outil-12-1-repercussions-des-commotions-cerebrales-et-interventions-pour-la-salle-de-classe/",
        title: "Répercussions des commotions cérébrales et interventions pour la salle de classe",
    },
    "https://pedsconcussion.com/tool-6-1-post-concussion-headache-algorithm-3/": {
        url: "https://pedsconcussion.com/outil-6-1-algorithme-de-gestion-des-maux-de-tete-post-commotions-cerebrales/",
        title: "Algorithme de gestion des maux de tête post-commotions cérébrales",
    },
    "https://pedsconcussion.com/tool-7-1-prolonged-post-concussion-sleep-disturbances-algorithm/": {
        url: "https://pedsconcussion.com/outil-7-1-algorithme-de-gestion-pour-les-troubles-du-sommeil-postcommotion-prolonges/",
        title: "Algorithme de gestion pour les troubles du sommeil post-commotion prolongés",
    },
    "https://pedsconcussion.com/tool-8-1-post-concussion-mental-health-considerations-algorithm-3/": {
        url: "https://pedsconcussion.com/outil-8-1-algorithme-des-considerations-sur-lasante-mentale-apres-une-commotion-cerebrale/",
        title: "Algorithme des considérations sur la santé mentale après une commotion cérébrale",
    },
    "https://pedsconcussion.com/tool-8-2-2/": {
        url: "https://pedsconcussion.com/outil-8-2-algorithme-de-gestion-des-troubles-de-sante-mentale-prolonges/",
        title: "Algorithme de gestion des troubles de santé mentale prolongés",
    },
};

/** URLs already in French: prevents the UI marking a French document "(en anglais)". */
export const ALREADY_FRENCH: readonly string[] = [
    "http://WWW.pedsconcussion.com/reconnaissance/",
    "https://bjsm.bmj.com/content/57/11/692",
    "https://concussionsontario.org/",
    "https://hollandbloorview.ca/sites/default/files/2019-06/Concussion%20handbook%20French%20Jan%202016.pdf",
    "https://hopitaldemontrealpourenfants.ca/wp-content/uploads/2024/04/2023-09_pads-dischargeforms_web_fr.pdf",
    "https://montrealchildrenshospital.ca/wp-content/uploads/2024/04/2023-10-ConcussionKit-Brochure_EN_WEB.pdf?_gl=1*b3a059*_up*MQ..*_ga*NDAwODA4MjkzLjE3MzQwMTMwNDU.*_ga_L7P8T0X3YQ*MTczNDAxMzA0NS4xLjAuMTczNDAxMzA0NS4wLjAuMA..",
    "https://parachute.ca/en/injury-topic/concussion/",
    "https://parachute.ca/en/injury-topics/concussion-ed-app/",
    "https://parachute.ca/wp-content/uploads/2019/06/TestsPr%C3%A9Saison-FicheInformative-Parachute-UA.pdf",
    "https://parachute.ca/wp-content/uploads/2021/03/Fiche-dinformation-post-commotion-pour-les-enfants-de-Nunavut-Commotion-cerebrale-UA.pdf",
    "https://pedsconcussion.com/examen-virtuel-des-commotions-cerebrales-manuel-de-formation-telecharger/",
    "https://pedsconcussion.com/fiche-dinformation-post-commotion/",
    "https://pedsconcussion.com/fr/enseignants/",
    "https://pedsconcussion.com/fr/entraineur/",
    "https://pedsconcussion.com/fr/parents/",
    "https://pedsconcussion.com/outil-10-1-algorithme-de-gestion-des-troubles-de-la-vision-des-troubles-vestibulaires-et-des-troubles-oculomoteurs/",
    "https://pedsconcussion.com/outil-12-1-repercussions-des-commotions-cerebrales-et-interventions-pour-la-salle-de-classe/",
    "https://pedsconcussion.com/outil-6-1-algorithme-de-gestion-des-maux-de-tete-post-commotions-cerebrales/",
    "https://pedsconcussion.com/outil-7-1-algorithme-de-gestion-pour-les-troubles-du-sommeil-postcommotion-prolonges/",
    "https://pedsconcussion.com/outil-8-1-algorithme-des-considerations-sur-lasante-mentale-apres-une-commotion-cerebrale/",
    "https://pedsconcussion.com/outil-8-2-algorithme-de-gestion-des-troubles-de-sante-mentale-prolonges/",
    "https://pedsconcussion.com/retour-aux-activites-sport-lecole/",
    "https://pedsconcussion.com/scat-enfant-fr/",
    "https://pedsconcussion.com/scat-fr/",
    "https://pedsconcussion.com/scoat-fr/",
    "https://pedsconcussion.com/telemedecine-et-soins-virtuel/",
    "https://pedsconcussion.com/wp-content/uploads/Outil-1.3-Algorithme-de-gestion-des-symptomes-de-commotion-cerebrale-aigue-et-prolongee-1.pdf",
    "https://resources.cattonline.com/files/retour-a-lactivite-french-return-to-activity",
    "https://resources.cattonline.com/files/retour-a-lecole-return-to-school-french-ver",
    "https://resources.cattonline.com/files/retour-au-travail-french-return-to-work",
    "https://www.cdc.gov/traumatic-brain-injury/media/pdfs/2018-cdc_mtbi_discharge-instructions-508.pdf?CDC_AAref_Val=https://www.cdc.gov/traumaticbraininjury/pdf/pediatricmtbiguidelineeducationaltools/2018-CDC_mTBI_Discharge-Instructions-508.pdf",
    "https://www.cheo.on.ca/en/resources-and-support/resources/P5643F.pdf",
    "https://www.childrenshospital.org/sites/default/files/media_migration/5e066fcf-202f-45f0-b945-f392aa0a61d7.pdf",
    "https://www.childrenshospital.org/~/media/centers-and-services/programs/f_n/headache-program/chb_my_headache_diary(1).ashx?la=en",
    "https://www.inesss.qc.ca/fileadmin/doc/INESSS/Rapports/Traumatologie/INESSS_Depliant_TCCL_INESSS.pdf",
];
