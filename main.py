import os
import uuid
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import create_document, get_documents, db
from schemas import Message

app = FastAPI(title="Vionix API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"name": "Vionix", "status": "ok", "message": "Vionix backend is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the Vionix backend API!"}


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Conversation session id. If not provided, a new one is created")
    message: str = Field(..., min_length=1, description="User's message")


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Simple chat endpoint that persists the conversation.
    - Creates a session_id if not provided
    - Stores user message and assistant reply in the database
    - Returns assistant reply
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    session_id = req.session_id or str(uuid.uuid4())

    # Save the user message
    user_msg = Message(session_id=session_id, role="user", content=req.message)
    create_document("message", user_msg)

    # Very lightweight rule-based assistant while offline (no external LLM)
    text = req.message.strip().lower()
    if any(k in text for k in ["hello", "hi", "hey"]):
        reply = "Hello! I'm Vionix, your all‑in‑one AI assistant. How can I help today?"
    elif "help" in text or "what can you do" in text:
        reply = (
            "I can organize tasks, summarize text, draft emails, brainstorm ideas, "
            "and answer quick questions. Tell me what you need."
        )
    elif text.startswith("summarize:") or text.startswith("summarise:"):
        content = req.message.split(":", 1)[1].strip() if ":" in req.message else req.message
        reply = content[:200] + ("…" if len(content) > 200 else "")
        reply = f"Here’s a concise summary: {reply}"
    elif text.startswith("todo:") or text.startswith("task:"):
        items = [i.strip(" -•") for i in req.message.split("\n") if i.strip()]
        bullets = "\n".join(f"• {i}" for i in items)
        reply = f"Added to your list:\n{bullets}"
    else:
        reply = (
            "Got it. I’m processing your request. In this demo, I’m running in local smart mode "
            "without external LLMs, so responses are templated. Tell me if you want a summary, todo, or general help."
        )

    # Save assistant reply
    assistant_msg = Message(session_id=session_id, role="assistant", content=reply)
    create_document("message", assistant_msg)

    return ChatResponse(session_id=session_id, reply=reply)


class MessagesResponse(BaseModel):
    session_id: str
    messages: List[Message]


@app.get("/api/messages", response_model=MessagesResponse)
def get_messages(session_id: str = Query(..., description="Conversation session id"), limit: int = Query(50, ge=1, le=200)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    docs = get_documents("message", {"session_id": session_id}, limit=limit)
    # Convert raw dicts to Message models (ignore extra db fields)
    msgs: List[Message] = []
    for d in docs:
        try:
            msgs.append(Message(session_id=d.get("session_id", session_id), role=d.get("role", "user"), content=d.get("content", "")))
        except Exception:
            continue

    return {"session_id": session_id, "messages": msgs}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
