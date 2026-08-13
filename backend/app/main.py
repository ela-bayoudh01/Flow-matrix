from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (enregistre les modèles auprès de Base.metadata)
from .database import Base, engine, get_db
from .flow_filters import flow_filter_params
from .flow_validation import apply_validation
from .flows_query import DEFAULT_LIMIT, list_flows
from .ingestion import import_log_file
from .models import Flow
from .schemas import (
    FlowOut,
    FlowsResponse,
    ImportSummary,
    MatrixResponse,
    ValidationHistoryResponse,
    ValidationUpdate,
)
from .Services import matrix_engine
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
        cells = matrix_engine.build_matrix(db, dimension=dimension, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dimension": dimension, "cells": cells}


@app.get("/api/flows", response_model=FlowsResponse)
def get_flows(
    filters: dict = Depends(flow_filter_params),
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    # Même fonction que le drill-down d'une cellule de matrice (filtrée sur
    # ingress_zone/egress_zone) : une seule source de vérité pour les deux vues.
    return list_flows(db, limit=limit, offset=offset, **filters)


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
