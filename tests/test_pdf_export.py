from io import BytesIO
import unittest

from PyPDF2 import PdfReader

from backend.services.pdf_export import generate_combined_pdf


class GenerateCombinedPdfTests(unittest.TestCase):
    def test_generates_pdf_from_html_without_native_renderer_libraries(self):
        pdf_bytes = generate_combined_pdf({
            'summary': (
                '<html><head><style>body { color: red; }</style></head><body>'
                '<h1>Resume Score — 2026</h1><h2>Overall score</h2>'
                '<p>Score: 82</p><ul><li>✓ Strong skills</li></ul>'
                '</body></html>'
            ),
            'recommendations': '<html><body><h1>Recommendations</h1></body></html>',
        })

        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        reader = PdfReader(BytesIO(pdf_bytes))
        self.assertGreaterEqual(len(reader.pages), 2)
        extracted_text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        self.assertIn('Resume Score — 2026', extracted_text)
        self.assertIn('[x] Strong skills', extracted_text)
        self.assertIn('Strong skills', extracted_text)
        self.assertIn('Recommendations', extracted_text)

    def test_rejects_empty_report_mapping(self):
        with self.assertRaisesRegex(ValueError, 'At least one report'):
            generate_combined_pdf({})


if __name__ == '__main__':
    unittest.main()
