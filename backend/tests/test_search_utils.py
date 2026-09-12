import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow
from app.search_utils import apply_keyword_search


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_apply_keyword_search_matches_any_of_the_given_columns(session):
    session.add_all(
        [
            Flow(source="A", src_ip="10.0.0.1", dst_ip="1.1.1.1", protocol="tcp", ingress_zone="Users_Zone"),
            Flow(source="B", src_ip="10.0.0.2", dst_ip="2.2.2.2", protocol="tcp", ingress_zone="Internet_Zone"),
        ]
    )
    session.commit()

    matched_by_src = apply_keyword_search(session.query(Flow), "10.0.0.1", [Flow.src_ip, Flow.ingress_zone]).all()
    matched_by_zone = apply_keyword_search(session.query(Flow), "Internet", [Flow.src_ip, Flow.ingress_zone]).all()

    assert {f.source for f in matched_by_src} == {"A"}
    assert {f.source for f in matched_by_zone} == {"B"}


def test_apply_keyword_search_none_or_empty_keyword_is_a_no_op(session):
    session.add(Flow(source="A", src_ip="10.0.0.1", dst_ip="1.1.1.1", protocol="tcp"))
    session.commit()

    assert apply_keyword_search(session.query(Flow), None, [Flow.src_ip]).count() == 1
    assert apply_keyword_search(session.query(Flow), "", [Flow.src_ip]).count() == 1


def test_apply_keyword_search_casts_non_text_columns(session):
    session.add(Flow(source="A", src_ip="10.0.0.1", dst_ip="1.1.1.1", dst_port=8443, protocol="tcp"))
    session.commit()

    result = apply_keyword_search(session.query(Flow), "8443", [Flow.dst_port]).all()

    assert len(result) == 1
