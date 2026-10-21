"""Regenerate synthetic PDF fixtures. Requires reportlab (development only)."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures'
root.mkdir(parents=True, exist_ok=True)
pdf = canvas.Canvas(str(root / 'synthetic_notice.pdf'), invariant=True)
pdf.setTitle('Synthetic evidence - not a regulatory notice')
for number in (1, 2):
    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(55, 770, 'Mira / synthetic extraction fixture')
    pdf.setFont('Helvetica', 11)
    for i, line in enumerate([
        'TEST CONTENT ONLY. This is not a MAS publication or regulatory advice.',
        f'Page {number}: invented evidence for validating page-level citations.',
        'These paragraphs exercise text extraction, repeat ingestion and source inspection.',
        'No actual legal requirements or compliance conclusions are stated here.',
        'A later ingestion must preserve this saved source and its exact passage offsets.',
    ]):
        pdf.drawString(55, 725 - i * 25, line)
    pdf.drawString(55, 60, f'Physical page {number} / 2')
    pdf.showPage()
pdf.save()
image = Image.new('RGB', (900, 300), 'white')
draw = ImageDraw.Draw(image)
draw.text((30, 40), 'SYNTHETIC SCAN - no embedded text layer', fill='black')
scan = canvas.Canvas(str(root / 'synthetic_scan.pdf'), invariant=True)
scan.setTitle('Synthetic image-only scan')
scan.drawImage(ImageReader(image), 55, 400, width=480, height=160)
scan.showPage()
scan.save()
