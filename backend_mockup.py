from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn


app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Pydantic models for request validation
class MessageGenerate(BaseModel):
    conversation_id: int
    participant: Optional[str] = None

class MessagePatch(BaseModel):
    message_id: int
    content: str

class MessageDelete(BaseModel):
    message_id: int

# Mock endpoints
@app.post("/api/message/generate")
async def generate_message(request: MessageGenerate):
    print(f"Generate message called for conversation {request.conversation_id}")
    # Mock response
    return {
        "id": 1234,
        "role": "assistant",
        "content": "This is a mock response from the backend!",
        "time": "2024-03-10T12:00:00Z"
    }

@app.patch("/api/message/{conversationId}/{messageId}")
async def patch_message(conversationId: int, messageId: int, request: MessagePatch):
    print(f"Patch message called for message {messageId}")
    # Mock response
    return {
        "id": messageId,
        "conversationId": conversationId,
        "content": request.content,
        "time": "2024-03-10T12:00:00Z"
    }

@app.delete("/api/message/{message_id}")
async def delete_message(message_id: int):
    print(f"Delete message called for message {message_id}")
    return {"status": "success", "message": f"Message {message_id} deleted"}

