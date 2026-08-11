# Nouvelair Flow Matrix — Backend

Outil d'aide à la décision pour l'équipe réseau de Nouvelair : transforme les logs du firewall Cisco FTD en une matrice de flux réseau exploitable, qualifie les communications observées, et propose des règles ACL suivant le principe de moindre privilège. Toute décision (autorisation, blocage, validation de règle) reste sous le contrôle du responsable réseau — l'outil n'applique aucun changement automatique sur le firewall.

Voir [`docs/00-comprehension-et-plan.md`](../docs/00-comprehension-et-plan.md) à la racine du dépôt pour le contexte complet, les décisions de conception et la roadmap.

## Stack

- **FastAPI** (API) + **SQLAlchemy** (ORM) + **SQLite** (stockage)
- **Pytest** pour les tests

## Setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
```

## Lancer l'API

```bash
uvicorn app.main:app --reload
```

API disponible sur http://127.0.0.1:8000 — doc interactive sur `/docs`.

## Lancer les tests

```bash
pytest
```

## Structure

```
app/
  main.py              # point d'entrée FastAPI
  database.py           # engine/session SQLAlchemy
  models.py             # modèles ORM (LogEntry, Flow, AclRule, AclProposal...)
  schemas.py             # schémas Pydantic
  parser.py              # Parser Engine
  Services/
    flow_engine.py        # Flow Engine
    matrix_engine.py       # Matrix Engine (vue dynamique sur Flow)
    qualification_engine.py # Qualification Engine
    acl_engine.py          # ACL Engine
```
