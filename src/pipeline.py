"""LangGraph orchestrator — defines the agent pipeline graph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.agents.classifier import classify
from src.agents.execution import execute_query
from src.agents.export import export_data
from src.agents.insight import generate_insights
from src.agents.response_composer import compose_response
from src.agents.router import route
from src.agents.schema_retrieval import retrieve_schema
from src.agents.sql_generator import generate_sql
from src.agents.sql_validator import validate_sql
from src.agents.visualization import generate_visualization
from src.config import AppConfig, load_config
from src.llm_client import LLMClient
from src.state import AgentState


def _build_graph(config: AppConfig | None = None, llm: LLMClient | None = None):
    """Build and compile the LangGraph state machine."""
    config = config or load_config()
    llm = llm or LLMClient(config.llm)

    # --- Node wrappers ---
    def classifier_node(state: AgentState) -> AgentState:
        return classify(state, llm)

    def router_node(state: AgentState) -> AgentState:
        return route(state, llm, config)

    def schema_node(state: AgentState) -> AgentState:
        return retrieve_schema(state, config)

    def generator_node(state: AgentState) -> AgentState:
        return generate_sql(state, llm)

    def validator_node(state: AgentState) -> AgentState:
        return validate_sql(state, llm, config.guardrails)

    def execution_node(state: AgentState) -> AgentState:
        return execute_query(state, config.athena)

    def insight_node(state: AgentState) -> AgentState:
        return generate_insights(state, llm)

    def visualization_node(state: AgentState) -> AgentState:
        return generate_visualization(state, llm)

    def export_node(state: AgentState) -> AgentState:
        return export_data(state, config.guardrails)

    def response_node(state: AgentState) -> AgentState:
        return compose_response(state, llm)

    # --- Conditional edges ---
    def after_classification(state: AgentState) -> str:
        c = state.classification
        if not c:
            return "respond"
        if c.needs_clarification:
            return "respond"
        if not c.requires_sql:
            return "respond"
        return "route"

    def after_validation(state: AgentState) -> str:
        v = state.validation
        if v and v.is_valid:
            return "execute"
        if state.sql_attempt >= config.guardrails.retry_attempts:
            return "respond"
        return "generate"  # retry

    def after_execution(state: AgentState) -> str:
        if state.execution and state.execution.success:
            return "insight"
        return "respond"

    def after_insight(state: AgentState) -> str:
        if state.visualization_requested:
            return "visualize"
        if state.export_requested:
            return "export"
        return "respond"

    def after_visualization(state: AgentState) -> str:
        if state.export_requested:
            return "export"
        return "respond"

    def after_export(state: AgentState) -> str:
        return "respond"

    # --- Build graph ---
    graph = StateGraph(AgentState)

    graph.add_node("classify", classifier_node)
    graph.add_node("route", router_node)
    graph.add_node("schema", schema_node)
    graph.add_node("generate", generator_node)
    graph.add_node("validate", validator_node)
    graph.add_node("execute", execution_node)
    graph.add_node("insight", insight_node)
    graph.add_node("visualize", visualization_node)
    graph.add_node("export", export_node)
    graph.add_node("respond", response_node)

    graph.set_entry_point("classify")

    graph.add_conditional_edges("classify", after_classification, {
        "route": "route",
        "respond": "respond",
    })

    graph.add_edge("route", "schema")
    graph.add_edge("schema", "generate")
    graph.add_edge("generate", "validate")

    graph.add_conditional_edges("validate", after_validation, {
        "execute": "execute",
        "generate": "generate",
        "respond": "respond",
    })

    graph.add_conditional_edges("execute", after_execution, {
        "insight": "insight",
        "respond": "respond",
    })

    graph.add_conditional_edges("insight", after_insight, {
        "visualize": "visualize",
        "export": "export",
        "respond": "respond",
    })

    graph.add_conditional_edges("visualize", after_visualization, {
        "export": "export",
        "respond": "respond",
    })

    graph.add_edge("export", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


class Pipeline:
    """High-level pipeline interface wrapping the LangGraph graph."""

    def __init__(self, config: AppConfig | None = None, llm: LLMClient | None = None):
        self._config = config or load_config()
        self._llm = llm or LLMClient(self._config.llm)
        self._graph = _build_graph(self._config, self._llm)

    def run(
        self,
        user_message: str,
        conversation_history: list[Dict[str, str]] | None = None,
        export_requested: bool = False,
        export_format: str = "",
        visualization_requested: bool = False,
        requested_chart_type: str = "",
        preferred_database: str = "",
    ) -> AgentState:
        """Run the full pipeline and return the final state."""
        initial_state = AgentState(
            user_message=user_message,
            conversation_history=conversation_history or [],
            export_requested=export_requested,
            export_format=export_format,
            visualization_requested=visualization_requested,
            requested_chart_type=requested_chart_type,
            preferred_database=preferred_database,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

        final_state = self._graph.invoke(initial_state)

        # LangGraph may return a dict; convert back to AgentState
        if isinstance(final_state, dict):
            return AgentState(**final_state)
        return final_state
