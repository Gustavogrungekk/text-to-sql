"""Tests for the Router Agent."""

import pytest

from src.agents.router import route
from src.state import AgentState


class TestRouter:
    def test_routes_to_events_table(self, mock_llm):
        """Router seleciona tabela events para consultas de eventos."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["events"],
            "reasoning": "Usuário pergunta sobre eventos",
        })

        state = AgentState(user_message="Me mostra a contagem de eventos por tipo")
        result = route(state, mock_llm)

        assert result.routing is not None
        assert result.routing.database == "analytics"
        assert "events" in result.routing.tables

    def test_routes_to_transactions(self, mock_llm):
        """Router seleciona tabela transactions para consultas de receita."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["transactions"],
            "reasoning": "Usuário pergunta sobre receita/vendas",
        })

        state = AgentState(user_message="Qual foi a receita total do último mês?")
        result = route(state, mock_llm)

        assert "transactions" in result.routing.tables

    def test_routes_to_multiple_tables(self, mock_llm):
        """Router seleciona múltiplas tabelas para joins."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["transactions", "products"],
            "reasoning": "Join necessário para receita por categoria",
        })

        state = AgentState(user_message="Receita por categoria de produto")
        result = route(state, mock_llm)

        assert len(result.routing.tables) == 2
        assert "transactions" in result.routing.tables
        assert "products" in result.routing.tables

    def test_routing_includes_reasoning(self, mock_llm):
        """Router fornece justificativa para a seleção."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["users"],
            "reasoning": "Consulta sobre perfis de usuários",
        })

        state = AgentState(user_message="Quantos usuários se cadastraram?")
        result = route(state, mock_llm)

        assert result.routing.reasoning != ""

    def test_agent_log_created(self, mock_llm):
        """Router cria entrada no log de agentes."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["events"],
            "reasoning": "consulta de eventos",
        })

        state = AgentState(user_message="Contar eventos")
        result = route(state, mock_llm)

        assert any(log["agent"] == "router" for log in result.agent_logs)

    def test_forced_database_overrides_llm_choice(self, mock_llm):
        """Router respeita forced_database no modo multi-base."""
        mock_llm.set_response("agente de roteamento", {
            "database": "analytics",
            "tables": ["events"],
            "reasoning": "LLM sugeriu analytics",
        })

        state = AgentState(user_message="consulta multi-base", forced_database="sales")
        state.catalog_metadata = {
            "databases": {
                "analytics": {"tables": {"events": {"columns": []}}},
                "sales": {"tables": {"orders": {"columns": []}}},
            }
        }

        result = route(state, mock_llm)

        assert result.routing is not None
        assert result.routing.database == "sales"
