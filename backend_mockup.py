import sqlite3
import trustme
import time
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from contextlib import contextmanager


# Error response model
class ErrorResponse(BaseModel):
    error: str


# Pydantic models for request validation
class ConversationState(BaseModel):
    id: int
    hashsum: int


class ApiConversationsCheck(BaseModel):
    conversations: List[ConversationState]


class ApiMessageSend(BaseModel):
    conversationId: int
    roleName: str
    content: str
    time: int


class ApiMessageGenerate(BaseModel):
    conversationId: int
    roleName: str
    time: int


class MessagePatch(BaseModel):
    id: int
    conversationId: int
    content: str


# Database connection management
@contextmanager
def get_db():
    conn = sqlite3.connect('chat.db')
    conn.row_factory = sqlite3.Row  # This enables dictionary-like access to rows
    try:
        yield conn
    finally:
        conn.close()


# Initialize database and create tables
def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        
        # Create messages table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                conversationId INTEGER NOT NULL,
                roleName TEXT NOT NULL,
                content TEXT NOT NULL,
                time INTEGER NOT NULL
            )
        ''')
        
        # Create index for faster querying
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_time 
            ON messages(conversationId, time)
        ''')
        
        conn.commit()


# Generate and save development certificates using trustme
def setup_development_certificates():
    ca = trustme.CA()
    server_cert = ca.issue_cert("localhost")
    cert_dir = Path("devcerts")
    cert_dir.mkdir(exist_ok=True)
    
    server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
    server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
    ca.cert_pem.write_to_path(cert_dir / "ca.pem")
    
    return str(cert_dir / "server.pem"), str(cert_dir / "server.key")


# Generate a hashsum from the conversation messages
def generate_hash(messages: List[sqlite3.Row]) -> int:
    """
    Custom hashsum generator for checking the integrity of a conversation.
    """
    if not messages:
        return 0
    
    hash_value = 0
    hash_chars = ""

    for message in messages:
        content = message['content']
        if not content:
            hash_value += 0
            continue

        hash_value += ord(content[0])
        hash_value += ord(content[-1])
        hash_value *= len(content)
        hash_chars += content[0] + content[-1] + str(len(content))

    hash_value %= (2**32)
    print(f"Generated hashsum: {hash_value} string rep: {hash_chars}")
    return hash_value


# Setup FastAPI app
app = FastAPI()

# Initialize the database on startup
init_db()


# API endpoints
@app.get("/api/conversation/byuserid/{user_id}")
async def get_conversations(user_id: int, response: Response, status_code=status.HTTP_200_OK):
    print("Get conversations called")

    try:
        if not user_id:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="User id missing")
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM messages WHERE conversationId = ?",
                (1,)  # Hardcoded to conversation 1 as in original
            )
            messages = cur.fetchall()
            
            print(f"Messages found: {len(messages)}")
            hashsum = generate_hash(messages)

            if hashsum == 0:
                response.status_code = status.HTTP_204_NO_CONTENT
                return None

            return [{'id': 1, 'hashsum': hashsum}]
        
    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}")
async def get_conversation_messages(
    conversation_id: int, 
    timestamp: int, 
    messages_count: int,
    response: Response, 
    status_code=status.HTTP_200_OK
):
    print("Get conversation messages called")

    try:
        if not conversation_id or timestamp is None:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID and latest timestamp are required")

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM messages 
                WHERE conversationId = ? AND time < ? 
                ORDER BY time DESC LIMIT ?
                """,
                (conversation_id, timestamp, min(messages_count, 30))
            )
            messages = cur.fetchall()
            
            if messages:
                # Convert Row objects to dictionaries
                messages = [dict(msg) for msg in messages]
                messages.reverse()  # Reverse to get chronological order
                
                if messages_count > 30 and len(messages) == 30:
                    response.status_code = status.HTTP_206_PARTIAL_CONTENT
                else:
                    response.status_code = status.HTTP_200_OK
                return messages
            else:
                response.status_code = status.HTTP_204_NO_CONTENT
                return None
        
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.post("/api/message/send")
async def user_send_message(request: ApiMessageSend, response: Response, status_code=status.HTTP_200_OK):
    print("Message send called")

    try:
        if not request.content:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Message content cannot be empty")

        message_id = int(time.time() * 1000)
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, request.conversationId, request.roleName, request.content, request.time)
            )
            conn.commit()
        
        response.status_code = status.HTTP_201_CREATED
        return {"id": message_id}
        
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.post("/api/message/generate")
async def generate_message(request: ApiMessageGenerate, response: Response, status_code=status.HTTP_200_OK):
    print("Generate message called")

    try:
        if not request:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID missing")

        message_id = int(time.time() * 1000)
        current_time = int(time.time())
        
        message_doc = {
            'id': message_id,
            'conversationId': request.conversationId,
            'roleName': request.roleName,
            'content': "This is a mock response from the backend!",
            'time': current_time
        }
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, request.conversationId, request.roleName, 
                 message_doc['content'], current_time)
            )
            conn.commit()
        
        response.status_code = status.HTTP_201_CREATED
        return message_doc
        
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.patch("/api/message/patch")
async def patch_message(request: MessagePatch, status_code=status.HTTP_200_OK):
    print("Patch message called")

    try:
        if not request.id:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE messages 
                SET content = ? 
                WHERE id = ? AND conversationId = ?
                """,
                (request.content, request.id, request.conversationId)
            )
            conn.commit()
            
            if cur.rowcount == 0:
                return Response(status_code=status.HTTP_404_NOT_FOUND)
                
        return None
        
    except Exception as e:
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.delete("/api/message/delete/{conversation_id}/{message_id}")
async def delete_message(conversation_id: int, message_id: int, status_code=status.HTTP_200_OK):
    print("Delete message called")

    try:
        if not conversation_id or not message_id:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM messages WHERE conversationId = ? AND id = ?",
                (conversation_id, message_id)
            )
            conn.commit()
            
            if cur.rowcount == 0:
                return Response(status_code=status.HTTP_404_NOT_FOUND)
                
        return None
        
    except Exception as e:
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# CORS configuration
origins = [
    "http://localhost:4200",
    "http://localhost:8080",
    "https://localhost:4200",
    "https://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Development certificate setup
dev_certs = "True"

if dev_certs == "True":
    print("Starting in development mode with auto-generated certificates...")
    cert_file, key_file = setup_development_certificates()

    print(f"""
    🔐 Development HTTPS certificates generated!
    
    To trust these certificates in development:
    1. Certificate file location: {cert_file}
    2. You might need to add an exception in your browser
    3. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0'
    
    ⚠️  These are self-signed certificates for development only!
    """)
    
    ssl_config = {
        "ssl_keyfile": key_file,
        "ssl_certfile": cert_file,
    }
else:
    ssl_config = {}
