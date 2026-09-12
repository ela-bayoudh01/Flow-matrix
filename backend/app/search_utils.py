"""Recherche par mot-clé, partagée par toutes les listes de l'app (Flows, Cycle de
validation, Historique, Recommandations, Propositions ACL) -- demande directe de
l'encadrant (2026-08-25) : un seul mécanisme, jamais recodé différemment page par page.
Toujours côté serveur (jamais un filtre client sur une page déjà tronquée à `limit`) :
sur `flow_matrix.db` réel, une seule source dépasse déjà 4 700 flux pour 500 chargés par
page -- un filtre client donnerait des résultats incomplets sans le dire.
"""

from typing import Sequence

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Query
from sqlalchemy.orm.attributes import InstrumentedAttribute


def apply_keyword_search(query: Query, keyword: str | None, columns: Sequence[InstrumentedAttribute]) -> Query:
    """Filtre `query` sur les lignes où `keyword` apparaît (sous-chaîne, insensible à la
    casse) dans AU MOINS une des `columns` données. `keyword` vide/None -> aucun filtre.
    `cast(..., String)` : permet de chercher un port ou un ID numérique aussi bien qu'une
    IP/zone/nom de règle, sans traitement spécial par type de colonne.
    """
    if not keyword:
        return query
    pattern = f"%{keyword}%"
    return query.filter(or_(*[cast(col, String).ilike(pattern) for col in columns]))
