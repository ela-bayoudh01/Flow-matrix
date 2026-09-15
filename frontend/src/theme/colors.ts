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

// Traduction affichage (2026-09-13, demande de l'encadrant -- "la plateforme doit être
// entièrement en français") : low/medium/high/critical restent les identifiants techniques
// EXACTS partout ailleurs (clé de CRITICALITY_COLORS ci-dessus, valeur de filtre envoyée à
// l'API, criticality_label en base) -- seule cette table d'affichage traduit le mot montré à
// l'écran, jamais la valeur elle-même (changer la valeur casserait les filtres et les
// couleurs conditionnelles qui s'appuient dessus). Terminologie standard cybersécurité,
// chaînée dans displayAxisLabel ci-dessous -- une seule fonction d'affichage pour
// Action/Statut/Criticité, jamais une 4ᵉ définition séparée.
export const CRITICALITY_LABELS: Record<string, string> = {
  low: "Faible",
  medium: "Moyenne",
  high: "Élevée",
  critical: "Critique",
  // Pas une vraie valeur de criticality_label (NULL en base, cf. FilterBar.tsx) -- "clé"
  // synthétique utilisée par les répartitions par criticité (FlowsSummary.criticality_breakdown
  // ct.) pour désigner les flux jamais qualifiés. Traduite ici pour rester cohérente partout
  // où elle apparaît à côté des 4 vraies valeurs (mêmes composants, même table de recherche).
  non_qualifie: "Non qualifié",
};

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

// Traduction affichage des mêmes statuts bruts (2026-09-12, demande de l'encadrant après
// démo -- "la plateforme doit être entièrement en français") -- une seule table, réutilisée
// partout où un de ces statuts est affiché tel quel (FlowsTable.tsx, FlowDiffDetailDrawer.tsx,
// AclProposalsTable.tsx, RecommendationsTable.tsx, filtres...), même principe que
// validationStatusColor ci-dessus (couleur par sens, pas par mot). Les 3 vocabulaires ne se
// chevauchent jamais en valeur ("approved" existe pour Flow ET AclProposal, mais désigne la
// même idée dans les deux cas) -- une seule table plate suffit, jamais 3 tables redondantes.
export const STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  approved: "Approuvé",
  blocked: "Bloqué",
  acknowledged: "Traité",
  dismissed: "Rejeté",
  rejected: "Rejeté",
};

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

// Traduction affichage de la valeur brute stockée (Flow.dominant_action/decided_action,
// NetworkPolicy.action...) -- jamais la valeur elle-même, toujours "Allow"/"Block" en base et
// dans l'API (2026-09-12, "la plateforme doit être entièrement en français"). Même principe
// que STATUS_LABELS ci-dessus : une seule table, réutilisée partout (describeAction,
// displayAxisLabel, et les rares endroits qui affichent l'action sans passer par ces deux
// fonctions -- ValidationCyclePage.tsx/NetworkPoliciesPage.tsx, tables de politiques).
export const ACTION_LABELS: Record<string, string> = {
  Allow: "Autorisé",
  Block: "Bloqué",
};

// "Mixed" est un terme de debug interne, jamais présentable tel quel (demande de
// l'encadrant, 2026-09-06) -- même après avoir restreint le calcul au cycle en cours
// (cf. FlowOut.cycle_dominant_action), un flux peut légitimement avoir plusieurs actions
// dans la même fenêtre. Remplacé par une répartition chiffrée ("18 Autorisé / 2 Bloqué"),
// jamais le mot brut -- partout où une action de flux est affichée (ActionChip, panneaux de
// détail, fiche de changement de règle).
export interface ActionDisplay {
  label: string;
  color: string;
}

export function describeAction(action: string | null, allowCount: number, blockCount: number): ActionDisplay {
  if (action !== "Mixed") {
    return { label: action ? (ACTION_LABELS[action] ?? action) : "—", color: ACTION_COLORS[action ?? ""] ?? STATUS_COLORS.muted };
  }
  return { label: `${allowCount} ${ACTION_LABELS.Allow} / ${blockCount} ${ACTION_LABELS.Block}`, color: ACTION_COLORS.Mixed };
}

// Même principe que describeAction ci-dessus, appliqué à un libellé d'axe de matrice (ex.
// l'en-tête de colonne "Mixed" sur la dimension "Zone × Action") -- pas de répartition
// chiffrée disponible à cet endroit (juste un nom de colonne), donc un libellé neutre. Sert
// aussi de traduction générique pour les autres colonnes/valeurs textuelles (statuts de
// validation sur "Zone × Statut de validation" par exemple) -- STATUS_LABELS en filet, jamais
// une 3ᵉ table de correspondance.
export function displayAxisLabel(label: string): string {
  if (label === "Mixed") return "Trafic partagé";
  return ACTION_LABELS[label] ?? STATUS_LABELS[label] ?? CRITICALITY_LABELS[label] ?? label;
}

// Écart d'un Flow par rapport à la dernière Matrice Validée (Cycle de validation) --
// conforme = rien à faire (bon), nouveau/modifie = à revoir (attention croissante),
// regle_non_appliquee = une décision humaine déjà prise, toujours pas honorée par le
// pare-feu (2026-09-03, priorité maximale : plus urgent qu'un simple "modifie", puisque
// quelqu'un a déjà décidé et attend), disparu = juste informationnel (plus revu depuis la
// baseline, pas une alerte en soi).
export const DIFF_STATUS_COLORS: Record<string, string> = {
  conforme: STATUS_COLORS.good,
  nouveau: STATUS_COLORS.warning,
  modifie: STATUS_COLORS.serious,
  regle_non_appliquee: STATUS_COLORS.critical,
  disparu: STATUS_COLORS.muted,
};
export const DIFF_STATUS_LABELS: Record<string, string> = {
  conforme: "Conforme",
  nouveau: "Nouveau",
  modifie: "Modifié",
  regle_non_appliquee: "Règle non appliquée",
  disparu: "Disparu",
};

// Libellés lisibles des champs comparés par le Cycle de validation (Services/
// validation_cycle_engine.py::STRUCTURAL_FIELDS) -- une seule source pour la colonne "Écart"
// de FlowsTable et le panneau de détail FlowDiffDetailDrawer.
export const DIFF_FIELD_LABELS: Record<string, string> = {
  // "cycle_dominant_action" (pas "dominant_action") depuis le 2026-09-06 -- la comparaison
  // du diff porte sur l'action DE CE CYCLE (voir Services/validation_cycle_engine.py::
  // STRUCTURAL_FIELDS), jamais le cumul lifetime. Bug réel signalé le 2026-09-06 : ce mapping
  // n'avait pas suivi le renommage, le panneau affichait le nom de champ brut au lieu d'un
  // libellé humain.
  cycle_dominant_action: "Action",
  ingress_zone: "Zone source",
  egress_zone: "Zone destination",
  last_access_control_rule_name: "Règle ACL",
  criticality_label: "Criticité",
  decided_action: "Action décidée",
};

// Ordre de "pire écart présent" dans une cellule de matrice (mode de coloration Écart) --
// même principe que worstCriticality ci-dessus : regle_non_appliquee/modifie/nouveau sont ce
// qui demande une action (une décision non honorée passe avant une simple dérive), disparu
// reste informationnel, conforme est la situation attendue.
export const DIFF_STATUS_ORDER = ["regle_non_appliquee", "modifie", "nouveau", "disparu", "conforme"];

export function worstDiffStatus(summary: Record<string, number> | undefined): string | null {
  if (!summary) return null;
  for (const status of DIFF_STATUS_ORDER) {
    if (summary[status] > 0) return status;
  }
  return null;
}
