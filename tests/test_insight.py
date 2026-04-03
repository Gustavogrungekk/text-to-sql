"""Tests for the Insight Agent."""

import pytest

from src.agents.insight import generate_insights
from src.state import AgentState, ExecutionResult


class TestInsight:
    def test_generates_insights(self, mock_llm, state_with_execution):
        """Insight agent gera insights significativos."""
        mock_llm.set_response("analista de insights", {
            "explanation": "Os dados mostram distribuição de eventos por tipo.",
            "insights": [
                "Views dominam com 15.230 (53% do total)",
                "Compras representam 11% — considere melhorar a conversão",
            ],
            "summary": "Views são o tipo de evento dominante com signups ficando atrás.",
        })

        result = generate_insights(state_with_execution, mock_llm)

        assert result.insight is not None
        assert result.insight.explanation != ""
        assert len(result.insight.insights) >= 1
        assert result.insight.summary != ""

    def test_no_insights_on_failure(self, mock_llm):
        """Insight agent lida com execução falhada."""
        state = AgentState(user_message="test")
        state.execution = ExecutionResult(success=False, error="Consulta falhou")

        result = generate_insights(state, mock_llm)

        assert result.insight is not None
        assert "Sem dados" in result.insight.summary or "não foi bem-sucedida" in result.insight.explanation

    def test_insights_reference_data(self, mock_llm, state_with_execution):
        """Insights referenciam números reais dos resultados."""
        mock_llm.set_response("analista de insights", {
            "explanation": "Eventos de view totalizam 15.230, maior entre todos os tipos.",
            "insights": [
                "15.230 views vs 3.210 compras mostra um grande drop-off",
            ],
            "summary": "Alta contagem de views mas baixa conversão em compras.",
        })

        result = generate_insights(state_with_execution, mock_llm)

        assert "15.230" in result.insight.explanation or "15230" in result.insight.explanation

    def test_no_execution_result(self, mock_llm):
        """Insight agent lida com resultado de execução None."""
        state = AgentState(user_message="test")
        result = generate_insights(state, mock_llm)

        assert result.insight is not None

    def test_agent_log_created(self, mock_llm, state_with_execution):
        """Insight agent cria log de agente."""
        mock_llm.set_response("analista de insights", {
            "explanation": "teste", "insights": ["um"], "summary": "s",
        })

        result = generate_insights(state_with_execution, mock_llm)
        assert any(log["agent"] == "insight" for log in result.agent_logs)
