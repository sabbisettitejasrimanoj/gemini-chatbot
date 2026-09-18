from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from .config import settings

client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
database = client[settings.mongodb_database]
documents = database["documents"]
conversations = database["conversations"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def save_document(title: str, content: str, chunks: list[dict[str, Any]]) -> str:
    result = documents.insert_one({
        "title": title,
        "content": content,
        "chunks": chunks,
        "created_at": utc_now(),
    })
    return str(result.inserted_id)


def list_documents() -> list[dict[str, Any]]:
    return [
        {"id": str(item["_id"]), "title": item["title"], "created_at": item["created_at"].isoformat()}
        for item in documents.find({}, {"title": 1, "created_at": 1}).sort("created_at", -1)
    ]


def create_conversation(title: str) -> str:
    result = conversations.insert_one({
        "title": title[:80] or "New conversation",
        "messages": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    })
    return str(result.inserted_id)


def add_message(conversation_id: str, role: str, content: str) -> None:
    object_id = _conversation_object_id(conversation_id)
    conversations.update_one(
        {"_id": object_id},
        {"$push": {"messages": {"role": role, "content": content, "created_at": utc_now()}}, "$set": {"updated_at": utc_now()}},
    )


def get_messages(conversation_id: str) -> list[dict[str, str]]:
    conversation = conversations.find_one({"_id": _conversation_object_id(conversation_id)}, {"messages": 1})
    if not conversation:
        return []
    return [{"role": item["role"], "content": item["content"]} for item in conversation.get("messages", [])]


def _conversation_object_id(conversation_id: str) -> ObjectId:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("conversation_id must be a valid MongoDB ObjectId")
    return ObjectId(conversation_id)


def get_all_chunks() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents.find({}, {"title": 1, "chunks": 1}):
        for chunk in document.get("chunks", []):
            chunks.append({
                "title": document["title"],
                "content": chunk["content"],
                "embedding": chunk.get("embedding"),
                "image_url": chunk.get("image_url"),
            })
    return chunks
