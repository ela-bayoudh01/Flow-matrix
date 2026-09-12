// Types miroir des schémas Pydantic du backend (backend/app/schemas.py).
// Garder synchronisé manuellement -- pas de génération automatique en V1.

export interface ImportSummary {
  filename: string;
  lines_read: number;
  log_entries_created: number;
  log_entries_skipped_duplicate: number;
  parsing_errors: number;
  flows_touched: number;
  sources: string[];
  new_sources: string[];
}

// Historique des imports (2026-09-11, demande de l'encadrant) -- ImportLog, table d'audit en
// ajout seul (voir models.py backend), un enregistrement par import réussi, jamais modifié
// après coup. `source` : sources concaténées ("SITE-A, SITE-B") si un fichier en contenait
// plusieurs -- un fichier normal n'en a qu'une seule.
export interface ImportLogOut {
  id: number;
  filename: string;
  source: string;
  imported_at: string;
  lines_read: number;
  log_entries_created: number;
  log_entries_skipped_duplicate: number;
  parsing_errors: number;
  flows_touched: number;
}

export interface ImportLogsResponse {
  items: ImportLogOut[];
  total_count: number;
}

export interface FlowOut {
  id: number;
  source: string | null;
  src_ip: string;
  dst_ip: string;
  dst_port: number | null;
  protocol: string;
  dominant_action: string | null;
  occurrence_count: number;
  // Ajoutés le 2026-09-06 -- nécessaires pour ne jamais afficher "Mixed" tel quel (répartition
  // chiffrée "18 Allow / 2 Block" à la place, cf. describeAction dans theme/colors.ts).
  allow_count: number;
  block_count: number;
  total_initiator_bytes: number;
  total_responder_bytes: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  ingress_zone: string | null;
  egress_zone: string | null;
  application_protocol: string | null;
  web_application: string | null;
  last_access_control_rule_name: string | null;
  criticality_score: number | null;
  criticality_label: string | null;
  security_status: string | null;
  validation_status: string;
  validated_by: string | null;
  validated_at: string | null;
  decided_action: "Allow" | "Block" | null;

  // "Depuis la dernière clôture de cycle" (2026-09-06) -- distinct des champs lifetime
  // ci-dessus, jamais pollué par une occurrence contradictoire ancienne. Utilisé
  // spécifiquement par le Cycle de validation (FlowsTable avec showDiffColumn, cf.
  // describeAction ci-dessous) ; la Table des flux/Matrice Réelle gardent le lifetime.
  cycle_occurrence_count: number;
  cycle_allow_count: number;
  cycle_block_count: number;
  cycle_dominant_action: "Allow" | "Block" | "Mixed" | null;
  cycle_total_initiator_bytes: number;
  cycle_total_responder_bytes: number;
  cycle_total_connection_duration: number;
}

export interface FlowsSummary {
  total_flows: number;
  allow_count: number;
  block_count: number;
  criticality_breakdown: Record<string, number>;
}

export interface FlowsResponse {
  items: FlowOut[];
  total_count: number;
  summary: FlowsSummary;
}

// Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège potentiellement
// des milliers de connexions individuelles -- jamais consultables une par une jusqu'ici.
export interface LogEntryOut {
  id: number;
  first_packet_at: string | null;
  access_control_rule_action: string | null;
  access_control_rule_name: string | null;
  src_port: number | null;
  initiator_bytes: number | null;
  responder_bytes: number | null;
  connection_duration: number | null;
  application_protocol: string | null;
  web_application: string | null;
  ingress_zone: string | null;
  egress_zone: string | null;
}

export interface LogEntriesResponse {
  items: LogEntryOut[];
  total_count: number;
}

// Filtres communs à GET /api/flows et GET /api/matrix (backend/app/flow_filters.py --
// une seule définition partagée côté backend, on reflète la même liste ici).
export interface FlowFilterValues {
  source?: string;
  ingress_zone?: string;
  egress_zone?: string;
  src_ip?: string;
  dst_ip?: string;
  protocol?: string;
  dst_port?: number;
  dominant_action?: string;
  validation_status?: string;
  criticality_label?: string;
  application_protocol?: string;
  web_application?: string;
}

export interface FlowsFilters extends FlowFilterValues {
  limit?: number;
  offset?: number;
  // Drill-down d'une cellule de matrice, pour n'importe quelle dimension (pas seulement
  // "zone" -- ingress_zone/egress_zone ci-dessus restent utilisables séparément comme
  // filtre "normal", indépendamment d'un drill-down de cellule). Les trois vont ensemble.
  dimension?: string;
  row_value?: string;
  col_value?: string;
  // Recherche par mot-clé (demande de l'encadrant, 2026-08-25) -- volontairement PAS dans
  // FlowFilterValues : /api/matrix (agrégation) n'est pas une des listes de lignes visées.
  q?: string;
}

export interface MatrixCell {
  row: string | null;
  col: string | null;
  flow_count: number;
  allow_count: number;
  block_count: number;
  total_bytes: number;
  total_duration_seconds: number;
  criticality_breakdown: Record<string, number>;
}

export interface MatrixResponse {
  dimension: string;
  cells: MatrixCell[];
  dimension_notice: string | null;
}

// Bouton dédié "Changer la règle" (2026-09-05) -- seul chemin qui ouvre la fenêtre de
// confirmation + justification + fiche PDF, toujours, quel que soit l'état du flux. Valider/
// Bloquer restent un clic simple et immédiat, jamais conditionné à une détection de
// contradiction (décision de conception actée après un test réel où cette détection
// automatique ne déclenchait la fenêtre dans aucun cas concret).
export function invertedAction(flow: Pick<FlowOut, "dominant_action" | "decided_action">): "Allow" | "Block" {
  const current = flow.decided_action ?? flow.dominant_action;
  return current === "Block" ? "Allow" : "Block"; // défaut Block si Allow/Mixed/inconnu (moindre privilège)
}

export interface ValidationUpdate {
  status: "approved" | "blocked";
  validated_by?: string;
}

export interface RuleChangeUpdate {
  target_action: "Allow" | "Block";
  justification: string;
  validated_by?: string;
}

export interface ValidationHistoryOut {
  id: number;
  flow_id: number;
  source: string | null;
  src_ip: string;
  dst_ip: string;
  dst_port: number | null;
  protocol: string;
  old_status: string | null;
  new_status: string;
  validated_by: string | null;
  created_at: string;
  // Renseignés uniquement pour une entrée issue d'une inversion d'action -- None sur une
  // entrée "classique" (Valider/Bloquer qui confirme l'observé).
  justification: string | null;
  observed_action_before: string | null;
  decided_action: string | null;
}

export interface ValidationHistoryResponse {
  items: ValidationHistoryOut[];
  total_count: number;
}

// Miroir de RuleRecommendation (backend/app/models.py) -- findings du Recommendation Engine.
export interface RuleRecommendationOut {
  id: number;
  source: string | null;
  finding_type: "trop_permissive" | "obsolete" | "sans_regle_explicite";
  rule_name: string;
  ingress_zone: string;
  egress_zone: string;
  flow_count: number;
  evidence: Record<string, unknown> | null;
  status: "pending" | "acknowledged" | "dismissed";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleRecommendationsResponse {
  items: RuleRecommendationOut[];
  total_count: number;
}

export interface RecommendationFilters {
  status?: string;
  finding_type?: string;
  source?: string;
  q?: string; // recherche par mot-clé, demande de l'encadrant (2026-08-25)
}

export interface QualificationRunSummary {
  total_qualified: number;
  label_counts: Record<string, number>;
  unclassified_zones: string[];
}

export interface RecommendationRunSummary {
  total_findings: number;
  findings_by_type: Record<string, number>;
  created: number;
  updated: number;
  observation_window_days: number | null;
  obsolete_detection_enabled: boolean;
}

export interface RecommendationReview {
  status: "acknowledged" | "dismissed";
  reviewed_by?: string;
}

// Miroir de AclProposal (backend/app/models.py) -- propositions de l'ACL Engine.
export interface NetworkSummary {
  observed: string[];
  count: number;
  truncated: boolean;
}

export interface AclProposalOut {
  id: number;
  source: string | null;
  intent: "create" | "tighten" | "revoke" | "manual";
  ingress_zone: string;
  egress_zone: string;
  protocol: string | null;
  dst_port: number | null;
  src_networks: NetworkSummary | null;
  dst_networks: NetworkSummary | null;
  proposed_action: string | null;
  suggested_rule_name: string | null;
  target_rule_name: string;
  source_recommendation_id: number | null;
  proposed_rule_text: string | null;
  rationale: Record<string, unknown> | null;
  status: "pending" | "approved" | "rejected";
  validated_by: string | null;
  validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AclProposalsResponse {
  items: AclProposalOut[];
  total_count: number;
}

export interface AclProposalFilters {
  status?: string;
  intent?: string;
  source?: string;
  q?: string; // recherche par mot-clé, demande de l'encadrant (2026-08-25)
}

// Pourquoi "create" vaut ce qu'il vaut -- pour que 0 ne ressemble jamais à un échec
// silencieux (cas réel, 2026-08-22 : 4 flux approuvés, 0 proposition, tous déjà couverts par
// une règle nommée -- correct, mais invisible sans creuser la base à la main).
export interface AclCreateDetail {
  considered: number; // flux approuvés dans le périmètre (source + fenêtre de temps)
  eligible: number; // parmi eux, ceux réellement sous Default Action
  already_covered: number; // déjà régis par une règle explicite -- rien à créer pour eux
}

export interface AclProposalRunSummary {
  total_proposals: number;
  created: number;
  updated: number;
  by_intent: Record<string, number>;
  create_detail: AclCreateDetail;
}

export interface AclProposalReview {
  status: "approved" | "rejected";
  validated_by?: string;
}

export interface AclProposalManualCreate {
  source?: string;
  ingress_zone?: string;
  egress_zone?: string;
  protocol?: string;
  dst_port?: number;
  src_networks: string[];
  dst_networks: string[];
  proposed_action: string;
  suggested_rule_name?: string;
  target_rule_name?: string;
  justification: string;
  created_by?: string;
}

export interface AclProposalHistoryOut {
  id: number;
  acl_proposal_id: number;
  old_status: string | null;
  new_status: string;
  changed_by: string | null;
  created_at: string;
}

export interface AclProposalHistoryResponse {
  items: AclProposalHistoryOut[];
  total_count: number;
}

// Cycle de validation périodique (backend/app/models.py : ValidationCycle/FlowSnapshot).
// Un cycle est toujours propre à UNE source -- jamais deux firewalls mélangés (révisé le
// 2026-08-21 après retour de l'encadrant, cf. docs/13-cycle-de-validation.md).
export interface ValidationCycleOut {
  id: number;
  source: string;
  closed_by: string | null;
  closed_at: string;
  flow_count: number;
  note: string | null;
}

export interface ValidationCyclesResponse {
  items: ValidationCycleOut[];
  total_count: number;
}

// Suivi léger d'une réclamation "Règle non appliquée" (2026-09-10, demande de l'encadrant) --
// first_detected_at posé automatiquement (Services/validation_cycle_engine.py::
// _ensure_claims_detected), last_claimed_at/claim_count uniquement par un clic explicite
// "Déclarer la réclamation".
export interface RuleEnforcementClaimOut {
  id: number;
  flow_id: number;
  first_detected_at: string;
  last_claimed_at: string | null;
  claim_count: number;
}

export type DiffStatus = "nouveau" | "disparu" | "regle_non_appliquee" | "modifie" | "conforme";

export interface DiffFieldChange {
  avant: unknown;
  apres: unknown;
  // Renseignés uniquement pour le champ "cycle_dominant_action", et uniquement du côté
  // (avant et/ou après) qui vaut effectivement "Mixed" -- répartition chiffrée jamais le mot
  // brut, cf. describeAction ci-dessous.
  avant_allow?: number;
  avant_block?: number;
  apres_allow?: number;
  apres_block?: number;
}

export interface FlowDiffOut {
  flow: FlowOut;
  diff_status: DiffStatus;
  diff_details: Record<string, DiffFieldChange> | null;
}

export interface FlowDiffSummary {
  nouveau: number;
  disparu: number; // informationnel uniquement -- jamais un écart à traiter
  // Décision explicite (Flow.decided_action) toujours pas honorée par le pare-feu observé
  // (2026-09-03) -- écart prioritaire, distinct d'une simple dérive organique ("modifie").
  regle_non_appliquee: number;
  modifie: number;
  conforme: number;
  pending_review_count: number; // écarts À TRAITER (nouveau/modifie/regle_non_appliquee) encore "pending"
}

// nouveau + modifie + regle_non_appliquee -- la seule définition de "écart à traiter",
// jamais recalculée différemment ailleurs (cf. ECARTS_A_TRAITER côté backend,
// Services/validation_cycle_engine.py). Paramètre élargi à la forme structurelle minimale
// (pas FlowDiffSummary en dur) -- 2026-09-12, bug réel corrigé : MatrixGrid.tsx recalculait
// ce total lui-même en dur (nouveau + modifie + disparu, donc FAUX -- disparu ne compte
// jamais, regle_non_appliquee toujours omis), ce qui rendait le mode "Colorer par écart"
// pratiquement équivalent à "Colorer par nombre de flux". Réutilisée telle quelle par les
// deux (CellDiffOut.diff_summary a les mêmes clés, juste sans pending_review_count).
export function ecartsATraiter(summary: { nouveau: number; modifie: number; regle_non_appliquee: number }): number {
  return summary.nouveau + summary.modifie + summary.regle_non_appliquee;
}

export interface FlowDiffResponse {
  items: FlowDiffOut[];
  total_count: number;
  summary: FlowDiffSummary;
  // Dernier cycle de chaque source présente dans `items` -- {} si aucune baseline. Un cycle
  // est toujours propre à une source, jamais un seul "cycle" global.
  cycles: Record<string, ValidationCycleOut>;
}

export interface FlowDiffFilters extends FlowFilterValues {
  diff_status?: DiffStatus;
  limit?: number;
  offset?: number;
  q?: string; // recherche par mot-clé, demande de l'encadrant (2026-08-25)
  // Restreint aux Flow dont src_ip tombe dans ce CIDR (2026-09-11, fusion "Politiques de
  // sous-réseau" -> Cycle de validation) -- utilisé par le "+" d'une ligne de sous-réseau sur
  // ValidationCyclePage.tsx. Absent -> comportement inchangé (voir Services/
  // validation_cycle_engine.py::compute_diff).
  src_cidr?: string;
}

export interface CellDiffOut {
  row: string;
  col: string;
  diff_summary: Record<DiffStatus, number>;
}

export interface CellDiffResponse {
  cycles: Record<string, ValidationCycleOut>;
  cells: CellDiffOut[];
}

// Matrice Validée -- reconstruite depuis les FlowSnapshot figés du dernier cycle clôturé
// d'une source, pas depuis les Flow en direct (contrairement à MatrixResponse/MatrixCell,
// qu'elle réutilise telles quelles pour rester affichable par le même composant MatrixGrid).
export interface ValidatedMatrixResponse {
  dimension: string;
  cycle: ValidationCycleOut | null;
  cells: MatrixCell[];
}

// Rollup du diff de cycle par sous-réseau CIDR observé (2026-09-11, demande de l'encadrant --
// fusion de la page "Politiques de sous-réseau" dans le Cycle de validation) : même
// regroupement suggestif que SubnetObservationOut ci-dessous, avec en plus la répartition des
// écarts de ce cycle. Voir Services/validation_cycle_engine.py::compute_subnet_diff.
export interface SubnetDiffOut {
  cidr: string;
  machine_count: number;
  flow_count: number;
  diff_summary: Record<DiffStatus, number>;
}

export interface SubnetDiffResponse {
  source: string;
  prefix_length: number;
  cycle: ValidationCycleOut | null;
  items: SubnetDiffOut[];
}

// --- Politiques de sous-réseau (2026-09-10) -- fonctionnalité NOUVELLE et VOLONTAIREMENT
// ISOLÉE : aucun lien avec FlowOut.decided_action, DiffStatus, ou ValidationCycleOut ci-dessus.

// Un regroupement CIDR suggéré -- purement indicatif (backend/app/Services/
// subnet_observation.py) : le système ne peut pas connaître le vrai découpage réseau de
// Nouvelair à partir des seules IP des logs, juste un point de départ affinable.
export interface SubnetObservationOut {
  cidr: string;
  machine_count: number;
  flow_count: number;
}

export interface SubnetObservationsResponse {
  source: string;
  prefix_length: number;
  items: SubnetObservationOut[];
}

export interface NetworkPolicyCreate {
  source?: string;
  src_cidr: string;
  destination: string;
  protocol?: string;
  dst_port?: number;
  action: "Allow" | "Block";
  justification: string;
  decided_by?: string;
}

export interface NetworkPolicyOut {
  id: number;
  source: string | null;
  src_cidr: string;
  destination: string;
  protocol: string | null;
  dst_port: number | null;
  action: "Allow" | "Block";
  justification: string;
  decided_by: string | null;
  created_at: string;
}

export interface NetworkPoliciesResponse {
  items: NetworkPolicyOut[];
  total_count: number;
}
