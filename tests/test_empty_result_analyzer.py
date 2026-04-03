"""Tests for the Empty Result Analyzer agent."""

from __future__ import annotations

import pytest

from src.agents.empty_result_analyzer import analyze_empty_result
from src.state import AgentState, ExecutionResult, SchemaContext


class TestEmptyResultAnalyzer:

    @pytest.fixture
    def state_empty_result(self):
        state = AgentState(
            user_message="Quantas vendas tivemos em fevereiro de 2099?",
            current_date="2026-04-03",
        )
        state.generated_sql = (
            "SELECT COUNT(*) AS total "
            "FROM sales.orders "
            "WHERE dt BETWEEN '2099-02-01' AND '2099-02-28' "
            "LIMIT 100"
        )
        state.execution = ExecutionResult(
            success=True,
            data=[],
            columns=["total"],
            row_count=0,
            execution_time_ms=350,
            query_execution_id="q-empty-1",
            bytes_scanned=1024,
        )
        state.schema_context = SchemaContext(
            columns={
                "orders": [
                    {"name": "order_id", "type": "STRING", "description": "Order ID"},
                    {"name": "amount", "type": "DOUBLE", "description": "Order amount"},
                    {"name": "dt", "type": "STRING", "description": "Partition key"},
                ]
            },
            partitions={"orders": ["dt"]},
            business_rules=["Always filter by dt partition."],
            examples=[],
        )
        return state

    def test_classifies_suspicious_future_date(self, mock_llm, state_empty_result):
        """Analyzer classifica como suspicious quando há filtro de data no futuro."""
        mock_llm.set_response("analista de dados", {
            "classification": "suspicious",
            "reason": "O filtro de data usa o ano 2099, que está no futuro. Não existem dados para esse período.",
            "suggestions": [
                "Verifique o período solicitado — 2099 ainda não chegou.",
                "Tente consultar com datas mais recentes, como 2026 ou 2025.",
            ],
            "filters_analysis": "WHERE dt BETWEEN '2099-02-01' AND '2099-02-28' — período futuro.",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert result.empty_result_analysis.classification == "suspicious"
        assert len(result.empty_result_analysis.suggestions) >= 1
        assert result.empty_result_analysis.reason != ""

    def test_classifies_expected_no_data(self, mock_llm, state_empty_result):
        """Analyzer classifica como expected quando faz sentido não ter dados."""
        state_empty_result.user_message = "Vendas no feriado de natal 2025"
        state_empty_result.generated_sql = (
            "SELECT COUNT(*) AS total FROM sales.orders "
            "WHERE dt = '2025-12-25' LIMIT 100"
        )

        mock_llm.set_response("analista de dados", {
            "classification": "expected",
            "reason": "É plausível que não haja vendas no dia de Natal, pois a loja pode não operar nessa data.",
            "suggestions": [],
            "filters_analysis": "WHERE dt = '2025-12-25' — data específica de feriado.",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert result.empty_result_analysis.classification == "expected"
        assert result.empty_result_analysis.suggestions == []

    def test_classifies_ambiguous(self, mock_llm, state_empty_result):
        """Analyzer classifica como ambiguous quando não tem info suficiente."""
        state_empty_result.user_message = "Dados da tabela X"
        state_empty_result.generated_sql = "SELECT * FROM sales.orders LIMIT 100"

        mock_llm.set_response("analista de dados", {
            "classification": "ambiguous",
            "reason": "A consulta é genérica e não há como determinar se os dados deveriam existir.",
            "suggestions": ["Especifique o período desejado.", "Informe qual tipo de dados procura."],
            "filters_analysis": "Sem filtros WHERE — consulta genérica.",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert result.empty_result_analysis.classification == "ambiguous"
        assert len(result.empty_result_analysis.suggestions) == 2

    def test_skips_when_rows_exist(self, mock_llm, state_empty_result):
        """Analyzer não executa quando há dados retornados."""
        state_empty_result.execution.data = [{"total": "42"}]
        state_empty_result.execution.row_count = 1

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is None

    def test_skips_when_execution_failed(self, mock_llm):
        """Analyzer não executa quando a execução falhou."""
        state = AgentState(user_message="teste")
        state.execution = ExecutionResult(success=False, error="Timeout")

        result = analyze_empty_result(state, mock_llm)

        assert result.empty_result_analysis is None

    def test_skips_when_no_execution(self, mock_llm):
        """Analyzer não executa quando não há resultado de execução."""
        state = AgentState(user_message="teste")

        result = analyze_empty_result(state, mock_llm)

        assert result.empty_result_analysis is None

    def test_invalid_classification_defaults_to_ambiguous(self, mock_llm, state_empty_result):
        """Analyzer normaliza classificações inválidas para 'ambiguous'."""
        mock_llm.set_response("analista de dados", {
            "classification": "invalid_value",
            "reason": "Motivo qualquer.",
            "suggestions": [],
            "filters_analysis": "",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert result.empty_result_analysis.classification == "ambiguous"

    def test_agent_log_created(self, mock_llm, state_empty_result):
        """Analyzer cria um log de agente."""
        mock_llm.set_response("analista de dados", {
            "classification": "expected",
            "reason": "Ok.",
            "suggestions": [],
            "filters_analysis": "",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert any(log["agent"] == "empty_result_analyzer" for log in result.agent_logs)

    def test_analysis_includes_filters_analysis(self, mock_llm, state_empty_result):
        """Analyzer popula o campo filters_analysis."""
        mock_llm.set_response("analista de dados", {
            "classification": "suspicious",
            "reason": "Filtros muito restritivos.",
            "suggestions": ["Remova o filtro de data."],
            "filters_analysis": "WHERE dt BETWEEN '2099-02-01' AND '2099-02-28', JOIN com tabela vazia.",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis.filters_analysis != ""
        assert "2099" in result.empty_result_analysis.filters_analysis

    def test_suggestions_string_normalized_to_list(self, mock_llm, state_empty_result):
        """Analyzer converte suggestions string em lista."""
        mock_llm.set_response("analista de dados", {
            "classification": "suspicious",
            "reason": "Problema.",
            "suggestions": "Tente remover o filtro de data.",
            "filters_analysis": "",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert isinstance(result.empty_result_analysis.suggestions, list)
        assert len(result.empty_result_analysis.suggestions) == 1
        assert result.empty_result_analysis.suggestions[0] == "Tente remover o filtro de data."

    def test_suggestions_invalid_type_normalized_to_empty(self, mock_llm, state_empty_result):
        """Analyzer converte suggestions de tipo inválido em lista vazia."""
        mock_llm.set_response("analista de dados", {
            "classification": "expected",
            "reason": "Ok.",
            "suggestions": 42,
            "filters_analysis": "",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert isinstance(result.empty_result_analysis.suggestions, list)
        assert result.empty_result_analysis.suggestions == []

    def test_suggestions_mixed_types_coerced_to_str(self, mock_llm, state_empty_result):
        """Analyzer converte itens não-string dentro da lista para str."""
        mock_llm.set_response("analista de dados", {
            "classification": "suspicious",
            "reason": "Ok.",
            "suggestions": ["Dica 1", 123, {"nested": True}],
            "filters_analysis": "",
        })

        result = analyze_empty_result(state_empty_result, mock_llm)

        assert result.empty_result_analysis is not None
        assert all(isinstance(s, str) for s in result.empty_result_analysis.suggestions)
        assert len(result.empty_result_analysis.suggestions) == 3
