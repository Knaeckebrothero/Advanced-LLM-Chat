# backend/services/agent.py
"""
LangGraph-based agent for the Fessi waste disposal assistant.
This agent uses Neo4j tools to answer waste disposal questions with multi-step reasoning.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
from typing import TypedDict, Annotated, Sequence, AsyncGenerator, Union, Optional
import operator
import json
import time
import uuid
import logging

from .tools.neo4j_tools import get_all_tools
from .tools.file_tools import get_file_content
from .tools.web_search_tools import get_web_search_tool
from ..models.message import AgentStep
from .image_handler import (
    prepare_image_for_llm,
    is_image_processing_enabled,
    prepare_document_for_llm,
    prepare_audio_for_llm
)

logger = logging.getLogger(__name__)

# Define the agent state
class AgentState(TypedDict):
    """State for the Fessi agent graph."""
    messages: Annotated[Sequence[Union[HumanMessage, AIMessage, SystemMessage, ToolMessage]], operator.add]
    steps: list
    final_response: str


# System prompt for the agent (bilingual - German primary, English fallback)
SYSTEM_PROMPT = """Du bist Fessi, ein freundlicher und hilfsbereiter Assistent für Abfallentsorgung in Frankfurt am Main.

## Deine Aufgaben:
- Hilf Nutzern herauszufinden, wie man bestimmte Abfälle richtig entsorgt
- Gib Informationen über Wertstoffhöfe und Sammelstellen
- Beantworte Fragen zur Mülltrennung und Recycling
- Erkläre die verschiedenen Tonnen und Container (Gelber Sack, Biotonne, etc.)

## Verfügbare Tools:
Du hast Zugang zu einer Wissensdatenbank mit Informationen über:
- Abfallarten und deren korrekte Entsorgung
- Entsorgungsmethoden (Tonnen, Container, Wertstoffhöfe)
- Standorte von Wertstoffhöfen in Frankfurt
- Häufig gestellte Fragen (FAQs)

Du kannst auch das Internet durchsuchen für aktuelle Informationen (falls die Websuche aktiviert ist).

## Anweisungen:
1. Nutze die verfügbaren Tools, um genaue Informationen abzurufen
2. Antworte immer auf Deutsch, es sei denn, der Nutzer spricht Englisch
3. Sei freundlich, klar und konkret in deinen Antworten
4. Wenn du keine passende Information findest, sage das ehrlich
5. Gib bei Bedarf allgemeine Tipps zur Mülltrennung

## Beispiel-Interaktionen:
- "Wo entsorge ich alte Batterien?" -> Nutze search_waste_disposal
- "Was gehört in den Gelben Sack?" -> Nutze get_disposal_method_details
- "Wo ist der nächste Wertstoffhof?" -> Nutze find_nearby_recycling_centers

## Datei-Zugriff:
Wenn Nutzer Dateien (Bilder, PDFs, Dokumente) teilen, siehst du in der aktuellen Nachricht den vollständigen Inhalt.
In Folge-Nachrichten werden Dateien als Platzhalter angezeigt:

[Attachment: report.pdf (fileId: abc123) - 5 pages, PDF document]

Um auf früher geteilte Dateien zuzugreifen, nutze das get_file_content Tool:
- get_file_content(file_id="abc123") - Gesamten Inhalt abrufen
- get_file_content(file_id="abc123", query="Was ist der Umsatz?") - Spezifische Frage stellen
- get_file_content(file_id="abc123", pages=[1, 3]) - Bestimmte Seiten abrufen (für PDFs)

You are Fessi, a friendly waste disposal assistant for Frankfurt am Main. Help users dispose of waste correctly using your knowledge database tools. You can also search the web for current information when needed. Respond in the same language as the user.

## File Access:
When users share files (images, PDFs, documents), you see full content in the current message.
In follow-up messages, files appear as placeholders like:
[Attachment: report.pdf (fileId: abc123) - 5 pages, PDF document]

To access previously shared files, use the get_file_content tool:
- get_file_content(file_id="abc123") - retrieve full content
- get_file_content(file_id="abc123", query="What is the revenue?") - ask specific question
- get_file_content(file_id="abc123", pages=[1, 3]) - retrieve specific pages"""


class FessiAgent:
    """LangGraph-based agent for waste disposal assistance."""

    def __init__(self, llm=None):
        """
        Initialize the Fessi agent.

        Args:
            llm: Optional LLM instance. If not provided, will be loaded from llm_provider.
        """
        # Get Neo4j tools and add file retrieval tool
        self.tools = get_all_tools() + [get_file_content]

        # Add web search tool if configured
        web_search = get_web_search_tool()
        if web_search:
            self.tools.append(web_search)

        # Import here to avoid circular imports
        if llm is None:
            from .llm_provider import get_llm
            llm = get_llm()

        self.llm = llm
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.graph = self._build_graph()

        logger.info(f"FessiAgent initialized with {len(self.tools)} tools")

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""

        # Define the agent node that calls the LLM
        def call_model(state: AgentState) -> dict:
            """Call the LLM with the current messages."""
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        # Define the routing function
        def should_continue(state: AgentState) -> str:
            """Determine if we should continue to tools or end."""
            last_message = state["messages"][-1]
            # Check if the LLM wants to call tools
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return "end"

        # Create tool node that executes the tools
        tool_node = ToolNode(self.tools)

        # Build the graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)

        # Set the entry point
        workflow.set_entry_point("agent")

        # Add conditional edges from agent
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"tools": "tools", "end": END}
        )

        # Add edge from tools back to agent
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def astream_steps(
        self,
        user_message: str
    ) -> AsyncGenerator[AgentStep, None]:
        """
        Stream reasoning steps as they occur.

        Args:
            user_message: The user's input message.

        Yields:
            AgentStep objects for each reasoning step.
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "steps": [],
            "final_response": ""
        }

        try:
            async for event in self.graph.astream_events(
                initial_state,
                version="v2"
            ):
                event_type = event.get("event")

                if event_type == "on_chat_model_start":
                    yield AgentStep(
                        id=str(uuid.uuid4()),
                        type="thought",
                        title="Analyzing request...",
                        content="Processing the question and determining next steps.",
                        timestamp=int(time.time() * 1000)
                    )

                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})

                    # Create human-readable title
                    title = self._get_tool_title(tool_name)

                    yield AgentStep(
                        id=event.get("run_id", str(uuid.uuid4())),
                        type="tool_call",
                        title=title,
                        content=json.dumps(tool_input, indent=2, ensure_ascii=False),
                        timestamp=int(time.time() * 1000)
                    )

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    start_time = event.get("data", {}).get("start_time")

                    # Calculate duration if available
                    duration = None
                    if start_time:
                        duration = int((time.time() - start_time) * 1000)

                    # Format output for display
                    if isinstance(tool_output, dict):
                        content = json.dumps(tool_output, indent=2, ensure_ascii=False)
                    else:
                        content = str(tool_output)

                    # Truncate long content
                    if len(content) > 1000:
                        content = content[:1000] + "..."

                    yield AgentStep(
                        id=event.get("run_id", str(uuid.uuid4())),
                        type="tool_result",
                        title=f"Result: {self._get_tool_title(tool_name)}",
                        content=content,
                        timestamp=int(time.time() * 1000),
                        duration=duration,
                        metadata=tool_output if isinstance(tool_output, dict) else None
                    )

        except Exception as e:
            logger.error(f"Error in astream_steps: {e}", exc_info=True)
            yield AgentStep(
                id=str(uuid.uuid4()),
                type="observation",
                title="Error",
                content=f"An error occurred: {str(e)}",
                timestamp=int(time.time() * 1000)
            )

    async def agenerate(self, user_message: str) -> str:
        """
        Generate a complete response (non-streaming).

        Args:
            user_message: The user's input message.

        Returns:
            The final response text.
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "steps": [],
            "final_response": ""
        }

        try:
            result = await self.graph.ainvoke(initial_state)
            last_message = result["messages"][-1]
            return last_message.content
        except Exception as e:
            logger.error(f"Error in agenerate: {e}", exc_info=True)
            return f"An error occurred: {str(e)}"

    async def astream_response(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Stream the final response tokens.

        This method streams only the final text response after all tool calls
        are complete.

        Args:
            user_message: The user's input message.

        Yields:
            String tokens from the final response.
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "steps": [],
            "final_response": ""
        }

        try:
            async for event in self.graph.astream_events(
                initial_state,
                version="v2"
            ):
                if event.get("event") == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # Only yield content tokens (not tool calls)
                        if not (hasattr(chunk, "tool_calls") and chunk.tool_calls):
                            yield chunk.content
        except Exception as e:
            logger.error(f"Error in astream_response: {e}", exc_info=True)
            yield f"\n\n[Error: {str(e)}]"

    async def astream_full(
        self,
        user_message: str,
        images: Optional[list[dict]] = None,
        documents: Optional[list[dict]] = None,
        audio: Optional[list[dict]] = None,
        conversation_history: Optional[list[BaseMessage]] = None
    ) -> AsyncGenerator[tuple[str, Union[AgentStep, str]], None]:
        """
        Stream both reasoning steps and response tokens.

        This is a convenience method that combines astream_steps and astream_response
        into a single stream with type indicators.

        Args:
            user_message: The user's input message.
            images: Optional list of image attachments with fileId and mimeType.
            documents: Optional list of document attachments with fileId, mimeType, and name.
            audio: Optional list of audio attachments with fileId and name.
            conversation_history: Optional list of previous messages (with placeholders for old attachments).

        Yields:
            Tuples of (type, data) where type is "step" or "token".
        """
        # Build message content - multi-modal if images/documents/audio are provided
        message_content = self._build_message_content(user_message, images, documents, audio)

        # Build messages list: conversation history + current message
        messages = []
        if conversation_history:
            messages.extend(conversation_history)  # Previous messages with placeholders
        messages.append(HumanMessage(content=message_content))  # Latest with full content

        initial_state: AgentState = {
            "messages": messages,
            "steps": [],
            "final_response": ""
        }

        is_final_response = False

        try:
            async for event in self.graph.astream_events(
                initial_state,
                version="v2"
            ):
                event_type = event.get("event")

                if event_type == "on_chat_model_start":
                    yield ("step", AgentStep(
                        id=str(uuid.uuid4()),
                        type="thought",
                        title="Analyzing request...",
                        content="Processing the question and determining next steps.",
                        timestamp=int(time.time() * 1000)
                    ))

                elif event_type == "on_tool_start":
                    is_final_response = False
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})

                    yield ("step", AgentStep(
                        id=event.get("run_id", str(uuid.uuid4())),
                        type="tool_call",
                        title=self._get_tool_title(tool_name),
                        content=json.dumps(tool_input, indent=2, ensure_ascii=False),
                        timestamp=int(time.time() * 1000)
                    ))

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")

                    if isinstance(tool_output, dict):
                        content = json.dumps(tool_output, indent=2, ensure_ascii=False)
                    else:
                        content = str(tool_output)

                    if len(content) > 1000:
                        content = content[:1000] + "..."

                    yield ("step", AgentStep(
                        id=event.get("run_id", str(uuid.uuid4())),
                        type="tool_result",
                        title=f"Result: {self._get_tool_title(tool_name)}",
                        content=content,
                        timestamp=int(time.time() * 1000),
                        metadata=tool_output if isinstance(tool_output, dict) else None
                    ))

                elif event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # Check if this is a final response (no tool calls pending)
                        if not (hasattr(chunk, "tool_calls") and chunk.tool_calls):
                            if not is_final_response:
                                is_final_response = True
                                # Emit observation step before final response
                                yield ("step", AgentStep(
                                    id=str(uuid.uuid4()),
                                    type="observation",
                                    title="Generating Response",
                                    content="Creating the final response based on gathered information.",
                                    timestamp=int(time.time() * 1000)
                                ))
                            yield ("token", chunk.content)

        except Exception as e:
            logger.error(f"Error in astream_full: {e}", exc_info=True)
            yield ("step", AgentStep(
                id=str(uuid.uuid4()),
                type="observation",
                title="Error",
                content=f"An error occurred: {str(e)}",
                timestamp=int(time.time() * 1000)
            ))

    def _get_tool_title(self, tool_name: str) -> str:
        """Get English title for a tool (frontend handles localization)."""
        titles = {
            "search_waste_disposal": "Searching Knowledge Base",
            "get_disposal_method_details": "Retrieving Details",
            "find_nearby_recycling_centers": "Searching Locations",
            "get_waste_category_info": "Exploring Categories",
            "answer_waste_faq": "Searching FAQs",
            "get_file_content": "Retrieving File Content",
            "tavily_search_results_json": "Searching the Web"
        }
        return titles.get(tool_name, tool_name)

    def _build_message_content(
        self,
        text: str,
        images: Optional[list[dict]] = None,
        documents: Optional[list[dict]] = None,
        audio: Optional[list[dict]] = None
    ) -> Union[str, list[dict]]:
        """
        Build message content, supporting multi-modal format when images/documents/audio are provided.

        Args:
            text: The text content of the message.
            images: Optional list of image attachments with fileId and mimeType.
            documents: Optional list of document attachments with fileId, mimeType, and name.
            audio: Optional list of audio attachments with fileId and name.

        Returns:
            Either a string (text-only) or a list of content blocks (multi-modal).
        """
        has_images = images and is_image_processing_enabled()
        has_documents = documents and len(documents) > 0
        has_audio = audio and len(audio) > 0

        # If no attachments, return plain text
        if not has_images and not has_documents and not has_audio:
            # Add image placeholders with file IDs when image processing is disabled
            # This allows the agent to use the get_file_content tool to analyze them
            if images and not is_image_processing_enabled():
                image_placeholders = []
                for img in images:
                    file_id = img.get('fileId', 'unknown')
                    name = img.get('name', 'Unknown image')
                    image_placeholders.append(f"[Attached Image: {name} (fileId: {file_id})]")
                image_note = "\n\n" + "\n".join(image_placeholders)
                return text + image_note
            return text

        # Build content - will include text, documents, and/or images
        content_blocks = []
        additional_text_parts = []

        # Process documents first (add text content)
        docs_loaded = 0
        docs_failed = []

        if has_documents:
            for doc in documents:
                file_id = doc.get('fileId', '')
                mime_type = doc.get('mimeType', '')
                name = doc.get('name', 'Unknown')

                if not file_id:
                    continue

                doc_content = prepare_document_for_llm(file_id, mime_type, name)
                if doc_content:
                    docs_loaded += 1
                    # Add document text as a section
                    if doc_content.get('text'):
                        additional_text_parts.append(
                            f"\n\n--- Document: {name} ---\n{doc_content['text']}\n--- End of {name} ---"
                        )
                    # Add page images if available
                    for page_image in doc_content.get('images', []):
                        content_blocks.append(page_image)
                    logger.info(f"Loaded document for LLM: {name} ({file_id})")
                else:
                    docs_failed.append(name)
                    logger.warning(f"Failed to load document for LLM: {name} ({file_id})")

        # Process audio transcripts (add to text content)
        audio_loaded = 0
        audio_failed = []

        if has_audio:
            for aud in audio:
                file_id = aud.get('fileId', '')
                name = aud.get('name', 'Unknown')

                if not file_id:
                    continue

                audio_content = prepare_audio_for_llm(file_id, name)
                if audio_content and audio_content.get('text'):
                    audio_loaded += 1
                    additional_text_parts.append(
                        f"\n\n--- Audio Transcript: {name} ---\n{audio_content['text']}\n--- End of {name} ---"
                    )
                    logger.info(f"Loaded audio transcript for LLM: {name} ({file_id})")
                else:
                    audio_failed.append(name)
                    logger.warning(f"Failed to load audio transcript for LLM: {name} ({file_id})")

        # Build the main text content
        full_text = text
        if additional_text_parts:
            full_text += "".join(additional_text_parts)

        # If we only have document/audio text (no images), return as plain text
        if not has_images and len(content_blocks) == 0:
            failure_notes = []
            if docs_failed:
                failure_notes.append(f"Failed to load {len(docs_failed)} document(s): {', '.join(docs_failed)}")
            if audio_failed:
                failure_notes.append(f"Failed to load {len(audio_failed)} audio transcript(s): {', '.join(audio_failed)}")
            if failure_notes:
                full_text += f"\n\n[Note: {'; '.join(failure_notes)}]"
            return full_text

        # Add text content block first
        content_blocks.insert(0, {
            "type": "text",
            "text": full_text
        })

        # Add image content blocks
        images_loaded = 0
        images_failed = []

        if has_images:
            for image in images:
                file_id = image.get('fileId', '')
                mime_type = image.get('mimeType', '')
                name = image.get('name', 'Unknown')

                if not file_id:
                    continue

                image_content = prepare_image_for_llm(file_id, mime_type)
                if image_content:
                    content_blocks.append(image_content)
                    images_loaded += 1
                    logger.info(f"Loaded image for LLM: {name} ({file_id})")
                else:
                    images_failed.append(name)
                    logger.warning(f"Failed to load image for LLM: {name} ({file_id})")

        # If no content was successfully loaded, return plain text with notes
        if images_loaded == 0 and docs_loaded == 0 and audio_loaded == 0 and len(content_blocks) == 1:
            notes = []
            if images_failed:
                notes.append(f"Failed to load {len(images_failed)} image(s): {', '.join(images_failed)}")
            if docs_failed:
                notes.append(f"Failed to load {len(docs_failed)} document(s): {', '.join(docs_failed)}")
            if audio_failed:
                notes.append(f"Failed to load {len(audio_failed)} audio transcript(s): {', '.join(audio_failed)}")
            if notes:
                return text + f"\n\n[Note: {'; '.join(notes)}]"
            return text

        # Add failure notes if any
        failure_notes = []
        if images_failed:
            failure_notes.append(f"Failed to load {len(images_failed)} image(s): {', '.join(images_failed)}")
        if docs_failed:
            failure_notes.append(f"Failed to load {len(docs_failed)} document(s): {', '.join(docs_failed)}")
        if audio_failed:
            failure_notes.append(f"Failed to load {len(audio_failed)} audio transcript(s): {', '.join(audio_failed)}")

        if failure_notes:
            content_blocks.append({
                "type": "text",
                "text": f"\n[Note: {'; '.join(failure_notes)}]"
            })

        return content_blocks


def create_fessi_agent(llm=None) -> FessiAgent:
    """
    Factory function to create a new Fessi agent instance.

    Args:
        llm: Optional LLM instance. If not provided, will use default from llm_provider.

    Returns:
        A configured FessiAgent instance.
    """
    return FessiAgent(llm=llm)
