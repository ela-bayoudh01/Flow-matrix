from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow, FlowValidationHistory, RuleEnforcementClaim, ValidationCycle
from app.Services import validation_cycle_engine as vce

# Naïfs, UTC implicite -- convention du projet (app/time_utils.py) : SQLite ne conserve pas
# le fuseau des datetime "aware" à travers un aller-retour en base, mélanger les deux lève un
# TypeError à la comparaison (bug réel déjà rencontré, cf. docs/01, étape 4).
T0 = datetime(2026, 8, 1)
T1 = datetime(2026, 8, 15)

SOURCE_A = "SITE-A-FWTEST"
SOURCE_B = "SITE-B-FWTEST"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _flow(**overrides):
    # cycle_allow_count/cycle_block_count/cycle_dominant_action reflètent par défaut les
    # mêmes valeurs que leurs équivalents lifetime (comportement réel avant toute clôture,
    # cf. Flow.cycle_dominant_action) -- un test qui override dominant_action/allow_count/
    # block_count sans se soucier du diff (cell-diff, matrice validée...) reste cohérent.
    # Les tests du diff lui-même (qui compare des états AVANT/APRÈS clôture) overrident
    # explicitement les champs cycle_* -- voir plus bas.
    defaults = dict(
        source=SOURCE_A, src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
        occurrence_count=1, allow_count=1, block_count=0, dominant_action="Allow",
        cycle_occurrence_count=1, cycle_allow_count=1, cycle_block_count=0, cycle_dominant_action="Allow",
        last_seen_at=T0, criticality_label="low", validation_status="pending",
    )
    defaults.update(overrides)
    return Flow(**defaults)


# --- diff_for_flow (fonction pure) -----------------------------------------------------


def test_diff_for_flow_is_nouveau_without_a_snapshot():
    result = vce.diff_for_flow(_flow(), snapshot=None)

    assert result == {"status": "nouveau", "details": None}


def test_diff_for_flow_is_disparu_when_not_reobserved_since_snapshot(session):
    flow = _flow(last_seen_at=T0)
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A, closed_by="loulou")
    snapshot = cycle.entries[0]

    # Aucune nouvelle observation depuis la baseline : last_seen_at inchangé.
    result = vce.diff_for_flow(flow, snapshot)

    assert result == {"status": "disparu", "details": None}


def test_diff_for_flow_is_conforme_when_reobserved_but_nothing_structural_changed(session):
    flow = _flow(last_seen_at=T0, occurrence_count=1)
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    # Revu depuis (last_seen_at avance) et le volume grimpe, mais rien de structurant ne
    # change -- décision actée le 2026-08-19 : occurrence_count seul ne déclenche jamais
    # "modifie". cycle_dominant_action réaffirmé "Allow" : close_cycle() vient de le remettre
    # à None, un vrai réimport (flow_engine.consolidate()) le recalculerait depuis les
    # nouvelles occurrences -- simulé ici à la main, comme last_seen_at/occurrence_count.
    flow.last_seen_at = T1
    flow.occurrence_count = 500
    flow.cycle_dominant_action = "Allow"
    flow.cycle_allow_count = 1

    result = vce.diff_for_flow(flow, snapshot)

    assert result == {"status": "conforme", "details": None}


def test_diff_for_flow_is_modifie_when_a_structural_field_changes(session):
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Block", cycle_allow_count=0, cycle_block_count=1)
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Allow"
    flow.cycle_allow_count = 1
    flow.cycle_block_count = 0
    flow.criticality_label = "high"

    result = vce.diff_for_flow(flow, snapshot)

    assert result["status"] == "modifie"
    assert result["details"] == {
        "cycle_dominant_action": {"avant": "Block", "apres": "Allow"},
        "criticality_label": {"avant": "low", "apres": "high"},
    }


def test_diff_for_flow_is_regle_non_appliquee_when_decided_action_not_yet_observed(session):
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]
    assert snapshot.decided_action == "Block"  # bien recopié depuis Flow à la clôture

    flow.last_seen_at = T1  # revu depuis, mais le pare-feu bloque toujours pas -> Allow
    flow.cycle_dominant_action = "Allow"
    flow.cycle_allow_count = 1
    flow.cycle_block_count = 0

    result = vce.diff_for_flow(flow, snapshot)

    assert result == {
        "status": "regle_non_appliquee",
        "details": {"decided_action": {"avant": "Block", "apres": "Allow"}},
    }


def test_diff_for_flow_is_regle_non_appliquee_shows_breakdown_never_raw_mixed(session):
    # Répartition chiffrée, jamais le mot brut "Mixed", quand l'action réobservée CE CYCLE
    # est elle-même partagée (2026-09-06, demande de l'encadrant).
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Mixed"
    flow.cycle_allow_count = 18
    flow.cycle_block_count = 2

    result = vce.diff_for_flow(flow, snapshot)

    assert result == {
        "status": "regle_non_appliquee",
        "details": {
            "decided_action": {"avant": "Block", "apres": "Mixed", "apres_allow": 18, "apres_block": 2}
        },
    }


def test_diff_for_flow_is_conforme_when_decided_action_finally_observed(session):
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Block"  # la règle a enfin été appliquée dans FMC
    flow.cycle_allow_count = 0
    flow.cycle_block_count = 1

    result = vce.diff_for_flow(flow, snapshot)

    assert result == {"status": "conforme", "details": None}


def test_diff_for_flow_ignores_lifetime_dominant_action_contamination(session):
    # Le bug réel signalé : dominant_action (lifetime) reste "Mixed" pour toujours dès qu'une
    # seule occurrence contradictoire a existé n'importe quand dans l'histoire du flow, même
    # avant ce cycle -- jamais réinitialisé. cycle_dominant_action, lui, ignore totalement
    # cette contamination ancienne : seul compte ce qui a été observé depuis la clôture.
    flow = _flow(
        last_seen_at=T0, dominant_action="Mixed", allow_count=97, block_count=1,  # pollué depuis longtemps
        cycle_dominant_action="Allow", cycle_allow_count=1, cycle_block_count=0,
        decided_action="Allow",
    )
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    # Nouvel import : dominant_action lifetime reste "Mixed" pour toujours (inchangé), mais
    # le comportement de CE cycle est parfaitement Allow, exactement comme décidé.
    flow.last_seen_at = T1
    flow.dominant_action = "Mixed"  # toujours pollué par l'ancienne histoire, sans rapport
    flow.cycle_dominant_action = "Allow"
    flow.cycle_allow_count = 1
    flow.cycle_block_count = 0

    result = vce.diff_for_flow(flow, snapshot)

    assert result == {"status": "conforme", "details": None}  # jamais "regle_non_appliquee"


def test_diff_for_flow_is_modifie_when_decided_action_honored_but_something_else_changed(session):
    # Régression verrouillée : cycle_dominant_action est exclu de la comparaison une fois la
    # décision honorée (sinon systématiquement "modifie", jamais "conforme"), mais un AUTRE
    # champ structurant qui change en plus doit quand même remonter en "modifie".
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block", criticality_label="low")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Block"  # décision honorée
    flow.cycle_allow_count = 0
    flow.cycle_block_count = 1
    flow.criticality_label = "high"  # mais autre chose a aussi changé

    result = vce.diff_for_flow(flow, snapshot)

    assert result["status"] == "modifie"
    assert result["details"] == {"criticality_label": {"avant": "low", "apres": "high"}}
    assert "cycle_dominant_action" not in result["details"]


def test_diff_for_flow_without_decided_action_uses_normal_logic(session):
    # Aucune régression : un flow sans décision explicite suit exactement le chemin actuel.
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action=None)
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Block"  # aucune décision derrière -- juste une dérive organique
    flow.cycle_allow_count = 0
    flow.cycle_block_count = 1

    result = vce.diff_for_flow(flow, snapshot)

    assert result["status"] == "modifie"  # jamais "regle_non_appliquee" sans décision préalable


# --- compute_diff ------------------------------------------------------------------------


def test_compute_diff_without_any_cycle_flags_everything_nouveau(session):
    session.add_all([_flow(src_ip="10.10.1.1"), _flow(src_ip="10.10.1.2")])
    session.commit()

    pairs, summary, cycles = vce.compute_diff(session, {})

    assert cycles == {}
    assert summary["nouveau"] == 2
    assert summary["disparu"] == 0 and summary["modifie"] == 0 and summary["conforme"] == 0
    assert {status for _, diff in pairs for status in [diff["status"]]} == {"nouveau"}


def test_compute_diff_after_a_cycle_detects_the_four_statuses(session):
    stable = _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1", last_seen_at=T0, validation_status="approved")
    stale = _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2", last_seen_at=T0, validation_status="approved")
    changed = _flow(
        src_ip="10.10.1.3", dst_ip="203.0.113.3", last_seen_at=T0,
        cycle_dominant_action="Block", cycle_allow_count=0, cycle_block_count=1,
        validation_status="approved",
    )
    session.add_all([stable, stale, changed])
    session.commit()

    vce.close_cycle(session, source=SOURCE_A, closed_by="loulou")

    # "Import simulé" du lot suivant : stable revu à l'identique (cycle_dominant_action
    # réaffirmé "Allow" -- close_cycle() vient de le remettre à None, un vrai réimport le
    # recalculerait depuis les nouvelles occurrences), changed revu avec une action de ce
    # cycle différente, stale jamais revu (last_seen_at inchangé), un flux tout neuf apparaît.
    stable.last_seen_at = T1
    stable.cycle_dominant_action = "Allow"
    stable.cycle_allow_count = 1
    changed.last_seen_at = T1
    changed.cycle_dominant_action = "Allow"
    changed.cycle_allow_count = 1
    changed.cycle_block_count = 0
    session.add(_flow(src_ip="10.10.1.9", dst_ip="203.0.113.9", last_seen_at=T1))
    session.commit()

    pairs, summary, cycles = vce.compute_diff(session, {})

    assert list(cycles.keys()) == [SOURCE_A]
    statuses = {flow.src_ip: diff["status"] for flow, diff in pairs}
    assert statuses == {
        "10.10.1.1": "conforme",
        "10.10.1.2": "disparu",
        "10.10.1.3": "modifie",
        "10.10.1.9": "nouveau",
    }
    assert summary == {"nouveau": 1, "disparu": 1, "regle_non_appliquee": 0, "modifie": 1, "conforme": 1, "pending_review_count": 1}
    # pending_review_count : seul le flux "nouveau" est encore pending -- "changed" est
    # "modifie" mais déjà approuvé (validation_status="approved" dès sa création ci-dessus
    # n'a jamais été touché), donc pas compté comme en attente.


def test_compute_diff_pending_review_count_only_counts_ecarts_still_pending(session):
    changed = _flow(
        src_ip="10.10.1.3", last_seen_at=T0, cycle_dominant_action="Block", cycle_allow_count=0,
        cycle_block_count=1, validation_status="pending",
    )
    session.add(changed)
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)

    changed.last_seen_at = T1
    # écart "modifie", jamais revalidé -> reste pending
    changed.cycle_dominant_action = "Allow"
    changed.cycle_allow_count = 1
    changed.cycle_block_count = 0
    session.commit()

    _, summary, _ = vce.compute_diff(session, {})

    assert summary["modifie"] == 1
    assert summary["pending_review_count"] == 1


def test_compute_diff_pending_review_count_never_counts_disparu(session):
    # Décision actée le 2026-08-21 (retour de l'encadrant) : "disparu" est informationnel,
    # jamais un écart à traiter -- même un flux "disparu" resté "pending" ne doit jamais
    # compter dans pending_review_count.
    flow = _flow(last_seen_at=T0, validation_status="pending")
    session.add(flow)
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)
    # jamais retouché depuis -> "disparu"

    _, summary, _ = vce.compute_diff(session, {})

    assert summary["disparu"] == 1
    assert summary["pending_review_count"] == 0


def test_compute_diff_never_mixes_two_sources_baselines(session):
    # Écart trouvé après démo à l'encadrant (2026-08-21) : un cycle ne doit jamais mélanger
    # deux sources -- un flux de SOURCE_B ne doit jamais être comparé à la baseline de
    # SOURCE_A, même si les deux sont présentes dans le même appel compute_diff().
    a = _flow(source=SOURCE_A, src_ip="10.10.1.1", last_seen_at=T0)
    b = _flow(source=SOURCE_B, src_ip="10.20.1.1", last_seen_at=T0)
    session.add_all([a, b])
    session.commit()

    vce.close_cycle(session, source=SOURCE_A)
    # SOURCE_B n'a jamais été clôturée -> son flux doit rester "nouveau", jamais comparé à
    # la baseline de SOURCE_A.

    pairs, summary, cycles = vce.compute_diff(session, {})

    statuses = {flow.source: diff["status"] for flow, diff in pairs}
    assert statuses[SOURCE_A] == "disparu"  # a une baseline, jamais retouché depuis
    assert statuses[SOURCE_B] == "nouveau"  # aucune baseline pour SOURCE_B
    assert set(cycles.keys()) == {SOURCE_A}


def test_compute_diff_respects_filters(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", source=SOURCE_A),
            _flow(src_ip="10.10.1.2", source=SOURCE_B),
        ]
    )
    session.commit()

    pairs, summary, _ = vce.compute_diff(session, {"source": SOURCE_A})

    assert len(pairs) == 1
    assert summary["nouveau"] == 1


def test_compute_diff_respects_the_keyword_search(session):
    # Demande de l'encadrant (2026-08-25) : même mécanisme de recherche que la Table des
    # flux, réutilisé tel quel (FLOW_SEARCH_COLUMNS), pas une deuxième logique.
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2"),
        ]
    )
    session.commit()

    pairs, summary, _ = vce.compute_diff(session, {}, q="203.0.113.1")

    assert len(pairs) == 1
    assert pairs[0][0].dst_ip == "203.0.113.1"


def test_compute_diff_respects_src_cidr_filter(session):
    # 2026-09-11, demande de l'encadrant -- fusion de "Politiques de sous-réseau" dans le
    # Cycle de validation : le "+" d'une ligne de sous-réseau réutilise ce même compute_diff,
    # juste filtré par src_cidr.
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2"),
            _flow(src_ip="10.20.9.9", dst_ip="203.0.113.3"),
        ]
    )
    session.commit()

    pairs, summary, _ = vce.compute_diff(session, {}, src_cidr="10.10.1.0/24")

    assert {flow.src_ip for flow, _ in pairs} == {"10.10.1.1", "10.10.1.2"}
    assert summary["nouveau"] == 2


def test_compute_diff_src_cidr_absent_behaves_exactly_like_before(session):
    # Comportement par défaut inchangé -- aucune régression sur les appelants existants.
    session.add(_flow(src_ip="10.10.1.1"))
    session.commit()

    pairs, summary, _ = vce.compute_diff(session, {})

    assert len(pairs) == 1


def test_compute_diff_rejects_an_invalid_src_cidr(session):
    session.add(_flow(src_ip="10.10.1.1"))
    session.commit()

    with pytest.raises(ValueError):
        vce.compute_diff(session, {}, src_cidr="not-a-cidr")


# --- compute_cell_diff ---------------------------------------------------------------------


def test_compute_cell_diff_rolls_up_by_the_same_dimension_as_the_matrix(session):
    a = _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1", ingress_zone="Users_Zone", egress_zone="Internet_Zone", last_seen_at=T0)
    b = _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2", ingress_zone="Users_Zone", egress_zone="Internet_Zone", last_seen_at=T0)
    session.add_all([a, b])
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)

    # revu, rien de structurant ne change -> conforme (cycle_dominant_action réaffirmé
    # "Allow" -- close_cycle() vient de le remettre à None, un vrai réimport le recalculerait).
    a.last_seen_at = T1
    a.cycle_dominant_action = "Allow"
    a.cycle_allow_count = 1
    session.add(_flow(src_ip="10.10.1.3", dst_ip="203.0.113.3", ingress_zone="Users_Zone", egress_zone="Internet_Zone"))
    session.commit()
    # b n'est jamais revu -> disparu

    result = vce.compute_cell_diff(session, "zone", {})

    assert list(result["cycles"].keys()) == [SOURCE_A]
    assert result["cells"] == [
        {
            "row": "Users_Zone",
            "col": "Internet_Zone",
            "diff_summary": {"nouveau": 1, "disparu": 1, "regle_non_appliquee": 0, "modifie": 0, "conforme": 1},
        }
    ]


def test_compute_cell_diff_rejects_unknown_dimension(session):
    with pytest.raises(ValueError):
        vce.compute_cell_diff(session, "nope", {})


# --- compute_subnet_diff (2026-09-11, fusion "Politiques de sous-réseau" -> Cycle de
# validation) -------------------------------------------------------------------------------


def test_compute_subnet_diff_groups_by_cidr_and_breaks_down_diff_statuses(session):
    a = _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1", last_seen_at=T0)
    b = _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2", last_seen_at=T0)
    session.add_all([a, b])
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)

    # a revu, rien de structurant ne change -> conforme ; b jamais revu -> disparu ; c, ajouté
    # après la clôture -> nouveau. a et c partagent le même /24 que b.
    a.last_seen_at = T1
    a.cycle_dominant_action = "Allow"
    a.cycle_allow_count = 1
    session.add(_flow(src_ip="10.10.1.3", dst_ip="203.0.113.3"))
    session.commit()

    result = vce.compute_subnet_diff(session, source=SOURCE_A, prefix_length=24)

    assert result["source"] == SOURCE_A
    assert result["prefix_length"] == 24
    assert result["cycle"] is not None
    assert result["items"] == [
        {
            "cidr": "10.10.1.0/24",
            "machine_count": 3,
            "flow_count": 3,
            "diff_summary": {"nouveau": 1, "disparu": 1, "regle_non_appliquee": 0, "modifie": 0, "conforme": 1},
        }
    ]


def test_compute_subnet_diff_respects_a_finer_granularity(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.1.40", dst_ip="203.0.113.2"),
        ]
    )
    session.commit()

    result = vce.compute_subnet_diff(session, source=SOURCE_A, prefix_length=27)

    assert {item["cidr"] for item in result["items"]} == {"10.10.1.0/27", "10.10.1.32/27"}


def test_compute_subnet_diff_never_mixes_two_sources(session):
    session.add_all(
        [
            _flow(source=SOURCE_A, src_ip="10.10.1.1"),
            _flow(source=SOURCE_B, src_ip="10.10.1.2"),
        ]
    )
    session.commit()

    result = vce.compute_subnet_diff(session, source=SOURCE_A, prefix_length=24)

    assert len(result["items"]) == 1
    assert result["items"][0]["machine_count"] == 1


def test_compute_subnet_diff_rejects_out_of_range_prefix_length(session):
    with pytest.raises(ValueError):
        vce.compute_subnet_diff(session, source=SOURCE_A, prefix_length=33)


def test_compute_subnet_diff_skips_flows_with_no_valid_ipv4_src_ip(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1"),
            _flow(src_ip="not-an-ip"),
        ]
    )
    session.commit()

    result = vce.compute_subnet_diff(session, source=SOURCE_A, prefix_length=24)

    assert len(result["items"]) == 1
    assert result["items"][0]["machine_count"] == 1


# --- close_cycle ---------------------------------------------------------------------------


def test_close_cycle_snapshots_only_the_given_source(session):
    session.add_all(
        [
            _flow(source=SOURCE_A, src_ip="10.10.1.1"),
            _flow(source=SOURCE_A, src_ip="10.10.1.2"),
            _flow(source=SOURCE_B, src_ip="10.20.1.1"),
        ]
    )
    session.commit()

    cycle = vce.close_cycle(session, source=SOURCE_A, closed_by="loulou", note="baseline initiale")

    assert cycle.source == SOURCE_A
    assert cycle.flow_count == 2  # pas les 3 -- SOURCE_B exclu
    assert cycle.closed_by == "loulou"
    assert cycle.note == "baseline initiale"
    assert len(cycle.entries) == 2


def test_close_cycle_freezes_the_exact_field_values(session):
    flow = _flow(
        dominant_action="Block", cycle_dominant_action="Block", cycle_allow_count=0, cycle_block_count=7,
        criticality_label="high", occurrence_count=42, validation_status="approved",
    )
    session.add(flow)
    session.commit()

    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    assert snapshot.flow_id == flow.id
    assert snapshot.dominant_action == "Block"
    assert snapshot.cycle_dominant_action == "Block"
    assert snapshot.cycle_block_count == 7
    assert snapshot.criticality_label == "high"
    assert snapshot.occurrence_count == 42
    assert snapshot.validation_status == "approved"

    # Modifier le Flow après coup ne doit jamais rétroactivement changer le snapshot figé --
    # sinon ce ne serait plus une référence stable pour le prochain diff.
    flow.dominant_action = "Allow"
    session.commit()
    session.refresh(snapshot)
    assert snapshot.dominant_action == "Block"


def test_close_cycle_resets_the_cycle_scoped_counters_on_flow(session):
    # La fenêtre "depuis la dernière clôture" doit repartir de zéro juste après avoir été
    # figée dans le FlowSnapshot -- jamais continuer d'accumuler depuis avant (2026-09-06).
    flow = _flow(
        cycle_occurrence_count=10, cycle_allow_count=8, cycle_block_count=2, cycle_dominant_action="Mixed",
        cycle_total_initiator_bytes=1000, cycle_total_responder_bytes=2000, cycle_total_connection_duration=30,
    )
    session.add(flow)
    session.commit()

    cycle = vce.close_cycle(session, source=SOURCE_A)
    snapshot = cycle.entries[0]

    # Figé dans le snapshot avec les valeurs d'avant la remise à zéro.
    assert snapshot.cycle_occurrence_count == 10
    assert snapshot.cycle_allow_count == 8
    assert snapshot.cycle_block_count == 2
    assert snapshot.cycle_dominant_action == "Mixed"

    # Remis à zéro sur le Flow, prêt pour la prochaine fenêtre.
    assert flow.cycle_occurrence_count == 0
    assert flow.cycle_allow_count == 0
    assert flow.cycle_block_count == 0
    assert flow.cycle_dominant_action is None
    assert flow.cycle_total_initiator_bytes == 0
    assert flow.cycle_total_responder_bytes == 0
    assert flow.cycle_total_connection_duration == 0


def test_close_cycle_never_overwrites_a_previous_cycle(session):
    session.add(_flow())
    session.commit()

    first = vce.close_cycle(session, source=SOURCE_A)
    second = vce.close_cycle(session, source=SOURCE_A)

    assert first.id != second.id
    assert session.query(ValidationCycle).count() == 2


def test_close_cycle_for_one_source_never_affects_another_sources_baseline(session):
    session.add_all([_flow(source=SOURCE_A, src_ip="10.10.1.1"), _flow(source=SOURCE_B, src_ip="10.20.1.1")])
    session.commit()

    vce.close_cycle(session, source=SOURCE_A)

    assert vce.get_latest_cycle(session, SOURCE_A) is not None
    assert vce.get_latest_cycle(session, SOURCE_B) is None


def test_get_latest_cycle_picks_the_most_recently_closed_for_that_source(session):
    older = ValidationCycle(source=SOURCE_A, closed_at=T0, flow_count=0)
    newer = ValidationCycle(source=SOURCE_A, closed_at=T1, flow_count=0)
    other_source = ValidationCycle(source=SOURCE_B, closed_at=T1, flow_count=0)
    session.add_all([older, newer, other_source])
    session.commit()

    latest = vce.get_latest_cycle(session, SOURCE_A)

    assert latest.id == newer.id


def test_previous_cycle_for_finds_the_cycle_it_replaced(session):
    first = vce.close_cycle(session, source=SOURCE_A)
    second = vce.close_cycle(session, source=SOURCE_A)

    assert vce.previous_cycle_for(session, second).id == first.id
    assert vce.previous_cycle_for(session, first) is None


# --- compute_validated_matrix : la Matrice Validée elle-même, pas un diff ------------------


def test_compute_validated_matrix_is_none_without_any_cycle(session):
    result = vce.compute_validated_matrix(session, SOURCE_A, "zone")

    assert result["cycle"] is None
    assert result["cells"] == []


def test_compute_validated_matrix_reconstructs_cells_from_frozen_snapshots(session):
    a = _flow(
        src_ip="10.10.1.1", dst_ip="203.0.113.1", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
        allow_count=3, block_count=0, criticality_label="low",
    )
    b = _flow(
        src_ip="10.10.1.2", dst_ip="203.0.113.2", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
        allow_count=0, block_count=1, criticality_label="high",
    )
    session.add_all([a, b])
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    # Modifier les Flow après coup ne doit jamais changer la Matrice Validée -- elle lit
    # FlowSnapshot, jamais Flow en direct (à la différence de la Matrice Réelle).
    a.ingress_zone = "Interco_Zone"
    session.commit()

    result = vce.compute_validated_matrix(session, SOURCE_A, "zone")

    assert result["cycle"].id == cycle.id
    assert result["cells"] == [
        {
            "row": "Users_Zone", "col": "Internet_Zone", "flow_count": 2,
            "allow_count": 3, "block_count": 1, "total_bytes": 0, "total_duration_seconds": 0,
            "criticality_breakdown": {"low": 1, "high": 1},
        }
    ]


def test_compute_validated_matrix_never_leaks_another_sources_data(session):
    session.add_all([_flow(source=SOURCE_A, src_ip="10.10.1.1"), _flow(source=SOURCE_B, src_ip="10.20.1.1")])
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)
    vce.close_cycle(session, source=SOURCE_B)

    result_a = vce.compute_validated_matrix(session, SOURCE_A, "zone")
    result_b = vce.compute_validated_matrix(session, SOURCE_B, "zone")

    assert sum(c["flow_count"] for c in result_a["cells"]) == 1
    assert sum(c["flow_count"] for c in result_b["cells"]) == 1


def test_compute_validated_matrix_rejects_the_timeslot_dimension(session):
    with pytest.raises(ValueError):
        vce.compute_validated_matrix(session, SOURCE_A, "timeslot_zone")


def test_compute_validated_matrix_supports_a_derived_dimension(session):
    session.add(
        _flow(ingress_zone="Users_Zone", egress_zone="Internet_Zone", dst_port=443, criticality_label="low")
    )
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)

    result = vce.compute_validated_matrix(session, SOURCE_A, "port_category_zone")

    assert result["cells"] == [
        {
            "row": "port_courant", "col": "Users_Zone", "flow_count": 1,
            "allow_count": 1, "block_count": 0, "total_bytes": 0, "total_duration_seconds": 0,
            "criticality_breakdown": {"low": 1},
        }
    ]


def test_previous_cycle_for_never_crosses_sources(session):
    cycle_a = ValidationCycle(source=SOURCE_A, closed_at=T1, flow_count=0)
    session.add_all([ValidationCycle(source=SOURCE_B, closed_at=T0, flow_count=0), cycle_a])
    session.commit()

    assert vce.previous_cycle_for(session, cycle_a) is None


# --- list_flow_snapshots_for_cell : drill-down d'une cellule de la Matrice Validée --------


def test_list_flow_snapshots_for_cell_returns_only_the_matching_cell(session):
    a = _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1", ingress_zone="Users_Zone", egress_zone="Internet_Zone")
    b = _flow(src_ip="10.10.1.2", dst_ip="203.0.113.2", ingress_zone="Users_Zone", egress_zone="Internet_Zone")
    other_cell = _flow(src_ip="10.10.1.3", dst_ip="203.0.113.3", ingress_zone="Interco_Zone", egress_zone="Internet_Zone")
    session.add_all([a, b, other_cell])
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    result = vce.list_flow_snapshots_for_cell(
        session, cycle_id=cycle.id, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone",
    )

    assert result["total_count"] == 2
    src_ips = {item["src_ip"] for item in result["items"]}
    assert src_ips == {"10.10.1.1", "10.10.1.2"}
    assert result["summary"]["total_flows"] == 2


def test_list_flow_snapshots_for_cell_reflects_the_frozen_state_not_the_live_flow(session):
    # Le point central de la demande : si le Flow change APRÈS la clôture, le drill-down doit
    # toujours montrer ce qui était vrai au moment de CE cycle précis -- jamais l'état courant
    # (sinon la liste ne correspondrait plus à ce que montre la cellule).
    flow = _flow(criticality_label="low", ingress_zone="Users_Zone", egress_zone="Internet_Zone")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    flow.criticality_label = "critical"
    flow.ingress_zone = "Interco_Zone"  # changerait même de cellule si on lisait Flow en direct
    session.commit()

    result = vce.list_flow_snapshots_for_cell(
        session, cycle_id=cycle.id, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone",
    )

    assert result["total_count"] == 1
    assert result["items"][0]["criticality_label"] == "low"  # figé, pas "critical"
    assert result["items"][0]["ingress_zone"] == "Users_Zone"  # figé, pas "Interco_Zone"


def test_list_flow_snapshots_for_cell_never_exposes_fields_never_frozen(session):
    # validated_by/validated_at/criticality_score/security_status/web_application/
    # first_seen_at ne sont jamais figés dans FlowSnapshot -- doivent rester explicitement
    # None, jamais fabriqués à partir de l'état courant du Flow (lecture seule honnête).
    flow = _flow(validated_by="Loulou")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    result = vce.list_flow_snapshots_for_cell(
        session, cycle_id=cycle.id, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone",
    )

    item = result["items"][0]
    assert item["validated_by"] is None
    assert item["validated_at"] is None
    assert item["criticality_score"] is None
    assert item["security_status"] is None
    assert item["web_application"] is None
    assert item["first_seen_at"] is None


def test_list_flow_snapshots_for_cell_rejects_unknown_dimension(session):
    cycle = vce.close_cycle(session, source=SOURCE_A)

    with pytest.raises(ValueError):
        vce.list_flow_snapshots_for_cell(session, cycle_id=cycle.id, dimension="nope", row_value="x", col_value="y")


def test_list_flow_snapshots_for_cell_rejects_the_timeslot_dimension(session):
    cycle = vce.close_cycle(session, source=SOURCE_A)

    with pytest.raises(ValueError):
        vce.list_flow_snapshots_for_cell(session, cycle_id=cycle.id, dimension="timeslot_zone", row_value="x", col_value="y")


def test_list_flow_snapshots_for_cell_paginates(session):
    session.add_all([_flow(src_ip=f"10.10.1.{i}", dst_ip="203.0.113.1") for i in range(1, 6)])
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    result = vce.list_flow_snapshots_for_cell(
        session, cycle_id=cycle.id, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone",
        limit=2, offset=1,
    )

    assert result["total_count"] == 5
    assert len(result["items"]) == 2


# --- _ensure_claims_detected (détection passive, via compute_diff) -------------------------


def test_compute_diff_creates_a_claim_the_first_time_a_flow_is_regle_non_appliquee(session):
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    flow.last_seen_at = T1
    flow.cycle_dominant_action = "Allow"  # toujours pas appliqué
    session.commit()

    assert session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).count() == 0

    pairs, summary, _ = vce.compute_diff(session, {})

    assert summary["regle_non_appliquee"] == 1
    claim = session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).one()
    assert claim.first_detected_at is not None
    assert claim.claim_count == 0  # jamais réclamé -- juste détecté
    assert claim.last_claimed_at is None


def test_compute_diff_never_recreates_or_overwrites_an_existing_claim(session):
    flow = _flow(last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    session.add(flow)
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)
    flow.last_seen_at = T1
    session.commit()

    vce.compute_diff(session, {})
    first_claim = session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).one()
    original_detected_at = first_claim.first_detected_at

    # Un deuxième calcul de diff (ex. rechargement de page) ne doit jamais créer de doublon ni
    # réécrire first_detected_at -- toujours la première fois vue, jamais réinitialisée.
    vce.compute_diff(session, {})

    claims = session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).all()
    assert len(claims) == 1
    assert claims[0].first_detected_at == original_detected_at


def test_compute_diff_never_creates_a_claim_for_a_flow_thats_not_regle_non_appliquee(session):
    session.add(_flow(last_seen_at=T0))  # conforme, pas de decided_action
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)

    vce.compute_diff(session, {})

    assert session.query(RuleEnforcementClaim).count() == 0


def test_compute_diff_sums_regle_non_appliquee_across_every_source(session):
    # Support direct de la tuile Dashboard "X règles non appliquées (toutes sources)" --
    # aucun filtre source ne doit être nécessaire pour obtenir le total réel.
    a = _flow(source=SOURCE_A, src_ip="10.10.1.1", last_seen_at=T0, cycle_dominant_action="Allow", decided_action="Block")
    b = _flow(source=SOURCE_B, src_ip="10.20.1.1", last_seen_at=T0, cycle_dominant_action="Block", decided_action="Allow")
    session.add_all([a, b])
    session.commit()
    vce.close_cycle(session, source=SOURCE_A)
    vce.close_cycle(session, source=SOURCE_B)
    a.last_seen_at = T1
    b.last_seen_at = T1
    session.commit()

    _, summary, _ = vce.compute_diff(session, {})  # aucun filtre source

    assert summary["regle_non_appliquee"] == 2


# --- build_cycle_report ---------------------------------------------------------------------


def test_build_cycle_report_lists_decisions_made_since_the_previous_cycle(session):
    from datetime import timedelta

    from app.time_utils import utcnow

    flow = _flow()
    session.add(flow)
    session.commit()
    cycle_1 = vce.close_cycle(session, source=SOURCE_A)
    before_cycle_1 = cycle_1.closed_at - timedelta(seconds=1)

    # Décision AVANT le cycle 1 -- ne doit pas apparaître dans le rapport du cycle 2.
    session.add(FlowValidationHistory(
        flow_id=flow.id, old_status="pending", new_status="blocked", justification="Avant cycle 1.",
        decided_action="Block", created_at=before_cycle_1,
    ))
    session.commit()

    # "now" est nécessairement postérieur à cycle_1.closed_at (déjà écrit ci-dessus) et
    # antérieur à cycle_2.closed_at (pas encore clôturé) -- garanti par l'ordre d'exécution,
    # jamais par un décalage fixe qui pourrait tomber des deux côtés du second cycle réel.
    between = utcnow()
    # Décision APRÈS le cycle 1, AVANT le cycle 2 -- doit apparaître dans le rapport du cycle 2.
    session.add(FlowValidationHistory(
        flow_id=flow.id, old_status="approved", new_status="blocked", justification="Entre cycle 1 et 2.",
        decided_action="Block", created_at=between,
    ))
    # Valider/Bloquer classique (pas de justification) -- ne compte jamais comme un changement de règle.
    session.add(FlowValidationHistory(flow_id=flow.id, old_status="pending", new_status="approved", created_at=between))
    session.commit()
    cycle_2 = vce.close_cycle(session, source=SOURCE_A)

    report = vce.build_cycle_report(session, cycle_2)

    assert len(report) == 1
    history, reported_flow = report[0]
    assert history.justification == "Entre cycle 1 et 2."
    assert reported_flow.id == flow.id


def test_build_cycle_report_never_crosses_sources(session):
    a = _flow(source=SOURCE_A, src_ip="10.10.1.1")
    b = _flow(source=SOURCE_B, src_ip="10.20.1.1")
    session.add_all([a, b])
    session.commit()
    session.add(FlowValidationHistory(flow_id=b.id, old_status="pending", new_status="blocked", justification="Flux B.", decided_action="Block"))
    session.commit()
    cycle_a = vce.close_cycle(session, source=SOURCE_A)

    report = vce.build_cycle_report(session, cycle_a)

    assert report == []  # la décision de SOURCE_B ne doit jamais apparaître


def test_build_cycle_report_empty_when_no_rule_change_happened(session):
    session.add(_flow())
    session.commit()
    cycle = vce.close_cycle(session, source=SOURCE_A)

    assert vce.build_cycle_report(session, cycle) == []
