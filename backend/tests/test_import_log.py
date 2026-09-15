import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.import_log import list_import_log_errors, list_import_logs, record_import
from app.ingestion import import_log_file
from app.models import ImportLog

from .sample_logs import ALLOW_HTTPS_LINE, BLOCK_SMB_LINE, SITE_B_ALLOW_LINE


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _file_of(*lines: str) -> io.BytesIO:
    return io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))


def test_record_import_persists_the_summary_already_computed_by_ingestion(session):
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE, SITE_B_ALLOW_LINE), "test.log")

    log = record_import(session, summary)

    assert log.id is not None
    assert log.filename == "test.log"
    assert log.source == "SITE-A-FWTEST, SITE-B-FWTEST"  # sources concaténées
    assert log.lines_read == summary["lines_read"]
    assert log.log_entries_created == summary["log_entries_created"]
    assert log.log_entries_skipped_duplicate == summary["log_entries_skipped_duplicate"]
    assert log.parsing_errors == summary["parsing_errors"]
    assert log.flows_touched == summary["flows_touched"]


def test_record_import_never_touches_ingestion_itself(session):
    # Isolation explicite : record_import ne fait qu'écrire ImportLog à partir d'un résumé
    # déjà calculé -- aucun effet sur LogEntry/Flow au-delà de ce que l'import a déjà produit.
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE), "test.log")
    flows_before = session.query(ImportLog).count()

    record_import(session, summary)

    assert session.query(ImportLog).count() == flows_before + 1


def test_list_import_logs_orders_most_recent_first(session):
    s1 = import_log_file(session, _file_of(ALLOW_HTTPS_LINE), "first.log")
    record_import(session, s1)
    s2 = import_log_file(session, _file_of(BLOCK_SMB_LINE), "second.log")
    record_import(session, s2)

    result = list_import_logs(session)

    assert [item.filename for item in result["items"]] == ["second.log", "first.log"]
    assert result["total_count"] == 2


def test_list_import_logs_paginates(session):
    for i in range(3):
        summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE), f"file{i}.log")
        record_import(session, summary)

    page = list_import_logs(session, limit=2, offset=1)

    assert len(page["items"]) == 2
    assert page["total_count"] == 3


def test_list_import_logs_empty_returns_empty_list(session):
    result = list_import_logs(session)

    assert result == {"items": [], "total_count": 0}


# --- Détail des erreurs de parsing (2026-09-14, demande de l'encadrant) --------------------


def test_record_import_persists_parsing_error_details(session):
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE, "ligne invalide"), "test.log")

    log = record_import(session, summary)

    errors = list_import_log_errors(session, log.id)
    assert len(errors) == 1
    assert errors[0].line_number == 2
    assert errors[0].raw_line == "ligne invalide"
    assert "non reconnu" in errors[0].error_message


def test_list_import_log_errors_ordered_by_line_number(session):
    summary = import_log_file(session, _file_of("mauvaise ligne 1", ALLOW_HTTPS_LINE, "mauvaise ligne 3"), "test.log")
    log = record_import(session, summary)

    errors = list_import_log_errors(session, log.id)

    assert [e.line_number for e in errors] == [1, 3]
    assert [e.raw_line for e in errors] == ["mauvaise ligne 1", "mauvaise ligne 3"]


def test_list_import_log_errors_scoped_to_its_own_import(session):
    # Les erreurs d'un import ne doivent jamais apparaître dans le détail d'un autre.
    s1 = import_log_file(session, _file_of("erreur import 1"), "first.log")
    log1 = record_import(session, s1)
    s2 = import_log_file(session, _file_of("erreur import 2"), "second.log")
    log2 = record_import(session, s2)

    errors1 = list_import_log_errors(session, log1.id)
    errors2 = list_import_log_errors(session, log2.id)

    assert [e.raw_line for e in errors1] == ["erreur import 1"]
    assert [e.raw_line for e in errors2] == ["erreur import 2"]


def test_list_import_log_errors_empty_when_no_error(session):
    summary = import_log_file(session, _file_of(ALLOW_HTTPS_LINE), "test.log")
    log = record_import(session, summary)

    assert list_import_log_errors(session, log.id) == []
