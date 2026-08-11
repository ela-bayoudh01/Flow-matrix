from fastapi import Depends, FastAPI, UploadFile
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (enregistre les modèles auprès de Base.metadata)
from .database import Base, engine, get_db
from .ingestion import import_log_file
from .schemas import ImportSummary

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Nouvelair Flow Matrix",
    description="Analyse des logs Cisco FTD -> matrice de flux -> propositions ACL",
    version="0.1.0",
)


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
