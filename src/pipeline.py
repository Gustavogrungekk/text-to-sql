"""LangGraph orchestrator — defines the agent pipeline graph."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.agents.classifier import classify
from src.agents.empty_result_analyzer import analyze_empty_result
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
from src.knowledge.loader import load_catalog_snapshot
from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DB_SEP_RE = re.compile(r"[_\-.]+")


def _normalize_for_match(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def _normalize_db_name(db_name: str) -> str:
    return _normalize_for_match(_DB_SEP_RE.sub(" ", db_name))


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

    def empty_result_node(state: AgentState) -> AgentState:
        return analyze_empty_result(state, llm)

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
            if state.execution.row_count == 0:
                return "empty_analysis"
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
    graph.add_node("empty_analysis", empty_result_node)
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
        "empty_analysis": "empty_analysis",
        "respond": "respond",
    })

    graph.add_edge("empty_analysis", "respond")

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

    def _invoke_graph(
        self,
        user_message: str,
        conversation_history: list[Dict[str, str]],
        export_requested: bool,
        export_format: str,
        visualization_requested: bool,
        requested_chart_type: str,
        preferred_database: str,
        forced_database: str = "",
        catalog_metadata: Dict[str, Any] | None = None,
    ) -> AgentState:
        initial_state = AgentState(
            user_message=user_message,
            conversation_history=conversation_history,
            export_requested=export_requested,
            export_format=export_format,
            visualization_requested=visualization_requested,
            requested_chart_type=requested_chart_type,
            preferred_database=preferred_database,
            forced_database=forced_database,
            catalog_metadata=catalog_metadata or {},
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

        final_state = self._graph.invoke(initial_state)

        if isinstance(final_state, dict):
            return AgentState(**final_state)
        return final_state

    def _extract_explicit_databases(
        self,
        user_message: str,
        catalog: Dict[str, Any],
    ) -> list[str]:
        available_databases = list(catalog.get("databases", {}).keys())
        if len(available_databases) < 2:
            return []

        normalized_msg = _normalize_for_match(user_message)
        matches: list[str] = []
        for db_name in available_databases:
            normalized_db = _normalize_db_name(db_name)
            if not normalized_db:
                continue
            pattern = rf"\b{re.escape(normalized_db)}\b"
            if re.search(pattern, normalized_msg):
                matches.append(db_name)
        return matches

    def _run_multi_database(
        self,
        user_message: str,
        conversation_history: list[Dict[str, str]],
        requested_databases: list[str],
        catalog_metadata: Dict[str, Any],
        preferred_database: str,
        export_requested: bool,
        export_format: str,
        visualization_requested: bool,
        requested_chart_type: str,
    ) -> AgentState:
        sub_states: list[AgentState] = []
        for db_name in requested_databases:
            sub_state = self._invoke_graph(
                user_message=user_message,
                conversation_history=conversation_history,
                export_requested=False,
                export_format="",
                visualization_requested=False,
                requested_chart_type="",
                preferred_database=db_name,
                forced_database=db_name,
                catalog_metadata=catalog_metadata,
            )
            sub_states.append(sub_state)

        multi_results: list[Dict[str, Any]] = []
        response_parts = [
            "Detectei uma consulta multi-base e executei uma query separada por banco.",
            "No Athena, cada execucao aceita apenas um statement SQL, entao esse fluxo evita o uso de queries encadeadas com ';'.",
        ]

        combined_logs: list[Dict[str, Any]] = []
        for idx, sub_state in enumerate(sub_states):
            expected_db = requested_databases[idx]
            routing = sub_state.routing
            selected_db = routing.database if routing else expected_db
            selected_tables = routing.tables if routing else []
            execution_success = bool(sub_state.execution and sub_state.execution.success)

            result_item = {
                "database": selected_db,
                "tables": selected_tables,
                "sql": sub_state.generated_sql,
                "success": execution_success,
                "error": sub_state.error or (sub_state.execution.error if sub_state.execution else ""),
                "row_count": sub_state.execution.row_count if sub_state.execution else 0,
                "execution_time_ms": sub_state.execution.execution_time_ms if sub_state.execution else 0,
                "bytes_scanned": sub_state.execution.bytes_scanned if sub_state.execution else 0,
                "data": sub_state.execution.data if sub_state.execution else [],
                "columns": sub_state.execution.columns if sub_state.execution else [],
                "insights": sub_state.insight.insights if sub_state.insight else [],
                "summary": sub_state.insight.summary if sub_state.insight else "",
            }
            multi_results.append(result_item)
            combined_logs.extend(sub_state.agent_logs)

            section_lines = [f"### Banco `{selected_db}`"]
            if selected_tables:
                section_lines.append(f"Tabelas selecionadas: {', '.join(selected_tables)}.")
            if sub_state.generated_sql:
                section_lines.append(f"```sql\n{sub_state.generated_sql}\n```")
            if execution_success and sub_state.execution:
                section_lines.append(
                    f"Resultado: {sub_state.execution.row_count} linhas em {sub_state.execution.execution_time_ms} ms."
                )
                if sub_state.insight and sub_state.insight.summary:
                    section_lines.append(f"Resumo: {sub_state.insight.summary}")
            elif sub_state.error:
                section_lines.append(f"Erro: {sub_state.error}")
            elif sub_state.execution and sub_state.execution.error:
                section_lines.append(f"Erro na execucao: {sub_state.execution.error}")
            else:
                section_lines.append("Nao foi possivel concluir essa base.")

            response_parts.append("\n".join(section_lines))

        if export_requested or visualization_requested:
            response_parts.append(
                "Observacao: exportacao e visualizacao automatica foram desabilitadas no modo multi-base. "
                "Se precisar desses artefatos, rode por banco individualmente."
            )

        final_state = AgentState(
            user_message=user_message,
            conversation_history=conversation_history,
            export_requested=export_requested,
            export_format=export_format,
            visualization_requested=visualization_requested,
            requested_chart_type=requested_chart_type,
            preferred_database=preferred_database,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            catalog_metadata=catalog_metadata,
            multi_database_mode=True,
            multi_db_results=multi_results,
            final_response="\n\n".join(response_parts),
        )

        representative = next(
            (s for s in sub_states if s.execution and s.execution.success),
            sub_states[0] if sub_states else None,
        )
        if representative:
            final_state.classification = representative.classification
            final_state.routing = representative.routing
            final_state.schema_context = representative.schema_context
            final_state.generated_sql = representative.generated_sql
            final_state.sql_attempt = representative.sql_attempt
            final_state.validation = representative.validation
            final_state.execution = representative.execution
            final_state.insight = representative.insight
            final_state.visualization = representative.visualization
            final_state.export = representative.export

        final_state.agent_logs = combined_logs
        final_state.agent_logs.append(
            log_agent_action(
                "multi_database_orchestrator",
                "completed",
                {
                    "databases": requested_databases,
                    "total_queries": len(requested_databases),
                    "successes": sum(1 for item in multi_results if item["success"]),
                },
            )
        )
        return final_state

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
        history = conversation_history or []
        catalog_metadata = load_catalog_snapshot(self._config)
        explicit_databases = self._extract_explicit_databases(
            user_message,
            catalog_metadata,
        )

        if len(explicit_databases) > 1:
            return self._run_multi_database(
                user_message=user_message,
                conversation_history=history,
                requested_databases=explicit_databases,
                catalog_metadata=catalog_metadata,
                preferred_database=preferred_database,
                export_requested=export_requested,
                export_format=export_format,
                visualization_requested=visualization_requested,
                requested_chart_type=requested_chart_type,
            )

        return self._invoke_graph(
            user_message=user_message,
            conversation_history=history,
            export_requested=export_requested,
            export_format=export_format,
            visualization_requested=visualization_requested,
            requested_chart_type=requested_chart_type,
            preferred_database=preferred_database,
            catalog_metadata=catalog_metadata,
        )
