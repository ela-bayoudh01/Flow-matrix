"""Regenere docs/GUIDE-TECHNIQUE.pdf a partir de docs/GUIDE-TECHNIQUE.md (2026-09-15).

A relancer a chaque fois que le Markdown est corrige -- aucune autre etape necessaire, le PDF
n'est jamais edite a la main. Meme conversion que l'endpoint GET /api/technical-guide.pdf
(app/fiche_pdf.py::build_technical_guide_pdf), ce script existe juste pour regenerer le fichier
sur disque sans avoir a lancer le serveur.

Usage (depuis n'importe quel dossier) :
    backend/.venv/Scripts/python.exe backend/generate_guide_pdf.py      (Windows, venv pas active)
ou, venv deja active (.venv\\Scripts\\activate) :
    python backend/generate_guide_pdf.py
"""

from pathlib import Path

from app.fiche_pdf import build_technical_guide_pdf

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MARKDOWN_PATH = _REPO_ROOT / "docs" / "GUIDE-TECHNIQUE.md"
_PDF_PATH = _REPO_ROOT / "docs" / "GUIDE-TECHNIQUE.pdf"

if __name__ == "__main__":
    if not _MARKDOWN_PATH.exists():
        raise SystemExit(f"Introuvable : {_MARKDOWN_PATH}")

    markdown_text = _MARKDOWN_PATH.read_text(encoding="utf-8")
    pdf_bytes = build_technical_guide_pdf(markdown_text)
    _PDF_PATH.write_bytes(pdf_bytes)

    print(f"OK -- {_PDF_PATH} regenere ({len(pdf_bytes):,} octets) a partir de {_MARKDOWN_PATH.name}.")
