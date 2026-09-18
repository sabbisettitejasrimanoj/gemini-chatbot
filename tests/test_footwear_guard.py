import unittest
from unittest.mock import Mock

from google.genai.errors import ClientError

from app import rag


class FootwearGuardTests(unittest.TestCase):
    def test_footwear_question_is_allowed(self):
        self.assertTrue(rag.is_footwear_related("What is the difference between running shoes and hiking boots?"))

    def test_non_footwear_question_is_blocked(self):
        self.assertFalse(rag.is_footwear_related("How do I fix my laptop battery?"))

    def test_api_unavailable_returns_fallback(self):
        original_client = rag._client
        rag._client = Mock()
        rag._client.models.generate_content.side_effect = ClientError(
            503,
            {"error": {"message": "This model is currently experiencing high demand. Please try again later.", "status": "UNAVAILABLE"}},
        )
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


if __name__ == "__main__":
    unittest.main()
