"""Tests for the Visualization Agent."""

import json

import pytest

from src.agents.visualization import generate_visualization
from src.state import AgentState, ExecutionResult


class TestVisualization:
    def test_recommends_bar_chart(self, mock_llm, state_with_execution):
        """Agente de visualização recomenda gráfico de barras para dados categóricos."""
        state_with_execution.visualization_requested = True
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": True,
            "chart_type": "bar",
            "reasoning": "Comparação categórica de tipos de evento",
            "chart_config": {
                "x": "event_type",
                "y": "total",
                "title": "Eventos por Tipo",
            },
        })

        result = generate_visualization(state_with_execution, mock_llm)

        assert result.visualization is not None
        assert result.visualization.should_visualize is True
        assert result.visualization.chart_type == "bar"
        assert result.visualization.chart_json is not None

    def test_chart_config_structure(self, mock_llm, state_with_execution):
        """Configuração do gráfico contém campos Plotly obrigatórios."""
        state_with_execution.visualization_requested = True
        config = {
            "x": "event_type",
            "y": "total",
            "title": "Eventos por Tipo",
        }
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": True,
            "chart_type": "bar",
            "reasoning": "comparação",
            "chart_config": config,
        })

        result = generate_visualization(state_with_execution, mock_llm)

        parsed = json.loads(result.visualization.chart_json)
        assert "x" in parsed
        assert "y" in parsed
        assert "title" in parsed

    def test_no_chart_when_not_requested(self, mock_llm, state_with_execution):
        """Agente não gera gráfico quando não solicitado pelo usuário."""
        state_with_execution.visualization_requested = False
        result = generate_visualization(state_with_execution, mock_llm)

        assert result.visualization.should_visualize is False

    def test_no_chart_for_single_row(self, mock_llm):
        """Agente pula gráfico para resultado de linha única."""
        state = AgentState(user_message="me mostre um gráfico")
        state.visualization_requested = True
        state.execution = ExecutionResult(
            success=True,
            data=[{"count": "42"}],
            columns=["count"],
            row_count=1,
        )

        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": False,
            "chart_type": "",
            "reasoning": "Valor único, gráfico não necessário",
            "chart_config": None,
        })

        result = generate_visualization(state, mock_llm)

        assert result.visualization.should_visualize is False

    def test_no_chart_without_data(self, mock_llm):
        """Agente lida com ausência de dados de execução."""
        state = AgentState(user_message="test")
        result = generate_visualization(state, mock_llm)

        assert result.visualization.should_visualize is False

    def test_supports_line_chart(self, mock_llm, state_with_execution):
        """Agente pode recomendar gráficos de linha."""
        state_with_execution.visualization_requested = True
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": True,
            "chart_type": "line",
            "reasoning": "Dados de série temporal",
            "chart_config": {"x": "event_type", "y": "total", "title": "Tendência"},
        })

        result = generate_visualization(state_with_execution, mock_llm)
        assert result.visualization.chart_type == "line"

    def test_specific_chart_type_requested(self, mock_llm, state_with_execution):
        """Quando o usuário pede tipo específico, o agente usa esse tipo."""
        state_with_execution.visualization_requested = True
        state_with_execution.requested_chart_type = "pizza"
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": True,
            "chart_type": "pie",
            "reasoning": "Usuário solicitou gráfico de pizza",
            "chart_config": {"names": "event_type", "values": "total", "title": "Distribuição"},
        })

        result = generate_visualization(state_with_execution, mock_llm)
        assert result.visualization.chart_type == "pie"

    def test_agent_log_created(self, mock_llm, state_with_execution):
        """Agente de visualização cria log."""
        state_with_execution.visualization_requested = True
        mock_llm.set_response("especialista em visualiza", {
            "should_visualize": False, "chart_type": "", "reasoning": "não",
            "chart_config": None,
        })
        result = generate_visualization(state_with_execution, mock_llm)
        assert any(log["agent"] == "visualization" for log in result.agent_logs)
