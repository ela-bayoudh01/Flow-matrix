// Miroir manuel de Services/matrix_engine.py::DIMENSIONS (backend/app/schemas.py n'expose
// pas ces libellés -- même convention que le reste du projet, cf. api/types.ts). Regroupées
// pour un sélecteur lisible, pas une liste alphabétique brute.
export interface MatrixDimensionMeta {
  key: string;
  label: string; // titre de page, ex. "Matrice Zone × Zone"
  rowField: string; // nom du champ Flow réel (ou dérivé) -- miroir de DIMENSIONS[key][0]
  colField: string; // idem, DIMENSIONS[key][1]
  rowLabel: string;
  colLabel: string;
  group: string;
}

// "ip" reste dans cette liste (support backend documenté, cf. matrix_engine.DIMENSIONS) mais
// n'est plus affichée dans le sélecteur -- trop creuse en pratique pour être exploitable sans
// filtrer énormément (cf. dimension_notice "volume élevé", docs/05-matrix-engine.md §10).
// Toujours accessible en appel direct à l'API (GET /api/matrix?dimension=ip) sans rien recoder
// si un jour utile en debug -- juste exclue de SELECTABLE_GROUPS ci-dessous.
export const MATRIX_DIMENSIONS: MatrixDimensionMeta[] = [
  { key: "zone", label: "Zone × Zone", rowField: "ingress_zone", colField: "egress_zone", rowLabel: "Zone source", colLabel: "Zone destination", group: "Vue par défaut" },
  { key: "source_zone", label: "Source × Zone destination", rowField: "source", colField: "egress_zone", rowLabel: "Source (site)", colLabel: "Zone destination", group: "Par site" },
  { key: "source_criticality", label: "Source × Criticité", rowField: "source", colField: "criticality_label", rowLabel: "Source (site)", colLabel: "Criticité", group: "Par site" },
  { key: "zone_application", label: "Zone × Application", rowField: "ingress_zone", colField: "application_protocol", rowLabel: "Zone", colLabel: "Application", group: "Par service et protocole" },
  { key: "zone_protocol", label: "Zone × Protocole", rowField: "ingress_zone", colField: "protocol", rowLabel: "Zone", colLabel: "Protocole", group: "Par service et protocole" },
  { key: "zone_port", label: "Zone × Port destination", rowField: "ingress_zone", colField: "dst_port", rowLabel: "Zone", colLabel: "Port destination", group: "Par service et protocole" },
  { key: "port_category_zone", label: "Catégorie de port × Zone", rowField: "port_category", colField: "ingress_zone", rowLabel: "Catégorie de port", colLabel: "Zone", group: "Par service et protocole" },
  { key: "zone_action", label: "Zone × Action", rowField: "ingress_zone", colField: "dominant_action", rowLabel: "Zone", colLabel: "Action", group: "Par posture de sécurité" },
  { key: "zone_rule", label: "Zone × Règle ACL", rowField: "ingress_zone", colField: "last_access_control_rule_name", rowLabel: "Zone", colLabel: "Règle ACL", group: "Par posture de sécurité" },
  { key: "zone_criticality", label: "Zone × Criticité", rowField: "ingress_zone", colField: "criticality_label", rowLabel: "Zone", colLabel: "Criticité", group: "Par posture de sécurité" },
  { key: "zone_validation", label: "Zone × Statut de validation", rowField: "ingress_zone", colField: "validation_status", rowLabel: "Zone", colLabel: "Statut de validation", group: "Par posture de sécurité" },
  { key: "direction_criticality", label: "Direction × Criticité", rowField: "direction", colField: "criticality_label", rowLabel: "Direction (rôle de zone)", colLabel: "Criticité", group: "Par posture de sécurité" },
  { key: "ip", label: "IP source × IP destination", rowField: "src_ip", colField: "dst_ip", rowLabel: "IP source", colLabel: "IP destination", group: "Détail IP à IP" },
  { key: "timeslot_zone", label: "Créneau horaire × Zone", rowField: "timeslot", colField: "ingress_zone", rowLabel: "Créneau horaire", colLabel: "Zone", group: "Temporel (bêta)" },
];

// Groupes affichés dans le sélecteur, dans cet ordre -- "Détail IP à IP" volontairement
// absent (cf. commentaire ci-dessus). Retirer un groupe ici masque ses dimensions de
// l'interface sans toucher à MATRIX_DIMENSIONS ni au backend.
export const SELECTABLE_GROUPS = [
  "Vue par défaut",
  "Par site",
  "Par service et protocole",
  "Par posture de sécurité",
  "Temporel (bêta)",
];

export const DEFAULT_MATRIX_DIMENSION = "zone";

export function matrixDimensionMeta(key: string): MatrixDimensionMeta {
  return MATRIX_DIMENSIONS.find((d) => d.key === key) ?? MATRIX_DIMENSIONS[0];
}

// --- Explication de "(Non renseigné)", contextuelle selon la dimension affichée ------------
// Demande explicite de Loulou : le Responsable Réseau doit comprendre cette catégorie sans
// avoir à demander, en particulier ne pas la confondre avec "Unknown" (zone_application),
// qui a un sens différent (application analysée mais non reconnue, pas une donnée absente).

const ZONE_EXPLANATION = "« (Non renseigné) » regroupe les flux dont la zone n'était pas indiquée dans le log d'origine.";
const APPLICATION_EXPLANATION =
  "« (Non renseigné) » regroupe les flux pour lesquels aucune application n'a pu être identifiée — souvent parce que " +
  "la connexion a été bloquée avant l'inspection applicative. À ne pas confondre avec « Unknown », qui signifie que " +
  "l'application a été analysée mais non reconnue.";
const GENERIC_EXPLANATION = "« (Non renseigné) » regroupe les flux dont cette information était absente du log d'origine.";

function fieldKind(field: string): "zone" | "application" | "generic" {
  if (field === "ingress_zone" || field === "egress_zone") return "zone";
  if (field === "application_protocol" || field === "web_application") return "application";
  return "generic";
}

export function unsetLabelExplanation(meta: MatrixDimensionMeta): string {
  const kinds = new Set([fieldKind(meta.rowField), fieldKind(meta.colField)]);
  const parts: string[] = [];
  if (kinds.has("zone")) parts.push(ZONE_EXPLANATION);
  if (kinds.has("application")) parts.push(APPLICATION_EXPLANATION);
  if (parts.length === 0) parts.push(GENERIC_EXPLANATION);
  return parts.join("\n\n");
}
