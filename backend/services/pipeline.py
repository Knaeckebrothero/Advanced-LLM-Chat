"""
RAG Pipeline service for AI reasoning with ChromaDB and OpenAI.

This module provides the AI reasoning pipeline using LangGraph for multi-step
reasoning, ChromaDB for retrieval augmented generation, and OpenAI for LLM operations.
"""
import os
import json
from typing import List, Optional
from contextlib import contextmanager

from pydantic import SecretStr
from langgraph.checkpoint.sqlite import SqliteSaver
from rag_pipeline_recycling import (
    OpenAIClient,
    ChromaRetriever,
    ChromaDBConfig,
    ChatMessage,
    Role,
    PipelineGraph,
    UserType
)
from rag_pipeline_recycling.schemas.llm_client import OpenAIModels

from backend.database.db import get_db
from backend.config import (
    OPENAI_API_KEY,
    CHROMA_DB_PATH,
    CHROMA_COLLECTION_NAME,
    CHROMA_EMBEDDING_MODEL,
    DB_URI,
    ANSWER_MODEL,
    NODE_MODEL,
    IMG_MODEL,
)


# Singleton instances for the pipeline components
_OPENAI_CLIENT: Optional[OpenAIClient] = None
_CHROMA_RETRIEVER: Optional[ChromaRetriever] = None


def get_openai_client() -> OpenAIClient:
    """
    Get or create the OpenAI client singleton instance.

    :return: The OpenAI client instance
    :rtype: OpenAIClient
    """
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAIClient(api_key=OPENAI_API_KEY)
    return _OPENAI_CLIENT


def get_chroma_retriever() -> ChromaRetriever:
    """
    Get or create the ChromaDB retriever singleton instance.

    :return: The ChromaDB retriever instance
    :rtype: ChromaRetriever
    """
    global _CHROMA_RETRIEVER
    if _CHROMA_RETRIEVER is None:
        _CHROMA_RETRIEVER = ChromaRetriever(
            ChromaDBConfig(
                db_path=CHROMA_DB_PATH,
                collection_name=CHROMA_COLLECTION_NAME,
                embedding_model=CHROMA_EMBEDDING_MODEL,
            ),
            openai_api_key=SecretStr(OPENAI_API_KEY),
        )
    return _CHROMA_RETRIEVER


@contextmanager
def create_pipeline():
    """
    Context manager to create a PipelineGraph with checkpointing.

    Usage:
        with create_pipeline() as pipeline:
            result = pipeline.run_turn(...)

    :yields: A PipelineGraph instance with SQLite checkpointing
    :rtype: PipelineGraph
    """
    with SqliteSaver.from_conn_string(DB_URI) as checkpointer:
        yield PipelineGraph(
            checkpointer=checkpointer,
            llm_client=get_openai_client(),
            retriever=get_chroma_retriever()
        )


async def get_conversation_context_for_pipeline(
    conversation_id: str,
    limit: int = 5
) -> List[ChatMessage]:
    """
    Retrieve the last N messages from a conversation formatted for the pipeline.

    This function fetches messages from the database and converts them to the
    ChatMessage format expected by the RAG pipeline. It handles role mapping
    and content extraction from potentially JSON-formatted content.

    :param conversation_id: The unique identifier of the conversation
    :type conversation_id: str
    :param limit: Maximum number of messages to retrieve (default: 5)
    :type limit: int
    :return: List of ChatMessage objects in chronological order (oldest first)
    :rtype: List[ChatMessage]
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT roleName, content, time
                FROM messages
                WHERE conversationId = ?
                ORDER BY time DESC
                LIMIT ?
                """,
                (conversation_id, limit)
            )
            rows = cur.fetchall()

        # Reverse to get chronological order (oldest first)
        rows = list(reversed(rows))

        result: List[ChatMessage] = []
        for row in rows:
            # Normalize role names to lowercase strings
            role_name = (row["roleName"] or "").strip().lower()
            if role_name in ("assistant", "ai", "bot"):
                role_str = "assistant"
            elif role_name == "system":
                role_str = "system"
            else:
                role_str = "user"  # Fallback to user

            # Extract content (supports both plain text and JSON objects with 'content' field)
            raw_content = row["content"] or ""
            if isinstance(raw_content, str):
                try:
                    maybe_json = json.loads(raw_content)
                    if isinstance(maybe_json, dict) and "content" in maybe_json:
                        text_content = str(maybe_json.get("content") or "")
                    else:
                        text_content = raw_content
                except json.JSONDecodeError:
                    text_content = raw_content
            else:
                text_content = str(raw_content)

            # Create ChatMessage with role as string (Pydantic will cast to proper type)
            result.append(ChatMessage(role=role_str, content=text_content))

        return result

    except Exception as e:
        print(f"Error getting conversation context for pipeline: {str(e)}")
        return []


async def generate_pipeline_response(
    conversation_id: str,
    user_id: str,
    user_type: UserType = UserType.STUDENT,
    context_limit: int = 6,
    num_retrieval_results: int = 10,
    answer_model: Optional[OpenAIModels] = None,
    node_model: Optional[OpenAIModels] = None,
    img_model: Optional[OpenAIModels] = None,
) -> str:
    """
    Generate an AI response using the RAG pipeline.

    This function retrieves conversation context, runs the pipeline with the
    specified parameters, and returns the generated response.

    :param conversation_id: The unique identifier of the conversation
    :type conversation_id: str
    :param user_id: The unique identifier of the user
    :type user_id: str
    :param user_type: The type of user (STUDENT or TEACHER), default: STUDENT
    :type user_type: UserType
    :param context_limit: Number of previous messages to include in context
    :type context_limit: int
    :param num_retrieval_results: Number of documents to retrieve from ChromaDB
    :type num_retrieval_results: int
    :param answer_model: OpenAI model to use for final answer generation
    :type answer_model: Optional[OpenAIModels]
    :param node_model: OpenAI model to use for intermediate reasoning nodes
    :type node_model: Optional[OpenAIModels]
    :param img_model: OpenAI model to use for image understanding
    :type img_model: Optional[OpenAIModels]
    :return: The generated response content
    :rtype: str
    """
    # Get conversation context
    chat_messages = await get_conversation_context_for_pipeline(
        conversation_id,
        limit=context_limit
    )

    # Use default models if not specified
    answer_model = answer_model or ANSWER_MODEL
    node_model = node_model or NODE_MODEL
    img_model = img_model or IMG_MODEL

    # Run the pipeline
    with create_pipeline() as pipeline:
        result = pipeline.run_turn(
            user_id=user_id,
            user_type=user_type,
            chat_messages=chat_messages,
            answer_model_name=answer_model,
            node_model_name=node_model,
            img_model_name=img_model,
            num_retrieval_results=num_retrieval_results,
        )

    return result.response.content
