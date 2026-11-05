"""Build ordered, SMC-branded image portfolios for the team and client."""
from pathlib import Path
import re
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / 'docs/images'
OUTPUT = ROOT / 'output/pdf'
OUTPUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('SMC', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('SMC-Bold', 'C:/Windows/Fonts/arialbd.ttf'))

def natural(path):
    return [int(v) if v.isdigit() else v.lower() for v in re.split(r'(\d+)', path.name)]

for audience in ('team', 'client'):
    sources = sorted((IMAGES / audience).glob('*.png'), key=natural)
    assert sources, audience
    target = OUTPUT / f'SMC_Karaoke_Maker_{audience.title()}.pdf'
    page_width, page_height = landscape(A4)
    margin = 30
    c = canvas.Canvas(str(target), pagesize=(page_width, page_height), pageCompression=1)
    c.setTitle(f'SMC Karaoke Maker - {audience.title()}')
    c.setAuthor('Smart Media Control')
    c.setSubject('Confidential karaoke workflow presentation')
    for index, source in enumerate(sources, 1):
        if index == 1:
            c.setFillColorRGB(.46, .48, .50)
            c.setFont('SMC-Bold', 9)
            c.drawString(margin, page_height - 30, 'CONFIDENTIAL / Not for third party sharing')
            logo = Image.open(IMAGES / 'logo_SMC.png').convert('RGBA')
            logo_w = 34
            logo_h = logo_w * logo.height / logo.width
            logo_x = page_width - margin - 34 - 20
            c.drawImage(ImageReader(logo), logo_x, page_height - 18 - logo_h,
                        width=logo_w, height=logo_h, mask='auto')
            c.setFillColorRGB(.08, .13, .22)
            c.setFont('SMC-Bold', 9)
            c.drawRightString(page_width - margin, page_height - 66, 'Smart Media Control')
            c.setFillColorRGB(.28, .36, .46)
            c.setFont('SMC', 8)
            for line, y in zip(('Steenweg op Ravels 49/3', '2360 Oud-Turnhout', 'Belgium'), (78, 89, 100)):
                c.drawRightString(page_width - margin, page_height - y, line)
        image = Image.open(source)
        available_w = page_width - 2 * margin
        image_w = available_w
        image_h = image_w * image.height / image.width
        image_top = page_height - 116
        c.drawImage(ImageReader(image), margin, image_top - image_h,
                    width=image_w, height=image_h, preserveAspectRatio=True)
        c.setStrokeColorRGB(.87, .89, .92)
        c.setLineWidth(.5)
        c.line(margin, 28, page_width - margin, 28)
        c.setFont('SMC', 7)
        c.setFillColorRGB(.46, .50, .56)
        c.drawString(margin, 16, f'SMC | Karaoke Maker | {audience.title()}')
        c.drawRightString(page_width - margin, 16, f'{index} / {len(sources)}')
        c.bookmarkPage(f'page-{index}')
        c.addOutlineEntry(source.stem.replace('_', ' ').title(), f'page-{index}', level=0)
        c.showPage()
    c.save()
    reader = PdfReader(target)
    assert len(reader.pages) == len(sources)
    for index, page in enumerate(reader.pages, 1):
        assert ('CONFIDENTIAL' in page.extract_text()) == (index == 1)
        assert len(page.images) == (2 if index == 1 else 1)
    print(f'{target}: {len(reader.pages)} pages; source order: ' + ', '.join(p.name for p in sources))
