"""Tests for the SQL Validator Agent."""

import pytest

from src.agents.sql_validator import validate_sql
from src.config import GuardrailsConfig
from src.state import AgentState, ValidationResult


class TestSQLValidator:
    def test_valid_query_passes(self, mock_llm, state_with_sql):
        """SQL válido passa na validação."""
        mock_llm.set_response("agente de valida", {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "corrected_sql": None,
        })

        result = validate_sql(state_with_sql, mock_llm)

        assert result.validation is not None
        assert result.validation.is_valid is True
        assert len(result.validation.errors) == 0

    def test_detects_dangerous_operations(self, mock_llm, state_with_schema):
        """Validator bloqueia DROP, DELETE, INSERT, etc."""
        state_with_schema.generated_sql = "DROP TABLE analytics.events"
        result = validate_sql(state_with_schema, mock_llm)

        assert result.validation.is_valid is False
        assert any("perigosa" in e.lower() for e in result.validation.errors)

    def test_detects_non_select(self, mock_llm, state_with_schema):
        """Validator bloqueia statements que não são SELECT."""
        state_with_schema.generated_sql = "INSERT INTO analytics.events VALUES ('a', 'b')"
        result = validate_sql(state_with_schema, mock_llm)

        assert result.validation.is_valid is False

    def test_warns_on_missing_limit(self, mock_llm, state_with_schema):
        """Validator avisa e auto-adiciona LIMIT quando ausente."""
        state_with_schema.generated_sql = (
            "SELECT event_type FROM analytics.events WHERE dt = '2024-01-01'"
        )

        mock_llm.set_response("agente de valida", {
            "is_valid": True,
            "errors": [],
            "warnings": ["Sem cláusula LIMIT"],
            "corrected_sql": (
                "SELECT event_type FROM analytics.events "
                "WHERE dt = '2024-01-01' LIMIT 100"
            ),
        })

        result = validate_sql(state_with_schema, mock_llm)

        assert "LIMIT" in result.generated_sql.upper()

    def test_empty_sql_fails(self, mock_llm, state_with_schema):
        """Validator rejeita SQL vazio."""
        state_with_schema.generated_sql = ""
        result = validate_sql(state_with_schema, mock_llm)

        assert result.validation.is_valid is False
        assert any("vazio" in e.lower() for e in result.validation.errors)

    def test_llm_correction_applied(self, mock_llm, state_with_schema):
        """Validator aplica correções da LLM."""
        state_with_schema.generated_sql = "SELECT evnt_type FROM analytics.events LIMIT 10"

        mock_llm.set_response("agente de valida", {
            "is_valid": False,
            "errors": ["Coluna 'evnt_type' não encontrada"],
            "warnings": [],
            "corrected_sql": "SELECT event_type FROM analytics.events LIMIT 10",
        })

        result = validate_sql(state_with_schema, mock_llm)

        assert result.validation.is_valid is True
        assert "event_type" in result.generated_sql

    def test_auto_limit_with_guardrails(self, mock_llm, state_with_schema):
        """Validator auto-adiciona LIMIT baseado na config de guardrails."""
        guardrails = GuardrailsConfig(default_limit=50, require_limit=True)
        state_with_schema.generated_sql = (
            "SELECT event_type FROM analytics.events WHERE dt = '2024-01-01'"
        )

        mock_llm.set_response("agente de valida", {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "corrected_sql": None,
        })

        result = validate_sql(state_with_schema, mock_llm, guardrails)

        assert "LIMIT 50" in result.generated_sql

    def test_agent_log_created(self, mock_llm, state_with_sql):
        """Validator cria entradas no log de agentes."""
        mock_llm.set_response("agente de valida", {
            "is_valid": True, "errors": [], "warnings": [], "corrected_sql": None,
        })

        result = validate_sql(state_with_sql, mock_llm)
        assert any(log["agent"] == "sql_validator" for log in result.agent_logs)
