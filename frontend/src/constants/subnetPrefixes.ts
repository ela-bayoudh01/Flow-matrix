// Granularité du regroupement CIDR suggéré (2026-09-10, demande de l'encadrant) -- réutilisée
// telle quelle par NetworkPoliciesPage.tsx et ValidationCyclePage.tsx (tableau des
// sous-réseaux observés) : une seule liste, jamais deux définitions susceptibles de diverger.
export const PREFIX_OPTIONS = [16, 20, 22, 24, 25, 26, 27, 28, 29, 30] as const;
export const DEFAULT_PREFIX_LENGTH = 24;
