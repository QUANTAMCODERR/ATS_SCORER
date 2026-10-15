import io
import unittest
import zipfile

from docx import Document

from backend.services.resume_parser import parse_resume_file, validate_file


class ValidateResumeFileTests(unittest.TestCase):
    def test_validates_pdf_by_signature(self):
        self.assertEqual(
            validate_file(b'%PDF-1.7\nresume', 'resume.pdf'),
            (True, '', 'pdf'),
        )

    def test_validates_docx_by_container_contents(self):
        document = io.BytesIO()
        with zipfile.ZipFile(document, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('word/document.xml', '<document/>')

        self.assertEqual(
            validate_file(document.getvalue(), 'resume.docx'),
            (True, '', 'docx'),
        )

    def test_parses_docx_without_native_mime_library(self):
        document = Document()
        document.add_paragraph('Experienced software engineer')
        document_bytes = io.BytesIO()
        document.save(document_bytes)

        text, metadata = parse_resume_file(document_bytes.getvalue(), 'resume.docx')

        self.assertEqual(text, 'Experienced software engineer')
        self.assertEqual(metadata['file_type'], 'docx')

    def test_rejects_zip_that_is_not_a_docx(self):
        document = io.BytesIO()
        with zipfile.ZipFile(document, 'w') as archive:
            archive.writestr('notes.txt', 'not a resume')

        is_valid, error, file_type = validate_file(document.getvalue(), 'resume.docx')

        self.assertFalse(is_valid)
        self.assertIn('Unsupported file type', error)
        self.assertIsNone(file_type)

    def test_rejects_empty_file_with_complete_validation_result(self):
        self.assertEqual(
            validate_file(b'', 'resume.pdf'),
            (
                False,
                'Uploaded file is empty. Please check the file you have uploaded and try again.',
                None,
            ),
        )


if __name__ == '__main__':
    unittest.main()
