"""Tests for the Classifier Agent."""

import pytest

from src.agents.classifier import classify
from src.state import AgentState


class TestClassifier:
    def test_query_intent(self, mock_llm):
        """Classifier identifica intenção de consulta."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.95,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Me mostra o total de vendas por região no último mês")
        result = classify(state, mock_llm)

        assert result.classification is not None
        assert result.classification.intent == "query"
        assert result.classification.requires_sql is True
        assert result.classification.confidence >= 0.9

    def test_greeting_intent(self, mock_llm):
        """Classifier identifica saudação."""
        mock_llm.set_response("classificador de inten", {
            "intent": "greeting",
            "confidence": 0.99,
            "requires_sql": False,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Olá!")
        result = classify(state, mock_llm)

        assert result.classification.intent == "greeting"
        assert result.classification.requires_sql is False

    def test_follow_up_intent(self, mock_llm):
        """Classifier detecta follow-up."""
        mock_llm.set_response("classificador de inten", {
            "intent": "follow_up",
            "confidence": 0.88,
            "requires_sql": True,
            "is_follow_up": True,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(
            user_message="Agora filtra só por desktop",
            conversation_history=[
                {"role": "user", "content": "Mostra eventos por tipo de dispositivo"},
                {"role": "assistant", "content": "Aqui estão os eventos..."},
            ],
        )
        result = classify(state, mock_llm)

        assert result.classification.is_follow_up is True
        assert result.classification.requires_sql is True

    def test_needs_clarification(self, mock_llm):
        """Classifier pede esclarecimento em consultas ambíguas."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.4,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": True,
            "clarification_message": "Qual período de tempo você está se referindo?",
        })

        state = AgentState(user_message="Me mostra os dados")
        result = classify(state, mock_llm)

        assert result.classification.needs_clarification is True
        assert result.classification.clarification_message is not None

    def test_out_of_scope(self, mock_llm):
        """Classifier bloqueia requisições fora do escopo."""
        mock_llm.set_response("classificador de inten", {
            "intent": "out_of_scope",
            "confidence": 0.92,
            "requires_sql": False,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Como está o tempo hoje?")
        result = classify(state, mock_llm)

        assert result.classification.intent == "out_of_scope"
        assert result.classification.requires_sql is False

    def test_export_intent(self, mock_llm):
        """Classifier identifica intenção de exportação."""
        mock_llm.set_response("classificador de inten", {
            "intent": "export",
            "confidence": 0.93,
            "requires_sql": True,
            "is_follow_up": True,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Exporta isso em CSV")
        result = classify(state, mock_llm)

        assert result.classification.intent == "export"

    def test_visualization_intent(self, mock_llm):
        """Classifier identifica pedido explícito de gráfico."""
        mock_llm.set_response("classificador de inten", {
            "intent": "visualization",
            "confidence": 0.95,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": "chart_type:bar",
        })

        state = AgentState(user_message="Me faz um gráfico de barras das vendas por região")
        result = classify(state, mock_llm)

        assert result.classification.intent == "visualization"
        assert result.classification.requires_sql is True

    def test_agent_log_created(self, mock_llm):
        """Classifier cria entrada no log de agentes."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.9,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Contar usuários")
        result = classify(state, mock_llm)

        assert len(result.agent_logs) == 1
        assert result.agent_logs[0]["agent"] == "classifier"

    def test_extracts_explicit_date_range(self, mock_llm):
        """Classifier extrai período de datas explícito da pergunta."""
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

        state = AgentState(
            user_message="Me mostra as vendas de janeiro de 2024",
            current_date="2024-03-15",
        )
        result = classify(state, mock_llm)

        assert result.classification.date_start == "2024-01-01"
        assert result.classification.date_end == "2024-01-31"

    def test_extracts_relative_date(self, mock_llm):
        """Classifier calcula datas relativas como 'últimos 7 dias'."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.93,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
            "date_start": "2024-03-08",
            "date_end": "2024-03-15",
        })

        state = AgentState(
            user_message="Eventos dos últimos 7 dias",
            current_date="2024-03-15",
        )
        result = classify(state, mock_llm)

        assert result.classification.date_start == "2024-03-08"
        assert result.classification.date_end == "2024-03-15"

    def test_no_date_returns_null(self, mock_llm):
        """Classifier retorna null quando nenhuma data é mencionada."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.90,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
            "date_start": None,
            "date_end": None,
        })

        state = AgentState(user_message="Quantos eventos por tipo?")
        result = classify(state, mock_llm)

        assert result.classification.date_start is None
        assert result.classification.date_end is None

    def test_current_date_set_on_state(self, mock_llm):
        """Classifier preenche current_date no state se vazio."""
        mock_llm.set_response("classificador de inten", {
            "intent": "greeting",
            "confidence": 0.99,
            "requires_sql": False,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
        })

        state = AgentState(user_message="Olá")
        result = classify(state, mock_llm)

        assert result.current_date != ""

    def test_date_in_agent_log(self, mock_llm):
        """Classifier inclui datas extraídas no log."""
        mock_llm.set_response("classificador de inten", {
            "intent": "query",
            "confidence": 0.95,
            "requires_sql": True,
            "is_follow_up": False,
            "needs_clarification": False,
            "clarification_message": None,
            "date_start": "2024-06-01",
            "date_end": "2024-06-30",
        })

        state = AgentState(user_message="Vendas de junho 2024", current_date="2024-07-01")
        result = classify(state, mock_llm)

        log = result.agent_logs[0]
        assert log["details"]["date_start"] == "2024-06-01"
        assert log["details"]["date_end"] == "2024-06-30"
