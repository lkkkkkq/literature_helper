"""Construct rotation, raster OCR, and a two-page table fixture; not a real paper."""

import sys
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen.canvas import Canvas


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(root / "table.pdf"))
    for page in [1, 2]:
        canvas.setFont("Helvetica", 16)
        canvas.drawString(50, 780, "Constructed table " + ("start" if page == 1 else "continued"))
        canvas.setFont("Helvetica", 12)
        for y, left, right in [
            (730, "Sample", "Abundance (particles/L)"),
            (690, "A" if page == 1 else "B", "0.00004" if page == 1 else "12.50"),
        ]:
            canvas.drawString(60, y, left)
            canvas.drawString(220, y, right)
            canvas.line(50, y - 10, 490, y - 10)
        canvas.drawString(50, 630, "Synthetic fixture: do not treat these as research results.")
        canvas.showPage()
    canvas.save()
    with pdfium.PdfDocument(root / "table.pdf") as pdf:
        page = pdf[0]
        bitmap = page.render(scale=2)
        bitmap.to_pil().convert("RGB").save(root / "scan.pdf", "PDF", resolution=144)
        bitmap.close()
        page.close()
    with pdfium.PdfDocument.new() as writer, pdfium.PdfDocument(root / "table.pdf") as reader:
        writer.import_pages(reader)
        writer.import_pages(reader, pages=[0])
        page = writer[2]
        page.set_rotation(90)
        page.close()
        with pdfium.PdfDocument(root / "scan.pdf") as scan:
            writer.import_pages(scan)
        writer.save(root / "constructed-boundaries.pdf")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
