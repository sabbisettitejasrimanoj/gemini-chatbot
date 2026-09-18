import math
import re
from io import BytesIO
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from google import genai

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

from .config import settings
from .db import get_all_chunks

_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

FOOTWEAR_KEYWORDS = {
    "footwear",
    "shoe",
    "shoes",
    "sneaker",
    "sneakers",
    "boot",
    "boots",
    "sandal",
    "sandals",
    "loafer",
    "loafers",
    "heel",
    "heels",
    "trainer",
    "trainers",
    "slipper",
    "slippers",
    "running",
    "hiking",
    "athletic",
    "casual",
    "workwear",
    "outdoor",
    "ankle",
    "sole",
    "midsole",
    "insole",
    "upper",
    "cushioning",
    "footbed",
    "fit",
    "size",
    "width",
    "brand",
    "materials",
}


def is_footwear_related(query: str) -> bool:
    text = re.findall(r"[a-zA-Z]+", query.lower())
    normalized = set(text)
    return bool(normalized & FOOTWEAR_KEYWORDS) or any(term in query.lower() for term in ["shoe", "boots", "sandal", "sneaker", "trainer", "footwear"])


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    lower = filename.lower()

    if lower.endswith(".pdf"):
        if fitz is None:
            return file_bytes.decode("utf-8", errors="ignore")
        parts: list[str] = []
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                text = page.get_text()
                if text:
                    parts.append(text)
            return "\n".join(parts)
        except Exception:
            return file_bytes.decode("utf-8", errors="ignore")

    if lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        if Image is None or pytesseract is None:
            return "Uploaded footwear image. OCR support is not available yet."
        try:
            image = Image.open(BytesIO(file_bytes))
            return pytesseract.image_to_string(image)
        except Exception:
            return "Uploaded footwear image. OCR support is not available yet."

    return file_bytes.decode("utf-8", errors="ignore")


def split_text(text: str, words_per_chunk: int = 180, overlap: int = 30) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    step = max(1, words_per_chunk - overlap)
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + words_per_chunk]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def embed(text: str) -> list[float] | None:
    if not _client:
        return None
    response = _client.models.embed_content(model="gemini-embedding-001", contents=text)
    return list(response.embeddings[0].values) if response.embeddings else None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def lexical_score(query: str, content: str) -> float:
    terms = {term for term in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(term) > 2}
    words = set(re.findall(r"[a-zA-Z0-9]+", content.lower()))
    return len(terms & words) / max(len(terms), 1)


def retrieve(query: str, limit: int = 4) -> list[dict[str, Any]]:
    query_embedding = embed(query)
    scored = []
    for chunk in get_all_chunks():
        stored_embedding = chunk.get("embedding")
        score = cosine_similarity(query_embedding, stored_embedding) if query_embedding and stored_embedding else lexical_score(query, chunk["content"])
        scored.append({**chunk, "score": score})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def _fallback_footwear_summary(context: str) -> str:
    cleaned_context = re.sub(r"\[[^\]]+\]\s*", " ", context)
    cleaned_context = re.sub(r"\s+", " ", cleaned_context).strip()

    categories: dict[str, list[str]] = {"Best for comfort": [], "Best for style": [], "Best for everyday wear": []}
    seen: set[str] = set()

    for sentence in re.split(r"(?<=[.!?])\s+", cleaned_context):
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        if not cleaned:
            continue

        lower = cleaned.lower()
        if any(token in lower for token in ["catalog", "guide", "database", "source", "sizing", "document"]):
            continue

        match = re.search(r"([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)", cleaned)
        title = match.group(1) if match else cleaned[:60].strip()
        if not title or title in seen:
            continue
        seen.add(title)

        if any(word in lower for word in ["cushion", "comfort", "support", "padding", "foam", "midsole", "soft", "breathable"]):
            categories["Best for comfort"].append(title)
        if any(word in lower for word in ["style", "modern", "design", "fashion", "sleek", "trendy", "premium"]):
            categories["Best for style"].append(title)
        if any(word in lower for word in ["daily", "everyday", "casual", "versatile", "regular", "walking", "all-day"]):
            categories["Best for everyday wear"].append(title)

    if all(not items for items in categories.values()):
        return "The Gemini service is temporarily unavailable. Please try again in a moment or add more footwear knowledge to your database."

    lines = []
    for label, items in categories.items():
        if items:
            lines.append(f"- {label}: {', '.join(items[:2])}")

    return "The Gemini service is temporarily unavailable. Here are the best footwear picks based on the stored knowledge:\n" + "\n".join(lines[:3]) + "."


def generate_answer(query: str, context: str) -> str:
    if not is_footwear_related(query):
        return "I can only answer footwear-related questions. Please ask about shoes, boots, sandals, sneakers, or other footwear."

    if not _client:
        return (
            "Gemini is not configured yet. I found this relevant context:\n\n"
            f"{context or 'No matching documents found.'}\n\n"
            "Add GEMINI_API_KEY to .env to enable generated answers."
        )
    prompt = f"""You are Lumen, a footwear-focused assistant. Answer the user's question using only the context below. Only answer if the question is about footwear. If it is not about footwear, refuse politely. Keep the answer concise and factual.

Context:
{context or 'No relevant footwear context was found.'}

Question: {query}"""
    try:
        response = _client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        return response.text or "I could not generate an answer."
    except Exception:
        if context:
            return _fallback_footwear_summary(context)
        return "The Gemini service is temporarily unavailable. Please try again in a moment or add more footwear knowledge to your database."
