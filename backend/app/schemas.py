"""Schémas Pydantic (I/O API)."""

from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ImportSummary(BaseModel):
    filename: str
    lines_read: int
    log_entries_created: int
    log_entries_skipped_duplicate: int
    parsing_errors: int
    flows_touched: int
    sources: list[str]
    new_sources: list[str]


class ImportLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    source: str
    imported_at: datetime
    lines_read: int
    log_entries_created: int
    log_entries_skipped_duplicate: int
    parsing_errors: int
    flows_touched: int


class ImportLogsResponse(BaseModel):
    items: list[ImportLogOut]
    total_count: int


class ImportLogErrorOut(BaseModel):
    """Détail d'une ligne en échec de parsing (2026-09-14, demande de l'encadrant) -- affiché
    derrière un clic sur le nombre d'erreurs de la page Import."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    line_number: int
    raw_line: str
    error_message: str


class ImportLogErrorsResponse(BaseModel):
    items: list[ImportLogErrorOut]


class QualificationRunSummary(BaseModel):
    """Résumé retourné après une exécution du Qualification Engine (POST /api/flows/qualify)."""

    total_qualified: int
    label_counts: dict[str, int]
    unclassified_zones: list[str]


class FlowOut(BaseModel):
    """Un Flow tel qu'affiché dans la table plate ou le détail d'une cellule de matrice --
    tous les champs demandés pour le panneau de détail (voir docs/00, décision 2026-08-11).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    src_ip: str
    dst_ip: str
    dst_port: Optional[int]
    protocol: str
    dominant_action: Optional[str]
    occurrence_count: int
    # Ajoutés le 2026-09-06 -- nécessaires pour ne jamais afficher "Mixed" tel quel côté
    # frontend (répartition chiffrée "18 Allow / 2 Block" à la place, cf. describeAction).
    allow_count: int
    block_count: int
    total_initiator_bytes: int
    total_responder_bytes: int
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    ingress_zone: Optional[str]
    egress_zone: Optional[str]
    application_protocol: Optional[str]
    web_application: Optional[str]
    last_access_control_rule_name: Optional[str]
    criticality_score: Optional[float]
    criticality_label: Optional[str]
    security_status: Optional[str]
    validation_status: str
    validated_by: Optional[str]
    validated_at: Optional[datetime]
    decided_action: Optional[str]

    # "Depuis la dernière clôture de cycle" (2026-09-06) -- distinct des champs lifetime
    # ci-dessus, jamais pollué par une occurrence contradictoire ancienne. Voir Flow.cycle_*.
    cycle_occurrence_count: int
    cycle_allow_count: int
    cycle_block_count: int
    cycle_dominant_action: Optional[str]
    cycle_total_initiator_bytes: int
    cycle_total_responder_bytes: int
    cycle_total_connection_duration: int


class FlowsSummary(BaseModel):
    """Résumé agrégé (mêmes filtres que la liste) -- affiché en haut du panneau de détail
    d'une cellule ou de la table plate."""

    total_flows: int
    allow_count: int
    block_count: int
    criticality_breakdown: dict[str, int]


class FlowsResponse(BaseModel):
    items: list[FlowOut]
    total_count: int
    summary: FlowsSummary


class MatrixCell(BaseModel):
    row: Optional[str]
    col: Optional[str]
    flow_count: int
    allow_count: int
    block_count: int
    total_bytes: int
    total_duration_seconds: int
    criticality_breakdown: dict[str, int]


class MatrixResponse(BaseModel):
    dimension: str
    cells: list[MatrixCell]
    dimension_notice: Optional[str] = None


class SourcesResponse(BaseModel):
    """Toutes les sources connues, indépendamment de l'activité du cycle courant -- voir
    flows_query.list_known_sources() (2026-09-12, bug réel corrigé)."""

    sources: list[str]


class SourceCoverageOut(BaseModel):
    """Période couverte par les Flow d'une source + date du dernier import -- voir
    flows_query.list_source_coverage() (2026-09-12, demande de l'encadrant). Réutilisé tel
    quel par le Dashboard (toutes les sources), la Matrice et la Table des flux (la source
    actuellement filtrée)."""

    source: str
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    last_imported_at: Optional[datetime]
    flow_count: int


class SourceCoverageResponse(BaseModel):
    items: list[SourceCoverageOut]


class ValidationUpdate(BaseModel):
    """Valider/Bloquer classique -- toujours immédiat, jamais de justification. Voir
    RuleChangeUpdate pour le bouton dédié "Changer la règle"."""

    status: str  # "approved" ou "blocked" -- voir main.py VALID_VALIDATION_STATUSES
    validated_by: Optional[str] = None


class RuleChangeUpdate(BaseModel):
    """Bouton dédié "Changer la règle" (2026-09-05) -- seul chemin qui fige une décision
    CIBLE explicite sur l'action (Flow.decided_action), toujours avec justification
    obligatoire (vérifiée côté serveur, jamais fait confiance au client seul) et une fiche
    PDF générée depuis la ligne d'historique produite. Distinct de ValidationUpdate."""

    target_action: str  # "Allow" ou "Block" -- voir main.py VALID_TARGET_ACTIONS
    # Optional au niveau du schéma pour que "absent" et "vide" donnent la même erreur 400
    # explicite côté serveur (main.py), plutôt qu'un 422 générique de validation Pydantic.
    justification: Optional[str] = None
    validated_by: Optional[str] = None


class RuleEnforcementClaimOut(BaseModel):
    """Suivi léger d'une réclamation "Règle non appliquée" (2026-09-10) -- voir
    models.py::RuleEnforcementClaim pour la distinction first_detected_at (posé
    automatiquement) vs last_claimed_at/claim_count (posés par "Déclarer la réclamation")."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    flow_id: int
    first_detected_at: datetime
    last_claimed_at: Optional[datetime]
    claim_count: int


class FlowHistoryEntryOut(BaseModel):
    """Une entrée de FlowValidationHistory, avec le contexte du Flow concerné inclus."""

    entry_type: Literal["flow"] = "flow"
    id: int
    created_at: datetime
    source: Optional[str]
    # Renommé depuis `validated_by` (2026-09-13, fusion avec NetworkPolicy dans l'Historique
    # des validations) -- unifie le nom de champ avec NetworkPolicyHistoryEntryOut.decided_by
    # ci-dessous (même idée -- qui a décidé -- deux noms de colonne différents en base).
    decided_by: Optional[str]
    justification: Optional[str]

    flow_id: int
    src_ip: str
    dst_ip: str
    dst_port: Optional[int]
    protocol: str
    old_status: Optional[str]
    new_status: str
    # Renseignés uniquement pour une entrée issue d'une inversion d'action (2026-09-03) --
    # None sur une entrée "classique" (Valider/Bloquer qui confirme l'observé).
    observed_action_before: Optional[str]
    decided_action: Optional[str]


class NetworkPolicyHistoryEntryOut(BaseModel):
    """Une entrée NetworkPolicy affichée dans l'Historique des validations (2026-09-13, demande
    de l'encadrant : une politique de sous-réseau est aussi une vraie décision à tracer, au même
    titre qu'un changement de règle sur un flux précis) -- mêmes champs que la fiche PDF déjà
    existante (build_network_policy_pdf), rien de nouveau, juste réutilisé ici."""

    entry_type: Literal["network_policy"] = "network_policy"
    id: int
    created_at: datetime
    source: Optional[str]
    decided_by: Optional[str]
    justification: str  # toujours renseignée (obligatoire à la création), contrairement au flux

    src_cidr: str
    destination: str
    protocol: Optional[str]
    dst_port: Optional[int]
    action: str  # "Allow" | "Block"


# Union discriminée sur `entry_type` (2026-09-13) -- pas une ligne "large" avec des champs
# Optional des deux côtés qui ne s'appliqueraient qu'à un seul type : chaque variante ne porte
# que ses propres champs réels, et se traduit naturellement en union discriminée TypeScript
# côté frontend (narrowing sur `entry.entry_type`, cf. HistoryPage.tsx).
ValidationHistoryEntryOut = Annotated[
    Union[FlowHistoryEntryOut, NetworkPolicyHistoryEntryOut], Field(discriminator="entry_type")
]


class LogEntryOut(BaseModel):
    """Une connexion individuelle sous-jacente à un Flow -- drill-down (2026-09-06, demande
    de l'encadrant) : occurrence_count agrège potentiellement des milliers de LogEntry,
    jamais consultables un par un jusqu'ici. Sous-ensemble des colonnes structurées de
    LogEntry pertinentes pour une lecture humaine ligne par ligne -- `raw_line`/`extra`
    (SSL*, DNS*, NAT_*...) restent en base, jamais supprimés, mais pas dans ce résumé (cf.
    docs/02, "rien n'est supprimé" -- juste pas tout ressaisi ici en V1)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_packet_at: Optional[datetime]
    access_control_rule_action: Optional[str]
    access_control_rule_name: Optional[str]
    src_port: Optional[int]
    initiator_bytes: Optional[int]
    responder_bytes: Optional[int]
    connection_duration: Optional[int]
    application_protocol: Optional[str]
    web_application: Optional[str]
    ingress_zone: Optional[str]
    egress_zone: Optional[str]


class LogEntriesResponse(BaseModel):
    items: list[LogEntryOut]
    total_count: int


class ValidationHistoryResponse(BaseModel):
    items: list[ValidationHistoryEntryOut]
    total_count: int


class RecommendationRunSummary(BaseModel):
    """Résumé retourné après une exécution du Recommendation Engine (POST /api/recommendations/run)."""

    total_findings: int
    findings_by_type: dict[str, int]
    created: int
    updated: int
    observation_window_days: Optional[float]
    obsolete_detection_enabled: bool


class RuleRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    finding_type: str
    rule_name: str
    ingress_zone: str
    egress_zone: str
    flow_count: int
    evidence: Optional[dict]
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class RuleRecommendationsResponse(BaseModel):
    items: list[RuleRecommendationOut]
    total_count: int


class RecommendationReview(BaseModel):
    status: str  # "acknowledged" ou "dismissed" -- voir main.py VALID_RECOMMENDATION_STATUSES
    reviewed_by: Optional[str] = None


class AclCreateDetail(BaseModel):
    """Pourquoi "create" vaut ce qu'il vaut -- pour que 0 ne ressemble jamais à un échec
    silencieux (cas réel, 2026-08-22 : 4 flux approuvés, 0 proposition, tous déjà couverts
    par une règle nommée -- correct, mais invisible sans creuser la base à la main)."""

    considered: int  # flux approuvés dans le périmètre (source + fenêtre de temps)
    eligible: int  # parmi eux, ceux réellement sous Default Action (alimentent "create")
    already_covered: int  # déjà régis par une règle explicite -- rien à créer pour eux


class AclProposalRunSummary(BaseModel):
    """Résumé retourné après une exécution de l'ACL Engine (POST /api/acl-proposals/run)."""

    total_proposals: int
    created: int
    updated: int
    by_intent: dict[str, int]
    create_detail: AclCreateDetail


class AclProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    intent: str
    ingress_zone: str
    egress_zone: str
    protocol: Optional[str]
    dst_port: Optional[int]
    src_networks: Optional[dict]
    dst_networks: Optional[dict]
    proposed_action: Optional[str]
    suggested_rule_name: Optional[str]
    target_rule_name: str
    source_recommendation_id: Optional[int]
    proposed_rule_text: Optional[str]
    rationale: Optional[dict]
    status: str
    validated_by: Optional[str]
    validated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AclProposalsResponse(BaseModel):
    items: list[AclProposalOut]
    total_count: int


class AclProposalReview(BaseModel):
    status: str  # "approved" ou "rejected" -- voir main.py VALID_ACL_PROPOSAL_STATUSES
    validated_by: Optional[str] = None


class AclProposalManualCreate(BaseModel):
    """Ajout manuel d'une proposition, pour un flux/équipement pas encore observé dans les
    logs -- exigence actée dès la conception initiale de l'ACL Engine. `justification` est
    obligatoire : sans Flow ni RuleRecommendation d'origine, c'est la seule preuve disponible.
    """

    source: Optional[str] = None
    ingress_zone: Optional[str] = None
    egress_zone: Optional[str] = None
    protocol: Optional[str] = None
    dst_port: Optional[int] = None
    src_networks: list[str] = []
    dst_networks: list[str] = []
    proposed_action: str
    suggested_rule_name: Optional[str] = None
    target_rule_name: Optional[str] = None
    justification: str
    created_by: Optional[str] = None


class AclProposalHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    acl_proposal_id: int
    old_status: Optional[str]
    new_status: str
    changed_by: Optional[str]
    created_at: datetime


class AclProposalHistoryResponse(BaseModel):
    items: list[AclProposalHistoryOut]
    total_count: int


class ValidationCycleOut(BaseModel):
    """Une clôture de cycle de validation ("Matrice Validée" figée à un instant t, pour une
    source précise -- un cycle ne mélange jamais deux sources)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    closed_by: Optional[str]
    closed_at: datetime
    flow_count: int
    note: Optional[str]


class ValidationCyclesResponse(BaseModel):
    items: list[ValidationCycleOut]
    total_count: int


class FlowDiffOut(BaseModel):
    """Un Flow avec son écart calculé par rapport à la dernière Matrice Validée."""

    flow: FlowOut
    diff_status: str  # "nouveau" | "disparu" | "modifie" | "conforme"
    diff_details: Optional[dict[str, dict]] = None  # {champ: {"avant": ..., "apres": ...}} -- "modifie" seulement


class FlowDiffSummary(BaseModel):
    nouveau: int
    disparu: int  # informationnel uniquement -- jamais compté dans pending_review_count
    # Décision explicite (Flow.decided_action) toujours pas honorée par le pare-feu observé
    # (2026-09-03) -- distinct de "modifie" (dérive organique, personne n'a rien décidé),
    # compte dans pending_review_count comme "nouveau"/"modifie".
    regle_non_appliquee: int
    modifie: int
    conforme: int
    pending_review_count: int  # écarts À TRAITER (nouveau/modifie/regle_non_appliquee) encore "pending"


class FlowDiffResponse(BaseModel):
    items: list[FlowDiffOut]
    total_count: int
    summary: FlowDiffSummary
    # Dernier cycle de chaque source présente dans `items` -- {} si aucune des sources
    # concernées n'a de baseline. Jamais un seul "cycle" global : un cycle est toujours
    # propre à une source (cf. ValidationCycle, révisé le 2026-08-21).
    cycles: dict[str, ValidationCycleOut]


class CellDiffOut(BaseModel):
    row: str
    col: str
    diff_summary: dict[str, int]


class CellDiffResponse(BaseModel):
    cycles: dict[str, ValidationCycleOut]
    cells: list[CellDiffOut]


# --- Rollup du diff par sous-réseau CIDR (2026-09-11) -- fusion de "Politiques de sous-réseau"
# dans le Cycle de validation, voir Services/validation_cycle_engine.py::compute_subnet_diff.

class SubnetDiffOut(BaseModel):
    cidr: str
    machine_count: int
    flow_count: int
    diff_summary: dict[str, int]


class SubnetDiffResponse(BaseModel):
    source: str
    prefix_length: int
    cycle: Optional[ValidationCycleOut]
    items: list[SubnetDiffOut]


class ValidatedMatrixResponse(BaseModel):
    """Matrice Validée -- reconstruite depuis les FlowSnapshot du dernier cycle clôturé
    d'une source, pas depuis les Flow en direct. Mêmes MatrixCell que GET /api/matrix, pour
    être affichée par le même composant frontend. `cycle=None` si aucun cycle n'a encore été
    clôturé pour cette source (matrice vide, pas une erreur)."""

    dimension: str
    cycle: Optional[ValidationCycleOut]
    cells: list[MatrixCell]


# --- Politiques de sous-réseau (2026-09-10) -- fonctionnalité isolée, voir models.py::NetworkPolicy


class SubnetObservationOut(BaseModel):
    """Un regroupement CIDR suggéré -- purement indicatif, cf. Services/subnet_observation.py."""

    cidr: str
    machine_count: int
    flow_count: int


class SubnetObservationsResponse(BaseModel):
    source: str
    prefix_length: int
    items: list[SubnetObservationOut]


class NetworkPolicyCreate(BaseModel):
    source: Optional[str] = None
    src_cidr: str
    destination: str
    protocol: Optional[str] = None
    dst_port: Optional[int] = None
    action: str  # "Allow" ou "Block" -- voir main.py VALID_TARGET_ACTIONS (réutilisé)
    justification: str
    decided_by: Optional[str] = None


class NetworkPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    src_cidr: str
    destination: str
    protocol: Optional[str]
    dst_port: Optional[int]
    action: str
    justification: str
    decided_by: Optional[str]
    created_at: datetime


class NetworkPoliciesResponse(BaseModel):
    items: list[NetworkPolicyOut]
    total_count: int
