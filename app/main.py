from pathlib import Path
import re
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import add_message, create_conversation, get_messages, list_documents, replace_document, save_document
from .config import settings
from .rag import embed, extract_docx_content, extract_text_from_file, generate_answer, is_footwear_related, requested_filters, requested_footwear_types, retrieve, source_matches_query, split_text
from .schemas import ChatRequest

app = FastAPI(title="Lumen RAG Chatbot", version="1.0.0")
static_directory = Path(__file__).parent / "static"
uploads_directory = Path(__file__).parent / "uploads"
uploads_directory.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.mount("/uploads", StaticFiles(directory=uploads_directory), name="uploads")


def import_catalogs() -> list[str]:
    catalog_paths = sorted(Path(__file__).parent.parent.glob("*.docx"))
    all_image_urls: list[str] = []
    for catalog_path in catalog_paths:
        title = catalog_path.stem.replace("_", " ")
        try:
            extracted_text, embedded_images = extract_docx_content(catalog_path.read_bytes())
        except Exception:
            continue

        image_urls = []
        for image_name, image_bytes, _ in embedded_images:
            safe_name = f"{catalog_path.stem}_{Path(image_name).name}".replace(" ", "_")
            image_path = uploads_directory / safe_name
            if not image_path.exists():
                image_path.write_bytes(image_bytes)
            image_urls.append(f"/uploads/{safe_name}")
        all_image_urls.extend(image_urls)

        content = extracted_text or f"Footwear styles from {title}."
        entries = re.findall(r"(?:^|\n)\s*\d{1,2}\s+(.+)", extracted_text)
        if entries and image_urls:
            chunks = [{
                "content": f"{entry} from {title}.",
                "embedding": None,
                "image_urls": [image_urls[index]],
                "image_url": image_urls[index],
            } for index, entry in enumerate(entries[:len(image_urls)])]
        else:
            text_chunks = split_text(content) or [content]
            chunks = []
            for index, chunk in enumerate(text_chunks):
                chunk_images = [image_urls[index % len(image_urls)]] if image_urls else []
                chunks.append({"content": chunk, "embedding": None, "image_urls": chunk_images, "image_url": chunk_images[0] if chunk_images else None})
        replace_document(title, content, chunks)
    return all_image_urls


catalog_image_urls = import_catalogs()


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(static_directory / "index.html")


@app.get("/admin", include_in_schema=False)
def admin() -> FileResponse:
    return FileResponse(static_directory / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def require_admin(admin_key: str | None) -> None:
    if not settings.admin_key or admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Admin access is required.")


@app.get("/api/knowledge")
def knowledge_list(x_admin_key: str | None = Header(default=None)) -> dict[str, list[dict[str, str]]]:
    require_admin(x_admin_key)
    return {"documents": list_documents()}


UPLOAD_DIR = uploads_directory


@app.post("/api/knowledge")
async def knowledge_create(
    title: str = Form(...),
    content: str = Form(""),
    file: UploadFile | None = File(None),
    x_admin_key: str | None = Header(default=None),
) -> dict[str, object]:
    require_admin(x_admin_key)
    extracted_text = content
    image_urls: list[str] = []

    if file:
        filename = file.filename or "uploaded_file"
        file_bytes = await file.read()
        extracted_text = extract_text_from_file(filename, file_bytes) or content

        if filename.lower().endswith(".docx"):
            _, embedded_images = extract_docx_content(file_bytes)
            for image_name, image_bytes, _ in embedded_images:
                safe_name = f"{uuid4().hex}_{Path(image_name).name}"
                upload_path = UPLOAD_DIR / safe_name
                upload_path.write_bytes(image_bytes)
                image_urls.append(f"/uploads/{safe_name}")
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            safe_name = f"{uuid4().hex}_{Path(filename).name}"
            upload_path = UPLOAD_DIR / safe_name
            with upload_path.open("wb") as handle:
                handle.write(file_bytes)
            image_urls.append(f"/uploads/{safe_name}")

    if not extracted_text.strip() and image_urls:
        extracted_text = f"Footwear styles and models from {title}."

    text_chunks = split_text(extracted_text) or [f"Footwear style from {title}."]
    chunks = []
    for index, chunk in enumerate(text_chunks):
        chunk_images = [image_urls[index % len(image_urls)]] if image_urls else []
        chunks.append({"content": chunk, "embedding": embed(chunk), "image_urls": chunk_images, "image_url": chunk_images[0] if chunk_images else None})
    document_id = save_document(title, extracted_text, chunks)
    return {"id": document_id, "title": title, "chunks": len(chunks)}


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    try:
        conversation_id = payload.conversation_id or create_conversation(payload.message)
        add_message(conversation_id, "user", payload.message)

        if not is_footwear_related(payload.message):
            answer = "I can only answer footwear-related questions. Please ask about shoes, boots, sandals, sneakers, or other footwear."
            add_message(conversation_id, "assistant", answer)
            return {"conversation_id": conversation_id, "answer": answer, "sources": []}

        matches = retrieve(payload.message, limit=12)
        context = "\n\n".join(f"[{match['title']}] {match['content']}" for match in matches if match["score"] > 0)
        answer = generate_answer(payload.message, context)
        add_message(conversation_id, "assistant", answer)
        sources = []
        seen_sources = set()
        for match in matches:
            if match["score"] <= 0 or match["title"] in seen_sources or not source_matches_query(match["title"], match["content"], payload.message):
                continue
            seen_sources.add(match["title"])
            image_urls = match.get("image_urls", [])
            if not image_urls and match.get("image_url"):
                image_urls = [match["image_url"]]
            source = {"title": match["title"], "excerpt": match["content"][:180]}
            if image_urls and is_footwear_related(f"{match['title']} {match['content']}"):
                source["image_urls"] = image_urls
            sources.append(source)
        audiences, features = requested_filters(payload.message)
        footwear_types = requested_footwear_types(payload.message)
        if catalog_image_urls and not audiences and not features and not footwear_types:
            sources.append({"title": "Footwear catalog styles", "excerpt": "Images from the footwear catalog.", "image_urls": catalog_image_urls[:8]})
        return {"conversation_id": conversation_id, "answer": answer, "sources": sources}
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/chat/{conversation_id}")
def conversation(conversation_id: str) -> dict[str, object]:
    try:
        return {"messages": get_messages(conversation_id)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
