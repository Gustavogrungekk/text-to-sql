"""End-to-end tests for the full pipeline."""

import json

import pytest

from src.config import AppConfig, AthenaConfig, GuardrailsConfig, LLMConfig
from src.state import AgentState


# We mock the entire pipeline by mocking the LLM and Athena client at the agent level.
# This tests the LangGraph orchestration flow.


class TestEndToEnd:
    def test_greeting_flow(self, mock_llm):
        """Fluxo completo: saudação -> resposta."""
        from src.agents.classifier import classify
        from src.agents.response_composer import compose_response

        mock_llm.set_response("classificador de inten", {
            "intent": "greeting",
            "confidence": 0.99,
            "requires_sql": False,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Olá!")
        state = classify(state, mock_llm)
        state = compose_response(state, mock_llm)

        assert "Olá" in state.final_response or "olá" in state.final_response.lower()
        assert state.generated_sql == ""

    def test_out_of_scope_flow(self, mock_llm):
        """Fluxo completo: fora de escopo -> resposta."""
        from src.agents.classifier import classify
        from src.agents.response_composer import compose_response

        mock_llm.set_response("classificador de inten", {
            "intent": "out_of_scope",
            "confidence": 0.95,
            "requires_sql": False,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Como está o clima?")
        state = classify(state, mock_llm)
        state = compose_response(state, mock_llm)

        assert "escopo" in state.final_response.lower() or "fora" in state.final_response.lower()

    def test_clarification_flow(self, mock_llm):
        """Fluxo completo: consulta ambígua -> pedir clarificação."""
        from src.agents.classifier import classify
        from src.agents.response_composer import compose_response

        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.4,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": True,
            "clarification_message": "Qual período de datas você deseja consultar?",
        })

        state = AgentState(user_message="Me mostre os dados")
        state = classify(state, mock_llm)
        state = compose_response(state, mock_llm)

        assert "período" in state.final_response.lower() or "datas" in state.final_response.lower()

    def test_full_query_flow(self, mock_llm, mock_athena_client):
        """Fluxo completo: query -> roteamento -> schema -> gerar -> validar -> executar -> insight -> visualizar -> resposta."""
        from src.agents.classifier import classify
        from src.agents.execution import execute_query
        from src.agents.insight import generate_insights
        from src.agents.response_composer import compose_response
        from src.agents.router import route
        from src.agents.schema_retrieval import retrieve_schema
        from src.agents.sql_generator import generate_sql
        from src.agents.sql_validator import validate_sql
        from src.agents.visualization import generate_visualization
        from src.config import AthenaConfig

        # Setup mocks
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.95,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
            "date_start": "2024-01-01",
            "date_end": "2024-01-31",
        })
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["events"],
            "reasoning": "consulta de dados de eventos",
        })
        mock_llm.set_response("especialista em gera", (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events "
            "WHERE dt BETWEEN '2024-01-01' AND '2024-01-31' "
            "GROUP BY event_type ORDER BY total DESC LIMIT 10"
        ))
        mock_llm.set_response("agente de valida", {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "corrected_sql": None,
        })
        mock_llm.set_response("analista de insights", {
            "explanation": "A distribuição de eventos mostra views como dominante.",
            "insights": ["Views representam a maioria dos eventos."],
            "summary": "Views lideram todos os tipos de eventos.",
        })
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": True,
            "chart_type": "bar",
            "reasoning": "comparação categórica",
            "chart_config": {"x": "event_type", "y": "total", "title": "Eventos"},
        })
        mock_llm.set_response("assistente analista", "Aqui estão os principais eventos de janeiro de 2024.")

        state = AgentState(user_message="Me mostre os principais eventos em janeiro de 2024 com gráfico")
        state.visualization_requested = True
        state.current_date = "2024-03-15"

        # Execute pipeline manually
        state = classify(state, mock_llm)
        assert state.classification.requires_sql is True
        assert state.classification.date_start == "2024-01-01"
        assert state.classification.date_end == "2024-01-31"

        state = route(state, mock_llm)
        assert state.routing.database == "analytics"

        state = retrieve_schema(state)
        assert state.schema_context is not None

        state = generate_sql(state, mock_llm)
        assert state.generated_sql != ""

        state = validate_sql(state, mock_llm)
        assert state.validation.is_valid is True

        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")
        state = execute_query(state, config, client=mock_athena_client)
        assert state.execution.success is True

        state = generate_insights(state, mock_llm)
        assert len(state.insight.insights) >= 1

        state = generate_visualization(state, mock_llm)
        assert state.visualization.should_visualize is True

        state = compose_response(state, mock_llm)
        assert state.final_response != ""

    def test_sql_retry_flow(self, mock_llm, mock_athena_client):
        """Testa retry de geração SQL após falha na validação."""
        from src.agents.classifier import classify
        from src.agents.router import route
        from src.agents.schema_retrieval import retrieve_schema
        from src.agents.sql_generator import generate_sql
        from src.agents.sql_validator import validate_sql

        mock_llm.set_response("classificador de inten", {
            "intent": "query", "confidence": 0.95, "requires_sql": True,
            "is_follow_up": False, "needs_clarification": False,
            "clarification_message": None,
        })
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics", "tables": ["events"],
            "reasoning": "consulta de eventos",
        })

        state = AgentState(user_message="Contar eventos")
        state = classify(state, mock_llm)
        state = route(state, mock_llm)
        state = retrieve_schema(state)

        # Primeira tentativa — SQL inválido
        mock_llm.set_response("especialista em gera", "SELECT bad_col FROM analytics.events LIMIT 10")
        state = generate_sql(state, mock_llm)
        assert state.sql_attempt == 1

        mock_llm.set_response("agente de valida", {
            "is_valid": False,
            "errors": ["Coluna 'bad_col' não existe na tabela events"],
            "warnings": [],
            "corrected_sql": None,
        })
        state = validate_sql(state, mock_llm)
        assert state.validation.is_valid is False

        # Retry — SQL válido
        mock_llm.set_response("especialista em gera", (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events WHERE dt = '2024-01-01' "
            "GROUP BY event_type LIMIT 10"
        ))
        state = generate_sql(state, mock_llm)
        assert state.sql_attempt == 2

        mock_llm.set_response("agente de valida", {
            "is_valid": True, "errors": [], "warnings": [], "corrected_sql": None,
        })
        state = validate_sql(state, mock_llm)
        assert state.validation.is_valid is True

    def test_export_flow(self, mock_llm):
        """Tests the export flow after execution."""
        from src.agents.export import export_data
        from src.state import ExecutionResult

        state = AgentState(
            user_message="export as csv",
            export_requested=True,
            export_format="csv",
        )
        state.execution = ExecutionResult(
            success=True,
            data=[{"col1": "a", "col2": "b"}],
            columns=["col1", "col2"],
            row_count=1,
            query_execution_id="e2e-export-test",
        )

        state = export_data(state)

        assert state.export is not None
        assert state.export.format == "csv"
        assert state.export.row_count == 1

        # Cleanup
        from pathlib import Path
        Path(state.export.file_path).unlink(missing_ok=True)

    def test_full_pipeline_produces_logs(self, mock_llm, mock_athena_client):
        """Pipeline completo produz logs de agentes a cada etapa."""
        from src.agents.classifier import classify
        from src.agents.execution import execute_query
        from src.agents.insight import generate_insights
        from src.agents.router import route
        from src.agents.schema_retrieval import retrieve_schema
        from src.agents.sql_generator import generate_sql
        from src.agents.sql_validator import validate_sql
        from src.config import AthenaConfig

        mock_llm.set_response("classificador de inten", {
            "intent": "query", "confidence": 0.95, "requires_sql": True,
            "is_follow_up": False, "needs_clarification": False,
            "clarification_message": None,
        })
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics", "tables": ["events"], "reasoning": "q",
        })
        mock_llm.set_response("especialista em gera", "SELECT 1 FROM analytics.events WHERE dt='2024-01-01' LIMIT 1")
        mock_llm.set_response("agente de valida", {
            "is_valid": True, "errors": [], "warnings": [], "corrected_sql": None,
        })
        mock_llm.set_response("analista de insights", {
            "explanation": "t", "insights": ["i"], "summary": "s",
        })

        state = AgentState(user_message="test query")
        state = classify(state, mock_llm)
        state = route(state, mock_llm)
        state = retrieve_schema(state)
        state = generate_sql(state, mock_llm)
        state = validate_sql(state, mock_llm)
        state = execute_query(state, AthenaConfig(output_bucket="s3://t/", workgroup="t"), client=mock_athena_client)
        state = generate_insights(state, mock_llm)

        agents_logged = {log["agent"] for log in state.agent_logs}
        assert "classifier" in agents_logged
        assert "router" in agents_logged
        assert "schema_retrieval" in agents_logged
        assert "sql_generator" in agents_logged
        assert "sql_validator" in agents_logged
        assert "execution" in agents_logged
        assert "insight" in agents_logged
