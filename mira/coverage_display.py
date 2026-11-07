"""Auditor-facing language for the stored source coverage outcomes."""

from mira.contracts import CoverageStatus

CHECKLIST_DESCRIPTION = (
    "The checklist lists the publications and document categories configured for this brief. "
    "Each outcome describes what the run established about that checklist item."
)
MANUAL_IMPORT_NOTE = "source refuses automated access; needs a manual import"
EXTRACTION_ERROR_PREFIX = "document retrieved, but text extraction failed: "

COVERAGE_LABELS: dict[CoverageStatus, str] = {
    "found": "Relevant material found",
    "no_change": "Checked, no change found",
    "missing": "Coverage unconfirmed",
    "fetch_failed": "Could not retrieve",
    "out_of_budget": "Stopped at run limit",
}


def coverage_label(status: CoverageStatus, note: str | None = None) -> str:
    if status == "missing" and note == MANUAL_IMPORT_NOTE:
        return "Manual import needed"
    if status == "fetch_failed" and note and note.startswith(EXTRACTION_ERROR_PREFIX):
        return "Could not extract text"
    return COVERAGE_LABELS[status]
