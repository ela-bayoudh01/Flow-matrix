"""Schémas Pydantic (I/O API)."""

from pydantic import BaseModel


class ImportSummary(BaseModel):
    filename: str
    lines_read: int
    log_entries_created: int
    log_entries_skipped_duplicate: int
    parsing_errors: int
    flows_touched: int
