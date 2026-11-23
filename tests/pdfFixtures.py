"""
tests/pdfFixtures.py

Shared test helper: write small, real PDFs whose page-1 text pdftotext reads
back line by line. Not a test module (pytest collects only test_*.py).
"""

from pathlib import Path


def pdfWrite(path: Path, lines: list[str]) -> Path:
    """Write a one-page PDF with each line as its own text row."""
    rows = []
    for index, text in enumerate(lines):
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        rows.append(f"BT /F1 10 Tf 50 {780 - index * 14} Td ({escaped}) Tj ET")
    stream = "\n".join(rows).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    body += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(body)
    return path
