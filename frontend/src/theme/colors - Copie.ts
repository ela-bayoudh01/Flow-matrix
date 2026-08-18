// Source unique des couleurs de statut/identité de toute l'application -- avant cette étape,
// CRITICALITY_COLORS/FINDING_TYPE_COLORS/INTENT_COLORS étaient dupliqués et réinventés dans
// 3 fichiers différents (MatrixGrid, RecommendationsTable, AclProposalsTable). Palette calée
// sur la méthode data-viz du projet (contraste + séparation daltonisme validés), pas choisie
// à l'œil. Deux familles distinctes, jamais interchangeables :
//   - STATUS  : une sévérité/un état (criticité, statut de validation) -- ordonné, réservé.
//   - IDENTITY : une catégorie sans ordre de gravité (type de finding, intent ACL).

export const STATUS_COLORS = {
  critical: "#d03b3b",
  serious: "#ec835a",
  warning: "#fab219",
  good: "#0ca30c",
  muted: "#898781",
} as const;

// Criticité d'un Flow : critical/high/medium/low -> mapping direct sur le statut.
export const CRITICALITY_COLORS: Record<string, string> = {
  critical: STATUS_COLORS.critical,
  high: STATUS_COLORS.serious,
  medium: STATUS_COLORS.warning,
  low: STATUS_COLORS.good,
};
export const CRITICALITY_ORDER = ["critical", "high", "medium", "low"];
export const NON_QUALIFIE_COLOR = STATUS_COLORS.muted;

export function criticalityColor(label: string | null | undefined): string {
  if (!label) return NON_QUALIFIE_COLOR;
  return CRITICALITY_COLORS[label] ?? NON_QUALIFIE_COLOR;
}

export function worstCriticality(breakdown: Record<string, number>): string | null {
  for (const label of CRITICALITY_ORDER) {
    if (breakdown[label] > 0) return label;
  }
  return null;
}

// Statut de validation (Flow) / revue (RuleRecommendation, AclProposal) : vocabulaire
// différent par entité (approved/blocked, acknowledged/dismissed, approved/rejected) mais
// même sens à 3 états -- positif / négatif / en attente -- donc même mapping de couleur.
export function validationStatusColor(status: string): string {
  if (status === "approved" || status === "acknowledged") return STATUS_COLORS.good;
  if (status === "blocked" || status === "rejected" || status === "dismissed") return STATUS_COLORS.critical;
  return STATUS_COLORS.muted; // pending
}

// Identité : finding_type (Recommendation Engine) et intent (ACL Engine) partagent les mêmes
// couleurs quand ils désignent la même origine ("tighten" vient de "trop_permissive", etc.)
// -- continuité visuelle voulue entre les pages Recommandations et Propositions ACL.
export const IDENTITY_COLORS = {
  blue: "#2a78d6",
  orange: "#eb6834",
  neutral: "#757575",
  violet: "#4a3aa7",
} as const;

export const FINDING_TYPE_COLORS: Record<string, string> = {
  sans_regle_explicite: IDENTITY_COLORS.blue,
  trop_permissive: IDENTITY_COLORS.orange,
  obsolete: IDENTITY_COLORS.neutral,
};
export const FINDING_TYPE_LABELS: Record<string, string> = {
  trop_permissive: "Trop permissive",
  obsolete: "Obsolète",
  sans_regle_explicite: "Sans règle explicite",
};

export const INTENT_COLORS: Record<string, string> = {
  create: IDENTITY_COLORS.blue,
  tighten: IDENTITY_COLORS.orange,
  revoke: IDENTITY_COLORS.neutral,
  manual: IDENTITY_COLORS.violet,
};
export const INTENT_LABELS: Record<string, string> = {
  create: "Créer",
  tighten: "Resserrer",
  revoke: "Retirer",
  manual: "Ajout manuel",
};

// Allow/Block/Mixed (dominant_action) -- même logique statut (bon/mauvais/mixte).
export const ACTION_COLORS: Record<string, string> = {
  Allow: STATUS_COLORS.good,
  Block: STATUS_COLORS.critical,
  Mixed: STATUS_COLORS.warning,
};
