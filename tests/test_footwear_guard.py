import unittest
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile

from app import rag


class FootwearGuardTests(unittest.TestCase):
    def test_footwear_question_is_allowed(self):
        self.assertTrue(rag.is_footwear_related("What is the difference between running shoes and hiking boots?"))

    def test_non_footwear_question_is_blocked(self):
        self.assertFalse(rag.is_footwear_related("How do I fix my laptop battery?"))

    def test_source_filters_match_requested_audience_and_feature(self):
        self.assertTrue(rag.source_matches_query("Men's Running Shoes", "Men's breathable running shoes", "Show men's running shoes"))
        self.assertFalse(rag.source_matches_query("Women's Sandals", "Women's casual sandals", "Show men's running shoes"))

    def test_image_source_text_must_be_footwear_related(self):
        self.assertTrue(rag.is_footwear_related("Women's running shoes"))
        self.assertFalse(rag.is_footwear_related("Company financial report"))

    def test_source_filters_requested_footwear_type(self):
        self.assertTrue(rag.source_matches_query("Men's running shoes", "Breathable running shoes", "Show running shoes"))
        self.assertFalse(rag.source_matches_query("Leather boots", "Waterproof boots", "Show sandals"))

    def test_source_filters_leather_shoes(self):
        self.assertTrue(rag.source_matches_query("Leather Shoes", "Genuine leather upper", "Show leather shoes"))
        self.assertFalse(rag.source_matches_query("Canvas Sneakers", "Canvas upper", "Show leather shoes"))

    def test_api_unavailable_returns_fallback(self):
        original_client = rag._client
        rag._client = Mock()
        rag._client.chat.completions.create.side_effect = RuntimeError("temporary provider outage")
        try:
            result = rag.generate_answer(
                "Which sneakers fit size 10?",
                "[Footwear Product Catalog] Nike Pegasus has cushioning and comfort. [Footwear Product Catalog] Adidas Ultraboost has modern style and soft midsole cushioning.",
            )
            self.assertIn("Best for comfort", result)
            self.assertIn("Nike Pegasus", result)
            self.assertIn("Adidas Ultraboost", result)
            self.assertIn("Best for style", result)
            self.assertNotIn("Footwear Product Catalog", result)
        finally:
            rag._client = original_client

    def test_extract_text_from_file_text_file(self):
        result = rag.extract_text_from_file("catalog.txt", b"Nike Pegasus has breathable cushioning and modern style.")
        self.assertIn("Nike Pegasus", result)
        self.assertIn("cushioning", result.lower())

    def test_extract_text_from_file_pdf_not_crash(self):
        try:
            rag.extract_text_from_file("catalog.pdf", b"not-a-real-pdf")
        except Exception as exc:
            self.fail(f"PDF extraction raised an exception: {exc}")

    def test_extract_docx_text_and_embedded_images(self):
        document_xml = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Nike Pegasus running shoe</w:t></w:r></w:p></w:body></w:document>'''
        docx_bytes = BytesIO()
        with ZipFile(docx_bytes, "w", ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/media/image1.png", b"png-bytes")

        text, images = rag.extract_docx_content(docx_bytes.getvalue())
        self.assertIn("Nike Pegasus", text)
        self.assertEqual(images[0][0], "image1.png")
        self.assertEqual(images[0][1], b"png-bytes")

    def test_extract_image_only_docx_returns_no_text_but_images(self):
        docx_bytes = BytesIO()
        with ZipFile(docx_bytes, "w", ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
            archive.writestr("word/media/image1.jpg", b"jpeg-bytes")

        text, images = rag.extract_docx_content(docx_bytes.getvalue())
        self.assertEqual(text, "")
        self.assertEqual(images[0][2], "image/jpeg")


if __name__ == "__main__":
    unittest.main()
