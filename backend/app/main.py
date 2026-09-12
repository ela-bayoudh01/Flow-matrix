from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (enregistre les modèles auprès de Base.metadata)
from .acl_proposal_history_query import DEFAULT_LIMIT as ACL_PROPOSAL_HISTORY_DEFAULT_LIMIT
from .acl_proposal_history_query import list_acl_proposal_history
from .fiche_pdf import build_action_change_pdf, build_cycle_report_pdf, build_network_policy_pdf, build_rule_not_enforced_pdf
from .acl_proposal_review import apply_acl_proposal_review
from .acl_proposals_query import DEFAULT_LIMIT as ACL_PROPOSALS_DEFAULT_LIMIT
from .acl_proposals_query import list_acl_proposals
from .database import Base, engine, get_db
from .flow_filters import flow_filter_params
from .flow_validation import apply_rule_change, apply_validation
from .flows_query import DEFAULT_LIMIT, list_flows
from .ingestion import import_log_file
from .log_entries_query import DEFAULT_LIMIT as LOG_ENTRIES_DEFAULT_LIMIT
from .log_entries_query import list_log_entries_for_flow
from .models import AclProposal, Flow, FlowSnapshot, FlowValidationHistory, NetworkPolicy, RuleEnforcementClaim, RuleRecommendation, ValidationCycle
from .recommendations_query import DEFAULT_LIMIT as RECOMMENDATIONS_DEFAULT_LIMIT
from .recommendations_query import list_recommendations
from . import import_log
from . import network_policies
from . import rule_enforcement_claims
from .schemas import (
    AclProposalHistoryResponse,
    AclProposalManualCreate,
    AclProposalOut,
    AclProposalReview,
    AclProposalRunSummary,
    AclProposalsResponse,
    CellDiffResponse,
    FlowDiffResponse,
    FlowOut,
    FlowsResponse,
    ImportLogsResponse,
    ImportSummary,
    LogEntriesResponse,
    MatrixResponse,
    NetworkPoliciesResponse,
    NetworkPolicyCreate,
    NetworkPolicyOut,
    QualificationRunSummary,
    RecommendationReview,
    RecommendationRunSummary,
    RuleChangeUpdate,
    RuleEnforcementClaimOut,
    RuleRecommendationOut,
    RuleRecommendationsResponse,
    SubnetDiffResponse,
    SubnetObservationsResponse,
    ValidatedMatrixResponse,
    ValidationCycleOut,
    ValidationCyclesResponse,
    ValidationHistoryResponse,
    ValidationUpdate,
)
from .Services import acl_engine, matrix_engine, qualification_engine, recommendation_engine, subnet_observation, validation_cycle_engine
from .time_utils import utcnow
from .validation_cycle_query import DEFAULT_LIMIT as VALIDATION_CYCLE_DIFF_DEFAULT_LIMIT
from .validation_cycle_query import list_flows_with_diff
from .validation_history_query import DEFAULT_LIMIT as HISTORY_DEFAULT_LIMIT
from .validation_history_query import list_validation_history

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Nouvelair Flow Matrix",
    description="Analyse des logs Cisco FTD -> matrice de flux -> propositions ACL",
    version="0.1.0",
)

# Outil interne mono-utilisateur (cf. docs/00 §0, "Sécurité") : origines de dev Vite
# autorisées explicitement plutôt que "*", pour ne pas ouvrir l'API à n'importe quel site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# "approved"/"blocked" : choix de valeurs pour la V1, pas une contrainte de schéma (Flow.
# validation_status est une simple colonne texte, cf. docs/00 §3ter -- rester ajustable).
VALID_VALIDATION_STATUSES = {"approved", "blocked"}

VALID_TARGET_ACTIONS = {"Allow", "Block"}

VALID_RECOMMENDATION_STATUSES = {"acknowledged", "dismissed"}

VALID_ACL_PROPOSAL_STATUSES = {"approved", "rejected"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/logs/import", response_model=ImportSummary)
def import_logs(file: UploadFile, db: Session = Depends(get_db)):
    # def (pas async def) : la lecture du fichier est synchrone et peut être volumineuse
    # (jusqu'à 200 Mo sur les fichiers réels) -- FastAPI l'exécute alors dans un threadpool
    # au lieu de bloquer la boucle d'événements.
    summary = import_log_file(db, file.file, file.filename)
    # Historique des imports (2026-09-11, demande de l'encadrant) -- enregistrement du résumé
    # DÉJÀ CALCULÉ ci-dessus, aucune nouvelle logique d'import : voir app/import_log.py.
    import_log.record_import(db, summary)
    return summary


@app.get("/api/import-logs", response_model=ImportLogsResponse)
def get_import_logs(limit: int = import_log.DEFAULT_LIMIT, offset: int = 0, db: Session = Depends(get_db)):
    # Historique des imports, visible sur la page Import même après avoir navigué ailleurs et
    # être revenu -- toutes sources confondues (demande de l'encadrant, 2026-09-11), trié du
    # plus récent au plus ancien (voir import_log.list_import_logs).
    return import_log.list_import_logs(db, limit=limit, offset=offset)


@app.post("/api/flows/qualify", response_model=QualificationRunSummary)
def run_qualification(source: Optional[str] = None, db: Session = Depends(get_db)):
    # Déclenchement explicite, même principe que Recommendation Engine et ACL Engine --
    # complète le trio (aucun des trois ne se relance automatiquement après un import).
    # Qualifie TOUS les Flow de la source donnée (ou tous si source=None), pas seulement les
    # nouveaux -- qualify_all() est idempotent (recalcule, n'accumule rien), donc rejouable
    # sans risque après chaque import. Voir CLAUDE.md "Checklist après import" pour l'ordre
    # complet (qualification avant recommandations : trop_permissive dépend de criticality_label).
    return qualification_engine.qualify_all(db, source=source)


@app.get("/api/matrix", response_model=MatrixResponse)
def get_matrix(
    dimension: str = matrix_engine.DEFAULT_DIMENSION,
    filters: dict = Depends(flow_filter_params),
    db: Session = Depends(get_db),
):
    # Mêmes filtres que GET /api/flows (flow_filter_params partagé) : appliqués en base
    # avant l'agrégation, pas juste cachés côté frontend après coup (sinon les totaux
    # affichés seraient faux). Voir Services/matrix_engine.py.
    try:
        result = matrix_engine.build_matrix(db, dimension=dimension, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dimension": dimension, "cells": result["cells"], "dimension_notice": result["notice"]}


@app.get("/api/flows", response_model=FlowsResponse)
def get_flows(
    filters: dict = Depends(flow_filter_params),
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    dimension: Optional[str] = None,
    row_value: Optional[str] = None,
    col_value: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # Même fonction que le drill-down d'une cellule de matrice : une seule source de vérité
    # pour les deux vues. dimension/row_value/col_value (optionnels) restreignent à une
    # cellule précise, pour n'importe quelle dimension de matrice -- pas seulement "zone"
    # (ingress_zone/egress_zone restent utilisables séparément comme filtre "normal" via
    # `filters`, indépendamment d'un drill-down de cellule). q : recherche par mot-clé
    # (demande de l'encadrant, 2026-08-25), cf. app/search_utils.py.
    try:
        return list_flows(db, limit=limit, offset=offset, dimension=dimension, row_value=row_value, col_value=col_value, q=q, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/flows/{flow_id}/log-entries", response_model=LogEntriesResponse)
def get_flow_log_entries(
    flow_id: int,
    limit: int = LOG_ENTRIES_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    # Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège
    # potentiellement des milliers de connexions -- jamais consultables une par une jusqu'ici.
    # 404 si le Flow n'existe pas (cohérent avec les autres endpoints scopés à un flow_id).
    if db.get(Flow, flow_id) is None:
        raise HTTPException(status_code=404, detail="Flow introuvable")
    return list_log_entries_for_flow(db, flow_id=flow_id, limit=limit, offset=offset)


@app.patch("/api/flows/{flow_id}/validation", response_model=FlowOut)
def validate_flow(flow_id: int, payload: ValidationUpdate, db: Session = Depends(get_db)):
    # Valider/Bloquer classique -- toujours immédiat, jamais de justification ni de
    # decided_action (2026-09-05, revu après un test réel : plus aucune détection de
    # contradiction ne doit décider à la place de l'utilisateur si une fenêtre de confirmation
    # s'affiche). Voir change_flow_rule ci-dessous pour le bouton dédié "Changer la règle".
    if payload.status not in VALID_VALIDATION_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status doit être parmi {sorted(VALID_VALIDATION_STATUSES)}"
        )
    flow = db.get(Flow, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow introuvable")

    # apply_validation écrit aussi une trace dans FlowValidationHistory (qui/quand/ancien->
    # nouveau statut) -- jamais un changement de statut sans historique, cf. app/flow_validation.py.
    return apply_validation(db, flow, payload.status, payload.validated_by)


@app.patch("/api/flows/{flow_id}/change-rule", response_model=FlowOut)
def change_flow_rule(flow_id: int, payload: RuleChangeUpdate, db: Session = Depends(get_db)):
    # Bouton dédié "Changer la règle" (2026-09-05) -- seul chemin qui fige une décision CIBLE
    # explicite (Flow.decided_action), toujours avec justification obligatoire, jamais fait
    # confiance à un simple champ rempli côté client sans le revérifier ici.
    if payload.target_action not in VALID_TARGET_ACTIONS:
        raise HTTPException(
            status_code=400, detail=f"target_action doit être parmi {sorted(VALID_TARGET_ACTIONS)}"
        )
    flow = db.get(Flow, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow introuvable")
    justification = (payload.justification or "").strip()
    if not justification:
        raise HTTPException(
            status_code=400,
            detail="Une justification est obligatoire pour changer la règle de ce flux.",
        )

    return apply_rule_change(db, flow, payload.target_action, payload.validated_by, justification)


@app.get("/api/flows/{flow_id}/rule-enforcement-claim", response_model=Optional[RuleEnforcementClaimOut])
def get_flow_rule_enforcement_claim(flow_id: int, db: Session = Depends(get_db)):
    # Suivi léger existant (2026-09-10) -- null si ce Flow n'a jamais été vu "regle_non_appliquee"
    # (cf. Services/validation_cycle_engine.py::_ensure_claims_detected). Utilisé côté frontend
    # pour afficher le contexte ("3e réclamation") avant de confirmer "Déclarer la réclamation".
    if db.get(Flow, flow_id) is None:
        raise HTTPException(status_code=404, detail="Flow introuvable")
    return db.query(RuleEnforcementClaim).filter_by(flow_id=flow_id).one_or_none()


@app.post("/api/flows/{flow_id}/rule-enforcement-claims", response_model=RuleEnforcementClaimOut)
def create_rule_enforcement_claim(flow_id: int, db: Session = Depends(get_db)):
    # "Déclarer la réclamation" (2026-09-10) -- revérifié ici que le flux est ENCORE
    # "regle_non_appliquee" au moment du clic, jamais fait confiance à ce qu'affichait le
    # frontend au moment du chargement de la page (peut être obsolète).
    flow = db.get(Flow, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow introuvable")
    if flow.source is None:
        raise HTTPException(status_code=400, detail="Flow sans source -- aucun cycle de validation possible.")

    cycle = validation_cycle_engine.get_latest_cycle(db, flow.source)
    snapshot = (
        db.query(FlowSnapshot)
        .filter(FlowSnapshot.cycle_id == cycle.id, FlowSnapshot.flow_id == flow.id)
        .one_or_none()
        if cycle is not None
        else None
    )
    diff = validation_cycle_engine.diff_for_flow(flow, snapshot)
    if diff["status"] != "regle_non_appliquee":
        raise HTTPException(
            status_code=400,
            detail='Ce flux n\'est pas actuellement "Règle non appliquée" -- rien à réclamer.',
        )

    return rule_enforcement_claims.declare_claim(db, flow)


@app.get("/api/rule-enforcement-claims/{claim_id}/fiche.pdf")
def get_rule_enforcement_claim_fiche(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(RuleEnforcementClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Réclamation introuvable")
    flow = claim.flow
    history = rule_enforcement_claims.get_current_decision_history(db, flow)
    pdf_bytes = build_rule_not_enforced_pdf(claim, flow, history)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="reclamation_flux_{flow.id}_{claim.id}.pdf"'},
    )


@app.get("/api/validation-history", response_model=ValidationHistoryResponse)
def get_validation_history(
    flow_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_validation_history(db, flow_id=flow_id, q=q, limit=limit, offset=offset)


@app.get("/api/validation-history/{history_id}/fiche.pdf")
def get_action_change_fiche(history_id: int, db: Session = Depends(get_db)):
    # Fiche PDF d'une inversion d'action (2026-09-03) -- générée depuis la ligne d'historique
    # figée, jamais depuis l'état courant du Flow (qui continue d'évoluer après la décision).
    # 404 si cette ligne n'est pas issue d'une inversion (pas de justification) : rien à
    # produire, un Valider/Bloquer classique n'a pas de fiche associée.
    history = db.get(FlowValidationHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Entrée d'historique introuvable")
    if history.justification is None:
        raise HTTPException(
            status_code=404,
            detail="Cette entrée ne correspond pas à une inversion d'action -- aucune fiche à générer.",
        )
    flow = history.flow
    pdf_bytes = build_action_change_pdf(history, flow)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="fiche_flux_{flow.id}_{history_id}.pdf"'},
    )


@app.post("/api/recommendations/run", response_model=RecommendationRunSummary)
def run_recommendations(source: Optional[str] = None, db: Session = Depends(get_db)):
    # Déclenchement explicite (pas auto-exécuté à l'import), même logique que le
    # Qualification Engine actuellement -- voir docs/09-recommendation-engine.md.
    return recommendation_engine.run(db, source=source)


@app.get("/api/recommendations", response_model=RuleRecommendationsResponse)
def get_recommendations(
    status: Optional[str] = None,
    finding_type: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = RECOMMENDATIONS_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_recommendations(
        db, status=status, finding_type=finding_type, source=source, q=q, limit=limit, offset=offset
    )


@app.patch("/api/recommendations/{recommendation_id}", response_model=RuleRecommendationOut)
def review_recommendation(recommendation_id: int, payload: RecommendationReview, db: Session = Depends(get_db)):
    if payload.status not in VALID_RECOMMENDATION_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status doit être parmi {sorted(VALID_RECOMMENDATION_STATUSES)}"
        )
    recommendation = db.get(RuleRecommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommandation introuvable")

    recommendation.status = payload.status
    recommendation.reviewed_by = payload.reviewed_by
    recommendation.reviewed_at = utcnow()
    db.commit()
    db.refresh(recommendation)
    return recommendation


@app.post("/api/acl-proposals/run", response_model=AclProposalRunSummary)
def run_acl_proposals(source: Optional[str] = None, cycle_id: Optional[int] = None, db: Session = Depends(get_db)):
    # Déclenchement explicite, ne modifie jamais le firewall, ne produit que des propositions.
    # cycle_id (nouveau, 2026-08-21) : appel scopé à un cycle de validation qui vient d'être
    # clôturé -- ne considère que les flux approuvés/findings acquittés depuis le cycle
    # précédent de CETTE source (jamais tout l'historique confondu). C'est le chemin normal
    # depuis la page Cycle de validation. Sans cycle_id (source seul ou rien) : comportement
    # d'origine conservé (tout l'historique) -- gardé pour compatibilité/relance manuelle
    # ponctuelle, cf. docs/11-acl-engine.md et docs/13-cycle-de-validation.md.
    if cycle_id is not None:
        cycle = db.get(ValidationCycle, cycle_id)
        if cycle is None:
            raise HTTPException(status_code=404, detail="Cycle de validation introuvable")
        return acl_engine.run_for_cycle(db, cycle)
    return acl_engine.run(db, source=source)


@app.get("/api/acl-proposals", response_model=AclProposalsResponse)
def get_acl_proposals(
    status: Optional[str] = None,
    intent: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = ACL_PROPOSALS_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_acl_proposals(db, status=status, intent=intent, source=source, q=q, limit=limit, offset=offset)


@app.patch("/api/acl-proposals/{proposal_id}", response_model=AclProposalOut)
def review_acl_proposal(proposal_id: int, payload: AclProposalReview, db: Session = Depends(get_db)):
    if payload.status not in VALID_ACL_PROPOSAL_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status doit être parmi {sorted(VALID_ACL_PROPOSAL_STATUSES)}"
        )
    proposal = db.get(AclProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposition ACL introuvable")

    # apply_acl_proposal_review écrit aussi une trace dans AclProposalHistory (qui/quand/
    # ancien -> nouveau statut) -- jamais un changement de statut sans historique, cf.
    # app/acl_proposal_review.py.
    return apply_acl_proposal_review(db, proposal, payload.status, payload.validated_by)


@app.post("/api/acl-proposals", response_model=AclProposalOut, status_code=201)
def create_manual_acl_proposal(payload: AclProposalManualCreate, db: Session = Depends(get_db)):
    # Ajout manuel, pour un flux/équipement pas encore observé dans les logs -- aucun Flow ni
    # RuleRecommendation d'origine, contrairement aux 3 intents générés par POST /api/acl-proposals/run.
    proposal = acl_engine.build_manual_proposal(
        source=payload.source,
        ingress_zone=payload.ingress_zone,
        egress_zone=payload.egress_zone,
        protocol=payload.protocol,
        dst_port=payload.dst_port,
        src_ips=payload.src_networks,
        dst_ips=payload.dst_networks,
        proposed_action=payload.proposed_action,
        suggested_rule_name=payload.suggested_rule_name,
        target_rule_name=payload.target_rule_name,
        justification=payload.justification,
        created_by=payload.created_by,
    )
    db.add(proposal)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Une proposition identique existe déjà (même source/zones/protocole/port/règle ciblée).",
        ) from exc
    db.refresh(proposal)
    return proposal


@app.get("/api/acl-proposal-history", response_model=AclProposalHistoryResponse)
def get_acl_proposal_history(
    acl_proposal_id: Optional[int] = None,
    limit: int = ACL_PROPOSAL_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_acl_proposal_history(db, acl_proposal_id=acl_proposal_id, limit=limit, offset=offset)


@app.post("/api/validation-cycles/close", response_model=ValidationCycleOut)
def close_validation_cycle(source: str, closed_by: Optional[str] = None, note: Optional[str] = None, db: Session = Depends(get_db)):
    # Déclenchement explicite, jamais automatique -- fige tous les Flow actuels d'UNE source
    # (un cycle ne mélange jamais deux firewalls, révisé le 2026-08-21 après retour de
    # l'encadrant -- cf. docs/13) comme nouvelle référence pour cette source. Aucun verrou
    # technique si des écarts restent en attente de revue humaine (avertissement doux côté
    # interface uniquement, décision actée le 2026-08-19) -- toujours une décision libre du
    # Responsable Réseau.
    return validation_cycle_engine.close_cycle(db, source=source, closed_by=closed_by, note=note)


@app.get("/api/validation-cycles", response_model=ValidationCyclesResponse)
def get_validation_cycles(source: Optional[str] = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(ValidationCycle)
    if source is not None:
        query = query.filter(ValidationCycle.source == source)
    query = query.order_by(ValidationCycle.closed_at.desc())
    total_count = query.count()
    items = query.offset(offset).limit(max(1, min(limit, 1000))).all()
    return {"items": items, "total_count": total_count}


@app.get("/api/validation-cycles/{cycle_id}/report.pdf")
def get_cycle_report(cycle_id: int, db: Session = Depends(get_db)):
    # Rapport de clôture de cycle (2026-09-10, demande de l'encadrant) -- une ligne par
    # décision "Changer la règle" prise durant ce cycle. Toujours régénéré à la demande depuis
    # FlowValidationHistory (jamais persisté) -- retéléchargeable indéfiniment, toujours à
    # jour. Voir Services/validation_cycle_engine.py::build_cycle_report.
    cycle = db.get(ValidationCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Cycle introuvable")
    rows = validation_cycle_engine.build_cycle_report(db, cycle)
    pdf_bytes = build_cycle_report_pdf(cycle, rows)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rapport_cycle_{cycle.id}.pdf"'},
    )


@app.get("/api/validation-cycles/diff", response_model=FlowDiffResponse)
def get_validation_cycle_diff(
    diff_status: Optional[str] = None,
    q: Optional[str] = None,
    src_cidr: Optional[str] = None,
    filters: dict = Depends(flow_filter_params),
    limit: int = VALIDATION_CYCLE_DIFF_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    # Écart entre la Matrice Réelle courante et la dernière Matrice Validée (dernier
    # ValidationCycle clôturé) -- voir Services/validation_cycle_engine.py. Mêmes filtres que
    # /api/flows (flow_filter_params partagé) + diff_status en plus pour se concentrer sur
    # les écarts, tout en gardant la vue complète par défaut (cf. docs/13). q : recherche par
    # mot-clé (demande de l'encadrant, 2026-08-25). src_cidr (2026-09-11) : optionnel, restreint
    # aux Flow de ce sous-réseau -- utilisé par le "+" d'une ligne de sous-réseau sur la page
    # Cycle de validation ; absent -> comportement inchangé (voir list_flows_with_diff).
    try:
        return list_flows_with_diff(db, limit=limit, offset=offset, diff_status=diff_status, q=q, src_cidr=src_cidr, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/validation-cycles/subnet-diff", response_model=SubnetDiffResponse)
def get_validation_cycle_subnet_diff(
    source: str,
    prefix_length: int = subnet_observation.DEFAULT_PREFIX_LENGTH,
    db: Session = Depends(get_db),
):
    # Rollup du diff de cycle par sous-réseau CIDR observé (2026-09-11, demande de
    # l'encadrant -- fusion de "Politiques de sous-réseau" dans le Cycle de validation) : même
    # regroupement suggestif que GET /api/network-policies/subnets, mais avec la répartition
    # des écarts de ce cycle en plus. Voir Services/validation_cycle_engine.py::compute_subnet_diff.
    try:
        return validation_cycle_engine.compute_subnet_diff(db, source=source, prefix_length=prefix_length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/validation-cycles/matrix", response_model=ValidatedMatrixResponse)
def get_validated_matrix(source: str, dimension: str = matrix_engine.DEFAULT_DIMENSION, db: Session = Depends(get_db)):
    # Reconstruit la Matrice Validée elle-même (pas un diff) depuis les FlowSnapshot du
    # dernier cycle clôturé de cette source -- demande explicite de Loulou (2026-08-21) :
    # avant, la Matrice Validée n'existait que comme donnée interne au diff, jamais
    # consultable telle quelle. Voir docs/13-cycle-de-validation.md.
    try:
        result = validation_cycle_engine.compute_validated_matrix(db, source, dimension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dimension": dimension, "cycle": result["cycle"], "cells": result["cells"]}


@app.get("/api/validation-cycles/matrix/flows", response_model=FlowsResponse)
def get_validated_matrix_flows(
    cycle_id: int,
    dimension: str,
    row_value: str,
    col_value: str,
    limit: int = validation_cycle_engine.FLOW_SNAPSHOT_CELL_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    # Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant) --
    # lit FlowSnapshot (l'état figé de CE cycle précis), jamais Flow en direct : sinon la
    # liste affichée ne correspondrait plus à ce que montre la cellule. Voir le commentaire
    # complet dans Services/validation_cycle_engine.py::list_flow_snapshots_for_cell.
    if db.get(ValidationCycle, cycle_id) is None:
        raise HTTPException(status_code=404, detail="Cycle introuvable")
    try:
        return validation_cycle_engine.list_flow_snapshots_for_cell(
            db, cycle_id=cycle_id, dimension=dimension, row_value=row_value, col_value=col_value,
            limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/validation-cycles/cell-diff", response_model=CellDiffResponse)
def get_validation_cycle_cell_diff(
    dimension: str = matrix_engine.DEFAULT_DIMENSION,
    filters: dict = Depends(flow_filter_params),
    db: Session = Depends(get_db),
):
    # Rollup du diff par cellule de matrice -- consommé par le mode de coloration
    # "Écart depuis la dernière validation" de la page Matrice (fusionné côté frontend avec
    # les cellules de GET /api/matrix par (row, col), même dimension/filtres).
    try:
        return validation_cycle_engine.compute_cell_diff(db, dimension, filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Politiques de sous-réseau (2026-09-10, demande de l'encadrant) -------------------------
#
# Fonctionnalité NOUVELLE et VOLONTAIREMENT ISOLÉE : aucun de ces 4 endpoints ne touche à
# Flow.decided_action, au diff de cycle, ni à FlowSnapshot -- le premier lit uniquement Flow
# pour compter (jamais ne le modifie), les trois autres ne travaillent que sur NetworkPolicy,
# une table à part entière sans FK vers Flow. Voir Services/subnet_observation.py et
# network_policies.py.


@app.get("/api/network-policies/subnets", response_model=SubnetObservationsResponse)
def get_observed_subnets(
    source: str,
    prefix_length: int = subnet_observation.DEFAULT_PREFIX_LENGTH,
    db: Session = Depends(get_db),
):
    # Regroupement PUREMENT SUGGESTIF des IP source par préfixe CIDR -- jamais une vérité, le
    # système ne peut pas connaître le vrai découpage réseau de Nouvelair à partir des seules
    # IP des logs (réserve affichée systématiquement côté interface).
    try:
        items = subnet_observation.observed_subnets(db, source=source, prefix_length=prefix_length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"source": source, "prefix_length": prefix_length, "items": items}


@app.post("/api/network-policies", response_model=NetworkPolicyOut)
def create_network_policy_endpoint(payload: NetworkPolicyCreate, db: Session = Depends(get_db)):
    # CIDR source et destination : texte libre, jamais validé comme un vrai CIDR/une vraie IP
    # -- peut venir d'une suggestion de regroupement (ci-dessus) ou être saisi librement,
    # demande explicite de l'encadrant. Juste non vide, comme la justification.
    if payload.action not in VALID_TARGET_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action doit être parmi {sorted(VALID_TARGET_ACTIONS)}")
    src_cidr = (payload.src_cidr or "").strip()
    destination = (payload.destination or "").strip()
    justification = (payload.justification or "").strip()
    if not src_cidr:
        raise HTTPException(status_code=400, detail="CIDR source obligatoire.")
    if not destination:
        raise HTTPException(status_code=400, detail="Destination obligatoire.")
    if not justification:
        raise HTTPException(status_code=400, detail="Justification obligatoire.")

    return network_policies.create_network_policy(
        db,
        source=payload.source,
        src_cidr=src_cidr,
        destination=destination,
        protocol=payload.protocol,
        dst_port=payload.dst_port,
        action=payload.action,
        justification=justification,
        decided_by=payload.decided_by,
    )


@app.get("/api/network-policies", response_model=NetworkPoliciesResponse)
def get_network_policies(
    source: Optional[str] = None,
    limit: int = network_policies.DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return network_policies.list_network_policies(db, source=source, limit=limit, offset=offset)


@app.get("/api/network-policies/{policy_id}/fiche.pdf")
def get_network_policy_fiche(policy_id: int, db: Session = Depends(get_db)):
    policy = db.get(NetworkPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Politique introuvable")
    pdf_bytes = build_network_policy_pdf(policy)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="politique_sous_reseau_{policy.id}.pdf"'},
    )
