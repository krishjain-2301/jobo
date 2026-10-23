"""Read the text out of a resume so the AI can write about it."""

import re
from pathlib import Path


def extract_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        # Layout mode keeps the spaces between differently-styled words ("in **Application Security**"),
        # which the default mode glues together; it pads columns with spaces, so collapse those.
        text = "\n".join(page.extract_text(extraction_mode="layout") or "" for page in PdfReader(path).pages)
        return re.sub(r"[ \t]{2,}", " ", text).strip()
    if suffix == ".docx":
        from docx import Document

        return "\n".join(p.text for p in Document(path).paragraphs).strip()
    return path.read_text(encoding="utf-8", errors="ignore").strip()
