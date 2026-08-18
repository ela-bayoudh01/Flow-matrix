from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (enregistre les modèles auprès de Base.metadata)
from .acl_proposal_history_query import DEFAULT_LIMIT as ACL_PROPOSAL_HISTORY_DEFAULT_LIMIT
from .acl_proposal_history_query import list_acl_proposal_history
from .acl_proposal_review import apply_acl_proposal_review
from .acl_proposals_query import DEFAULT_LIMIT as ACL_PROPOSALS_DEFAULT_LIMIT
from .acl_proposals_query import list_acl_proposals
from .database import Base, engine, get_db
from .flow_filters import flow_filter_params
from .flow_validation import apply_validation
from .flows_query import DEFAULT_LIMIT, list_flows
from .ingestion import import_log_file
from .models import AclProposal, Flow, RuleRecommendation
from .recommendations_query import DEFAULT_LIMIT as RECOMMENDATIONS_DEFAULT_LIMIT
from .recommendations_query import list_recommendations
from .schemas import (
    AclProposalHistoryResponse,
    AclProposalManualCreate,
    AclProposalOut,
    AclProposalReview,
    AclProposalRunSummary,
    AclProposalsResponse,
    FlowOut,
    FlowsResponse,
    ImportSummary,
    MatrixResponse,
    QualificationRunSummary,
    RecommendationReview,
    RecommendationRunSummary,
    RuleRecommendationOut,
    RuleRecommendationsResponse,
    ValidationHistoryResponse,
    ValidationUpdate,
)
from .Services import acl_engine, matrix_engine, qualification_engine, recommendation_engine
from .time_utils import utcnow
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
    return summary


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
    db: Session = Depends(get_db),
):
    # Même fonction que le drill-down d'une cellule de matrice : une seule source de vérité
    # pour les deux vues. dimension/row_value/col_value (optionnels) restreignent à une
    # cellule précise, pour n'importe quelle dimension de matrice -- pas seulement "zone"
    # (ingress_zone/egress_zone restent utilisables séparément comme filtre "normal" via
    # `filters`, indépendamment d'un drill-down de cellule).
    try:
        return list_flows(db, limit=limit, offset=offset, dimension=dimension, row_value=row_value, col_value=col_value, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/flows/{flow_id}/validation", response_model=FlowOut)
def validate_flow(flow_id: int, payload: ValidationUpdate, db: Session = Depends(get_db)):
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


@app.get("/api/validation-history", response_model=ValidationHistoryResponse)
def get_validation_history(
    flow_id: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_validation_history(db, flow_id=flow_id, limit=limit, offset=offset)


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
    limit: int = RECOMMENDATIONS_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_recommendations(
        db, status=status, finding_type=finding_type, source=source, limit=limit, offset=offset
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
def run_acl_proposals(source: Optional[str] = None, db: Session = Depends(get_db)):
    # Déclenchement explicite, même logique que le Recommendation Engine -- voir
    # docs/11-acl-engine.md. Ne modifie jamais le firewall, ne produit que des propositions.
    return acl_engine.run(db, source=source)


@app.get("/api/acl-proposals", response_model=AclProposalsResponse)
def get_acl_proposals(
    status: Optional[str] = None,
    intent: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = ACL_PROPOSALS_DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_acl_proposals(db, status=status, intent=intent, source=source, limit=limit, offset=offset)


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
