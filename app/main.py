import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import add_message, create_conversation, get_messages, list_documents, save_document
from .rag import embed, extract_text_from_file, generate_answer, is_footwear_related, retrieve, split_text
from .schemas import ChatRequest, KnowledgeCreate

app = FastAPI(title="Lumen RAG Chatbot", version="1.0.0")
static_directory = Path(__file__).parent / "static"
uploads_directory = Path(__file__).parent / "uploads"
uploads_directory.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.mount("/uploads", StaticFiles(directory=uploads_directory), name="uploads")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(static_directory / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/knowledge")
def knowledge_list() -> dict[str, list[dict[str, str]]]:
    return {"documents": list_documents()}


UPLOAD_DIR = uploads_directory


@app.post("/api/knowledge")
async def knowledge_create(
    title: str = Form(...),
    content: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict[str, object]:
    extracted_text = content
    image_url = None

    if file:
        filename = file.filename or "uploaded_file"
        file_bytes = await file.read()
        extracted_text = extract_text_from_file(filename, file_bytes) or content

        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            safe_name = f"{abs(hash(filename + str(os.times().elapsed)))}_{filename}"
            upload_path = UPLOAD_DIR / safe_name
            with upload_path.open("wb") as handle:
                handle.write(file_bytes)
            image_url = f"/uploads/{safe_name}"

    chunks = [{"content": chunk, "embedding": embed(chunk), "image_url": image_url} for chunk in split_text(extracted_text)]
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

        matches = retrieve(payload.message)
        context = "\n\n".join(f"[{match['title']}] {match['content']}" for match in matches if match["score"] > 0)
        answer = generate_answer(payload.message, context)
        add_message(conversation_id, "assistant", answer)
        return {"conversation_id": conversation_id, "answer": answer, "sources": [{"title": match["title"], "excerpt": match["content"][:180], "image_url": match.get("image_url")} for match in matches if match["score"] > 0]}
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/chat/{conversation_id}")
def conversation(conversation_id: str) -> dict[str, object]:
    try:
        return {"messages": get_messages(conversation_id)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
