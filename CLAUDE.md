# Nouvelair Flow Matrix

Outil d'aide à la décision pour l'équipe réseau de Nouvelair : transforme les logs du firewall Cisco FTD en matrices de flux réseau croisées exploitables (14 dimensions : zone, IP, application, protocole, port, action, règle ACL, criticité, direction, catégorie de port...), qualifie les communications par criticité (règles explicites, pas de ML), détecte les règles ACL obsolètes/trop permissives, et propose des règles ACL en moindre privilège. **Outil d'assistance uniquement** : ne modifie jamais le firewall, le Responsable Réseau valide chaque décision.

**Stack** : FastAPI + SQLAlchemy + SQLite (backend) · React + TypeScript + MUI + AG Grid (frontend).

**État actuel** : projet fonctionnellement complet -- backend (6 moteurs : Parser/Flow/Matrix/Qualification/Recommendation/ACL Engines, historique de validation) et frontend (7 pages : Dashboard, Matrice, Table des flux, Historique, Recommandations, Propositions ACL), tous vérifiés sur les vraies données de `flow_matrix.db`. Passage de design professionnel effectué (sidebar, thème MUI personnalisé, palette calée sur la méthode data-viz, animations). Prochaine étape à définir avec Loulou.

**Données sensibles** : `backend/data/raw_logs/`, `backend/flow_matrix.db` et tout `docs/` contiennent de vraies données Nouvelair (IP, zones, sites) — gitignorés, jamais commités. Le code (y compris les tests) n'utilise que des données fictives.

**⚠️ Après l'import d'un nouveau fichier de logs**, rien ne se met à jour automatiquement au-delà de la Table des flux/Matrice/Dashboard/Historique — Qualification, Recommandations et Propositions ACL exigent chacune un déclenchement explicite, **dans cet ordre précis** (chacun dépend du précédent) : voir [`docs/12-checklist-apres-import.md`](docs/12-checklist-apres-import.md).

## Documentation

| Fichier | Contenu |
|---|---|
| `docs/00-comprehension-et-plan.md` | Contexte, décisions actées, principes non négociables du projet |
| `docs/01-journal-technique.md` | Résumés + liens vers chaque étape — point d'entrée chronologique |
| `docs/02-modele-de-donnees.md` | Schéma complet des tables (`LogEntry`, `Flow`, `AclProposal`...) |
| `docs/03-parser-engine.md` | Parsing des logs Cisco FTD : format, stratégie, vérifications |
| `docs/04-ingestion-et-flow-engine.md` | Import des logs, agrégation en `Flow`, bugs réels corrigés |
| `docs/05-matrix-engine.md` | Matrice Zone × Zone + extension à 14 dimensions, `dimension_notice` |
| `docs/06-catalogue-des-tests.md` | Tous les tests du projet expliqués + méthode de travail générale |
| `docs/07-qualification-engine.md` | Scoring de criticité, classification des zones, itérations mesurées |
| `docs/08-historique-des-validations.md` | Traçabilité des validations humaines (qui, quand, statut) |
| `docs/09-recommendation-engine.md` | Détection règles obsolètes/trop permissives, sur trafic déjà observé |
| `docs/10-comprendre-le-volume-de-donnees.md` | Pourquoi des cellules à "0 o" : lecture des octets mesurés par le firewall |
| `docs/11-acl-engine.md` | Propositions de règles ACL (create/tighten/revoke), fiche structurée FTD/FMC |
| `docs/12-checklist-apres-import.md` | Ordre exact des étapes à relancer après un nouvel import |
| `docs/frontend/00-architecture.md` | Structure des pages/composants, choix techniques frontend |
| `docs/frontend/01-setup-et-flows-table.md` | Setup React/Vite, première page (table des flux) |
| `docs/frontend/02-matrix-page.md` | Page matrice : construction, coloration, panneau de détail |
| `docs/frontend/03-filter-bar.md` | Filtres partagés matrice/table, extension du backend |
| `docs/frontend/04-legende-et-tooltip.md` | Légende de criticité et tooltip de cellule |
| `docs/frontend/05-dashboard-page.md` | Page de statistiques globales |
| `docs/frontend/06-history-page.md` | Page historique des validations, câblée sur l'API existante |
| `docs/frontend/07-recommendations-page.md` | Page recommandations : grille, panneau de détail, aide contextuelle |
| `docs/frontend/08-acl-proposals-page.md` | Page propositions ACL : grille, fiche, export, ajout manuel |
| `docs/frontend/09-design-system.md` | Passage design : palette, thème MUI, sidebar, animations |

## Règle de comportement

Au début de chaque session (ou après un compact), lis d'abord `docs/00-comprehension-et-plan.md` et `docs/01-journal-technique.md` pour te remettre à jour sur l'état du projet. Si la tâche demandée concerne une brique précise déjà documentée (parser, matrix engine, qualification, frontend...), lis aussi le fichier `docs/` correspondant avant de commencer, plutôt que de repartir de zéro ou de deviner. Ne réexplique jamais quelque chose qui est déjà écrit dans un doc : pointe vers le fichier si Loulou pose une question déjà documentée.
