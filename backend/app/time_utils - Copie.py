"""Convention de dates du projet : tous les datetime sont naïfs, en UTC implicite.
SQLite ne conserve pas le fuseau horaire des datetime "aware" à travers un aller-retour
en base ; mélanger naïf et aware fait lever un TypeError à la comparaison (bug réel
rencontré et corrigé, cf. docs/01-journal-technique.md, étape 4).
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
