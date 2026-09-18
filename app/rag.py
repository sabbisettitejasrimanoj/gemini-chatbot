import math
import mimetypes
import re
import logging
from pathlib import PurePosixPath
from io import BytesIO
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from groq import Groq

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

logger = logging.getLogger(__name__)

_client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None

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

AUDIENCE_TERMS = {
    "men": {"men", "mens", "men's", "male", "gentlemen"},
    "women": {"women", "womens", "women's", "female", "ladies"},
    "children": {"children", "kids", "kid", "boys", "girls"},
}
FEATURE_TERMS = {
    "running": {"running", "jogging", "trainer", "trainers"},
    "hiking": {"hiking", "trail", "outdoor"},
    "formal": {"formal", "dress", "office", "business"},
    "casual": {"casual", "everyday", "daily", "lifestyle"},
    "comfort": {"comfort", "comfortable", "cushioning", "support", "soft"},
    "sandals": {"sandal", "sandals", "slides", "flip-flops"},
    "boots": {"boot", "boots", "ankle", "workwear"},
}


def is_footwear_related(query: str) -> bool:
    text = re.findall(r"[a-zA-Z]+", query.lower())
    normalized = set(text)
    return bool(normalized & FOOTWEAR_KEYWORDS) or any(term in query.lower() for term in ["shoe", "boots", "sandal", "sneaker", "trainer", "footwear"])


def requested_filters(query: str) -> tuple[set[str], set[str]]:
    normalized = set(re.findall(r"[a-z0-9']+", query.lower()))
    audiences = {audience for audience, terms in AUDIENCE_TERMS.items() if normalized & terms}
    features = {feature for feature, terms in FEATURE_TERMS.items() if normalized & terms}
    return audiences, features


def source_matches_query(title: str, content: str, query: str) -> bool:
    audiences, features = requested_filters(query)
    source_text = f"{title} {content}".lower()
    if audiences and not any(term in source_text for audience in audiences for term in AUDIENCE_TERMS[audience]):
        return False
    if features and not any(term in source_text for feature in features for term in FEATURE_TERMS[feature]):
        return False
    return True


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    lower = filename.lower()

    if lower.endswith(".docx"):
        text, _ = extract_docx_content(file_bytes)
        return text

    if lower.endswith(".pdf"):
        if fitz is None:
            return file_bytes.decode("utf-8", errors="ignore")
        parts: list[str] = []
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                text = page.get_text()
                if isinstance(text, str) and text:
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


def extract_docx_content(file_bytes: bytes) -> tuple[str, list[tuple[str, bytes, str]]]:
    """Read document paragraphs and embedded images from a DOCX archive."""
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    images: list[tuple[str, bytes, str]] = []
    with ZipFile(BytesIO(file_bytes)) as archive:
        document_xml = ElementTree.fromstring(archive.read("word/document.xml"))
        paragraphs: list[str] = []
        for paragraph in document_xml.iter(f"{namespace}p"):
            text_parts = [node.text for node in paragraph.iter(f"{namespace}t") if isinstance(node.text, str)]
            text = "".join(text_parts).strip()
            if text:
                paragraphs.append(text)

        for member in sorted(archive.namelist()):
            path = PurePosixPath(member)
            if path.parent != PurePosixPath("word/media"):
                continue
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            images.append((path.name, archive.read(member), media_type))

    return "\n".join(paragraphs), images


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
    return None


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
    scored = []
    for chunk in get_all_chunks():
        score = lexical_score(query, chunk["content"])
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
        return "The AI service is temporarily unavailable. Please try again in a moment or add more footwear knowledge to your database."

    lines = []
    for label, items in categories.items():
        if items:
            lines.append(f"- {label}: {', '.join(items[:2])}")

    return "The AI service is temporarily unavailable. Here are the best footwear picks based on the stored knowledge:\n" + "\n".join(lines[:3]) + "."


def generate_answer(query: str, context: str) -> str:
    if not is_footwear_related(query):
        return "I can only answer footwear-related questions. Please ask about shoes, boots, sandals, sneakers, or other footwear."

    if not _client:
        return "Groq is not configured. Add your GROQ_API_KEY to .env and restart the server to enable AI-generated answers."
    prompt = f"""You are Lumen, a footwear-focused assistant. Answer the user's question using only the context below. Only answer if the question is about footwear. If it is not about footwear, refuse politely. Keep the answer concise and factual.

Context:
{context or 'No relevant footwear context was found.'}

Question: {query}"""
    try:
        response = _client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500,
        )
        return response.choices[0].message.content or "I could not generate an answer."
    except Exception as error:
        logger.warning("Groq answer generation failed: %s: %s", type(error).__name__, error)
        if context:
            return _fallback_footwear_summary(context)
        return "The AI service is temporarily unavailable. Please try again in a moment or add more footwear knowledge to your database."
