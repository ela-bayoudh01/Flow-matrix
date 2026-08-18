import io
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.ingestion import import_log_file
from app.models import Flow, LogEntry

from .sample_logs import ALLOW_HTTPS_LINE, ALLOW_HTTPS_LINE_REPEAT, BLOCK_SMB_LINE, SITE_B_ALLOW_LINE, NO_AC_POLICY_LINE


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _file_of(*lines: str) -> io.BytesIO:
    return io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))


def test_import_creates_log_entries_and_flows_with_source_from_ac_policy(session):
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE, SITE_B_ALLOW_LINE), "test.log")

    assert summary["lines_read"] == 2
    assert summary["log_entries_created"] == 2
    assert summary["flows_touched"] == 2

    sources = {row.source for row in session.query(LogEntry).all()}
    assert sources == {"SITE-A-FWTEST", "SITE-B-FWTEST"}  # pas le nom de fichier "test.log"


def test_two_lines_of_the_same_communication_produce_a_single_flow(session):
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE, ALLOW_HTTPS_LINE_REPEAT), "test.log")

    assert summary["log_entries_created"] == 2
    assert summary["flows_touched"] == 1
    flow = session.query(Flow).one()
    assert flow.occurrence_count == 2


def test_reimporting_the_same_file_is_idempotent(session):
    import_log_file(session, _file_of(ALLOW_HTTPS_LINE, BLOCK_SMB_LINE), "test.log")
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE, BLOCK_SMB_LINE), "test.log")

    assert summary["log_entries_created"] == 0
    assert summary["log_entries_skipped_duplicate"] == 2
    assert session.query(LogEntry).count() == 2  # pas de doublons en base


def test_missing_ac_policy_falls_back_to_filename_and_logs_warning(session, caplog):
    with caplog.at_level(logging.WARNING):
        summary = import_log_file(session, _file_of(NO_AC_POLICY_LINE), "site-a-fwtest.log-20260630")

    assert summary["log_entries_created"] == 1
    log_entry = session.query(LogEntry).one()
    assert log_entry.source == "site-a-fwtest.log-20260630"
    assert any("ACPolicy absent" in record.message for record in caplog.records)


def test_malformed_line_is_counted_and_does_not_abort_the_import(session):
    summary = import_log_file(session, _file_of("ligne invalide", ALLOW_HTTPS_LINE), "test.log")

    assert summary["parsing_errors"] == 1
    assert summary["log_entries_created"] == 1
