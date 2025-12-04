# backend/services/agent.py
"""
LangGraph-based agent for the Fessi waste disposal assistant.
This agent uses Neo4j tools to answer waste disposal questions with multi-step reasoning.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from typing import TypedDict, Annotated, Sequence, AsyncGenerator, Union, Optional
import operator
import json
import time
import uuid
import logging

from .tools.neo4j_tools import get_all_tools
from ..models.message import AgentStep
from .image_handler import prepare_image_for_llm, is_image_processing_enabled

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

You are Fessi, a friendly waste disposal assistant for Frankfurt am Main. Help users dispose of waste correctly using your knowledge database tools. Respond in the same language as the user."""


class FessiAgent:
    """LangGraph-based agent for waste disposal assistance."""

    def __init__(self, llm=None):
        """
        Initialize the Fessi agent.

        Args:
            llm: Optional LLM instance. If not provided, will be loaded from llm_provider.
        """
        self.tools = get_all_tools()

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
        images: Optional[list[dict]] = None
    ) -> AsyncGenerator[tuple[str, Union[AgentStep, str]], None]:
        """
        Stream both reasoning steps and response tokens.

        This is a convenience method that combines astream_steps and astream_response
        into a single stream with type indicators.

        Args:
            user_message: The user's input message.
            images: Optional list of image attachments with fileId and mimeType.

        Yields:
            Tuples of (type, data) where type is "step" or "token".
        """
        # Build message content - multi-modal if images are provided
        message_content = self._build_message_content(user_message, images)
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message_content)],
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
            "answer_waste_faq": "Searching FAQs"
        }
        return titles.get(tool_name, tool_name)

    def _build_message_content(
        self,
        text: str,
        images: Optional[list[dict]] = None
    ) -> Union[str, list[dict]]:
        """
        Build message content, supporting multi-modal format when images are provided.

        Args:
            text: The text content of the message.
            images: Optional list of image attachments with fileId and mimeType.

        Returns:
            Either a string (text-only) or a list of content blocks (multi-modal).
        """
        # If no images or image processing is disabled, return plain text
        if not images or not is_image_processing_enabled():
            # If images were provided but processing is disabled, add a note
            if images and not is_image_processing_enabled():
                image_count = len(images)
                image_note = f"\n\n[Note: {image_count} image(s) attached but image processing is disabled]"
                return text + image_note
            return text

        # Build multi-modal content
        content_blocks = []

        # Add text content first
        content_blocks.append({
            "type": "text",
            "text": text
        })

        # Add image content blocks
        images_loaded = 0
        images_failed = []

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

        # If no images were successfully loaded, return plain text with note
        if images_loaded == 0:
            if images_failed:
                return text + f"\n\n[Note: Failed to load {len(images_failed)} image(s): {', '.join(images_failed)}]"
            return text

        # If some images failed, add a note
        if images_failed:
            content_blocks.append({
                "type": "text",
                "text": f"\n[Note: Failed to load {len(images_failed)} image(s): {', '.join(images_failed)}]"
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
