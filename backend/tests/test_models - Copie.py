import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AclProposal, Flow, FlowValidationHistory, LogEntry


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_no_duplicate_index_names_across_all_tables():
    """Garde-fou générique (2026-08-14) : ce bug précis (une colonne avec `index=True` ET un
    `Index(...)` explicite de même nom dans `__table_args__`) s'est produit 4 fois de suite
    (FlowValidationHistory, RuleRecommendation, l'extension du Matrix Engine, AclProposal),
    toujours découvert tardivement via un `OperationalError` cryptique noyé dans des dizaines
    d'échecs de tests sans rapport (`Base.metadata` est partagée par tout le projet, donc
    N'IMPORTE QUEL test qui crée les tables échoue, pas seulement ceux du modèle en cause).
    Ce test l'attrape immédiatement, sans même toucher une base de données, avec un message
    qui pointe directement la table et l'index en cause. Réflexe systématique après l'ajout
    ou la modification de n'importe quel modèle -- pas une checklist à se rappeler, un test
    qui échoue tout seul.
    """
    for table in Base.metadata.tables.values():
        names = [index.name for index in table.indexes]
        duplicates = {name for name in names if names.count(name) > 1}
        assert not duplicates, (
            f"Index(es) en double sur la table {table.name!r} : {duplicates}. Cause typique : "
            "une colonne a mapped_column(index=True) ET un Index(...) explicite de même nom "
            "dans __table_args__ -- retirer l'un des deux, jamais les deux à la fois."
        )


def test_log_entry_consolidates_into_flow(session):
    flow = Flow(
        source="SITE-A-FWTEST",
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        dst_port=443,
        protocol="tcp",
        occurrence_count=1,
        allow_count=1,
        dominant_action="Allow",
    )
    session.add(flow)
    session.flush()

    log_entry = LogEntry(
        source="SITE-A-FWTEST",
        raw_line="Jun 28 23:34:06 10.10.64.254  : %FTD-6-430003: ...",
        firewall_device_ip="10.10.64.254",
        device_uuid="00000000-0000-4000-a000-000000000001",
        connection_id=50437,
        access_control_rule_action="Allow",
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        dst_port=443,
        protocol="tcp",
        flow=flow,
        extra={"URLCategory": "Computer Security", "SSLVersion": "Unknown"},
    )
    session.add(log_entry)
    session.commit()

    assert flow.log_entries == [log_entry]
    assert log_entry.flow.dst_ip == "203.0.113.10"
    assert log_entry.extra["URLCategory"] == "Computer Security"


def test_flow_identity_uniqueness_is_enforced(session):
    kwargs = dict(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(Flow(**kwargs))
    session.commit()

    session.add(Flow(**kwargs))
    with pytest.raises(IntegrityError):
        session.commit()


def test_acl_proposal_can_group_several_flows(session):
    flow_1 = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="10.12.1.100", dst_port=445, protocol="tcp")
    flow_2 = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.33", dst_ip="10.12.1.100", dst_port=445, protocol="tcp")
    proposal = AclProposal(
        source="SITE-A-FWTEST",
        intent="create",
        ingress_zone="Users_Zone",
        egress_zone="Servers_Zone",
        protocol="tcp",
        dst_port=445,
        proposed_action="Allow",
        proposed_rule_text="Zone source: Users_Zone / Zone destination: Servers_Zone / TCP/445",
        flows=[flow_1, flow_2],
    )
    session.add(proposal)
    session.commit()

    assert set(proposal.flows) == {flow_1, flow_2}
    assert flow_1.acl_proposals == [proposal]
    assert flow_2.acl_proposals == [proposal]


def test_deleting_flow_preserves_log_entries_but_removes_proposal_link(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    log_entry = LogEntry(
        source="SITE-A-FWTEST",
        raw_line="raw",
        device_uuid="uuid",
        connection_id=1,
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        flow=flow,
    )
    session.add(log_entry)
    session.commit()

    session.delete(flow)
    session.commit()

    refreshed = session.get(LogEntry, log_entry.id)
    assert refreshed is not None
    assert refreshed.flow_id is None


def test_validation_history_is_linked_to_its_flow(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.flush()

    entry = FlowValidationHistory(flow_id=flow.id, old_status="pending", new_status="approved", validated_by="Loulou")
    session.add(entry)
    session.commit()

    assert flow.validation_history == [entry]
    assert entry.flow.dst_ip == "203.0.113.10"


def test_deleting_flow_cascades_to_its_validation_history(session):
    # À la différence de LogEntry (qui doit survivre indépendamment), l'historique de
    # validation n'a pas de sens sans le Flow qu'il documente -- CASCADE assumé.
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.flush()
    session.add(FlowValidationHistory(flow_id=flow.id, old_status="pending", new_status="approved"))
    session.commit()

    session.delete(flow)
    session.commit()

    assert session.query(FlowValidationHistory).count() == 0
