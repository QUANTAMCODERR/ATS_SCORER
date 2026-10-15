from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


_FONT_DIR = Path(reportlab.__file__).resolve().parent / 'fonts'
_BODY_FONT = TTFont('ATSReport', str(_FONT_DIR / 'Vera.ttf'))
pdfmetrics.registerFont(_BODY_FONT)
pdfmetrics.registerFont(TTFont('ATSReport-Bold', str(_FONT_DIR / 'VeraBd.ttf')))

_BLOCK_TAGS = {
    'h1': 'title',
    'h2': 'heading',
    'h3': 'subheading',
    'h4': 'subheading',
    'h5': 'subheading',
    'h6': 'subheading',
    'p': 'body',
    'div': 'body',
    'section': 'body',
    'article': 'body',
    'header': 'body',
    'footer': 'body',
    'li': 'bullet',
    'blockquote': 'body',
    'tr': 'body',
}
_SKIPPED_TAGS = {'head', 'style', 'script', 'svg'}
_UNSUPPORTED_GLYPH_REPLACEMENTS = {
    ord('✓'): '[x]',
    ord('→'): '->',
}


class _ReportTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: List[Tuple[str, str]] = []
        self._text: List[str] = []
        self._block_kind = 'body'
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if self._skip_depth:
            if tag in _SKIPPED_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIPPED_TAGS:
            self._flush()
            self._skip_depth = 1
        elif tag in _BLOCK_TAGS:
            self._flush()
            self._block_kind = _BLOCK_TAGS[tag]
        elif tag == 'td' or tag == 'th':
            if self._text and not self._text[-1].endswith(' | '):
                self._text.append(' | ')
        elif tag == 'br':
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag in _SKIPPED_TAGS:
                self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            self._block_kind = 'body'

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = re.sub(r'\s+', ' ', ''.join(self._text)).strip()
        if text:
            self.blocks.append((self._block_kind, text))
        self._text.clear()


def _report_styles() -> Dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'ReportTitle',
            parent=styles['Title'],
            fontName='ATSReport-Bold',
            fontSize=19,
            leading=24,
            textColor=colors.HexColor('#0f172a'),
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        'heading': ParagraphStyle(
            'ReportHeading',
            parent=styles['Heading2'],
            fontName='ATSReport-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#334155'),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        'subheading': ParagraphStyle(
            'ReportSubheading',
            parent=styles['Heading3'],
            fontName='ATSReport-Bold',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
        ),
        'body': ParagraphStyle(
            'ReportBody',
            parent=styles['BodyText'],
            fontName='ATSReport',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=5,
        ),
        'bullet': ParagraphStyle(
            'ReportBullet',
            parent=styles['BodyText'],
            fontName='ATSReport',
            fontSize=9,
            leading=13,
            leftIndent=14,
            firstLineIndent=-9,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=3,
        ),
    }


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont('ATSReport', 8)
    canvas.setFillColor(colors.HexColor('#64748b'))
    canvas.drawString(0.65 * inch, 0.4 * inch, 'ATS Resume Score Report')
    canvas.drawRightString(7.85 * inch, 0.4 * inch, f'Page {document.page}')
    canvas.restoreState()


def generate_combined_pdf(html_docs: Dict[str, str]) -> bytes:
    if not html_docs:
        raise ValueError('At least one report is required to generate a PDF.')

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.7 * inch,
        title='ATS Resume Score Report',
    )
    styles = _report_styles()
    story = []

    for index, html_doc in enumerate(html_docs.values()):
        if index:
            story.append(PageBreak())

        parser = _ReportTextParser()
        parser.feed(html_doc)
        parser.close()

        for kind, text in parser.blocks:
            printable_text = text.translate(_UNSUPPORTED_GLYPH_REPLACEMENTS)
            printable_text = ''.join(
                character
                if ord(character) in _BODY_FONT.face.charWidths
                else '?'
                for character in printable_text
            )
            safe_text = escape(printable_text, quote=False)
            if kind == 'bullet':
                safe_text = f'- {safe_text}'
            story.append(Paragraph(safe_text, styles[kind]))
            if kind == 'title':
                story.append(Spacer(1, 4))

    if not story:
        raise ValueError('The reports contain no printable content.')

    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output.getvalue()
