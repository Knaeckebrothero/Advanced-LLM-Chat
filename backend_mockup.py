import trustme
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv, find_dotenv
from pathlib import Path


# Error response model
class ErrorResponse(BaseModel):
    error: str


# Pydantic models for request validation
class ApiMessageSend(BaseModel):
    conversationId: int
    roleName: str
    content: str
    time: int


class ApiMessageGenerate(BaseModel):
    conversationId: int
    participant: str
    lastTimestamp: int


class MessagePatch(BaseModel):
    messageId: int
    conversationId: int
    content: str


# Setup FastAPI app
app = FastAPI()


# Generate and save development certificates using trustme.
def setup_development_certificates():
    # Create a certificate authority
    ca = trustme.CA()
    
    # Generate server cert with localhost DNS name
    server_cert = ca.issue_cert("localhost")

    # Create a temporary directory for certificates if it doesn't exist
    cert_dir = Path("devcerts")
    cert_dir.mkdir(exist_ok=True)
    
    # Save the certificates
    server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
    server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
    ca.cert_pem.write_to_path(cert_dir / "ca.pem")
    
    return str(cert_dir / "server.pem"), str(cert_dir / "server.key")


# TODO: Create a endpoint who takes conversation hashes to check for new content.
# Perhaps you want to send the timestamp of the last message instead to check for changes.


# Mock endpoints for debugging purposes
@app.post("/api/message/send")
async def user_send_message(request: ApiMessageSend, response: Response):
    print("Message send called")

    try:
        # Error case
        if not request.content:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Message content cannot be empty")

        # Success case
        message_id = 12345
        response.status_code = status.HTTP_201_CREATED
        return {"messageId": message_id}
        
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))

@app.post("/api/message/generate")
async def generate_message(request: ApiMessageGenerate, response: Response):
    print("Generate message called")
    # TODO: Make the request also send the conversation hash to check if anything changed

    try:
        # Error case
        if not request:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID missing")

        # Success case
        response.status_code = status.HTTP_201_CREATED
        return {
            "id": 1234,
            "conversationId": request.conversationId,
            "roleName": request.roleName,
            "content": "This is a mock response from the backend!",
            "time": request.lastTimestamp
    }
        
    except Exception as e:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.patch("/api/message/patch")
async def patch_message(request: MessagePatch):
    print(f"Patch message called for message {request.messageId}")
    # Mock response
    return {
        "id": request.messageId,
        "conversationId": request.conversationId,
        "content": request.content,
        "time": "2024-03-10T12:00:00Z"
    }


@app.delete("/api/message/delete/{coversation_id}/{message_id}")
async def delete_message(coversation_id: str, message_id: str):
    print(f"Delete message called for message {message_id}")
    return {"status": "success", "message": f"Message {message_id} deleted"}


# load_dotenv(find_dotenv())
# dev_certs = os.getenv("DEV_CERTS", "True")
dev_certs = "True"

# Enable CORS
origins = [
    "http://localhost:4200",      # Angular dev server
    "http://localhost:8080",      # Alternative dev port
    "https://localhost:4200",     # In case you run Angular with SSL
    "https://localhost:8080",     # Alternative SSL port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
    expose_headers=["*"]  # Exposes all headers
)

# Check if we're in development mode
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
    # Production certificate paths
    ssl_config = {}
