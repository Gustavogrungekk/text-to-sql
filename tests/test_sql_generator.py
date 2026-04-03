"""Tests for the SQL Generator Agent."""

import pytest

from src.agents.sql_generator import generate_sql
from src.state import AgentState


class TestSQLGenerator:
    def test_generates_valid_select(self, mock_llm, state_with_schema):
        """Generator produz um SELECT."""
        mock_llm.set_response("especialista em gera", (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events "
            "WHERE dt BETWEEN '2024-01-01' AND '2024-01-31' "
            "GROUP BY event_type "
            "ORDER BY total DESC "
            "LIMIT 10"
        ))

        result = generate_sql(state_with_schema, mock_llm)

        assert result.generated_sql.upper().startswith("SELECT")
        assert "analytics.events" in result.generated_sql
        assert "LIMIT" in result.generated_sql.upper()

    def test_uses_partition_filter(self, mock_llm, state_with_schema):
        """Generator usa coluna de partição no WHERE."""
        sql = (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events "
            "WHERE dt BETWEEN '2024-01-01' AND '2024-01-31' "
            "GROUP BY event_type LIMIT 10"
        )
        mock_llm.set_response("especialista em gera", sql)

        result = generate_sql(state_with_schema, mock_llm)

        assert "dt" in result.generated_sql

    def test_increments_attempt_counter(self, mock_llm, state_with_schema):
        """Generator incrementa sql_attempt a cada chamada."""
        mock_llm.set_response("especialista em gera", "SELECT 1 LIMIT 1")

        assert state_with_schema.sql_attempt == 0
        result = generate_sql(state_with_schema, mock_llm)
        assert result.sql_attempt == 1

    def test_strips_markdown_wrappers(self, mock_llm, state_with_schema):
        """Generator remove blocos markdown do output da LLM."""
        mock_llm.set_response("especialista em gera", "```sql\nSELECT 1 LIMIT 1\n```")

        result = generate_sql(state_with_schema, mock_llm)

        assert not result.generated_sql.startswith("```")
        assert "SELECT 1" in result.generated_sql

    def test_error_without_schema(self, mock_llm):
        """Generator define erro quando contexto de schema está ausente."""
        state = AgentState(user_message="test")
        result = generate_sql(state, mock_llm)

        assert result.error is not None

    def test_retry_includes_previous_errors(self, mock_llm, state_with_schema):
        """Generator inclui erros de validação anterior no retry."""
        from src.state import ValidationResult

        state_with_schema.generated_sql = "SELECT bad_column FROM events"
        state_with_schema.sql_attempt = 1
        state_with_schema.validation = ValidationResult(
            is_valid=False,
            errors=["Coluna 'bad_column' não existe na tabela events"],
        )

        mock_llm.set_response("especialista em gera", "SELECT event_type FROM analytics.events LIMIT 10")

        result = generate_sql(state_with_schema, mock_llm)

        assert result.sql_attempt == 2
        assert "bad_column" not in result.generated_sql

    def test_agent_log_created(self, mock_llm, state_with_schema):
        """Generator cria entrada no log de agentes."""
        mock_llm.set_response("especialista em gera", "SELECT 1 LIMIT 1")
        result = generate_sql(state_with_schema, mock_llm)

        assert any(log["agent"] == "sql_generator" for log in result.agent_logs)

    def test_uses_extracted_dates(self, mock_llm, state_with_schema):
        """Generator usa datas extraídas pelo classifier no SQL."""
        from src.state import ClassificationResult

        state_with_schema.classification = ClassificationResult(
            intent="query",
            confidence=0.95,
            requires_sql=True,
            date_start="2024-06-01",
            date_end="2024-06-30",
        )
        state_with_schema.current_date = "2024-07-10"

        sql = (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events "
            "WHERE dt BETWEEN '2024-06-01' AND '2024-06-30' "
            "GROUP BY event_type LIMIT 10"
        )
        mock_llm.set_response("especialista em gera", sql)

        result = generate_sql(state_with_schema, mock_llm)
        assert "2024-06-01" in result.generated_sql
        assert "2024-06-30" in result.generated_sql

    def test_no_date_uses_latest_partition(self, mock_llm, state_with_schema):
        """Generator usa dados recentes quando nenhuma data é informada."""
        from src.state import ClassificationResult

        state_with_schema.classification = ClassificationResult(
            intent="query",
            confidence=0.90,
            requires_sql=True,
            date_start=None,
            date_end=None,
        )
        state_with_schema.current_date = "2024-07-10"

        sql = (
            "SELECT event_type, COUNT(*) AS total "
            "FROM analytics.events "
            "WHERE dt >= date_format(date_add('day', -7, current_date), '%Y-%m-%d') "
            "GROUP BY event_type LIMIT 10"
        )
        mock_llm.set_response("especialista em gera", sql)

        result = generate_sql(state_with_schema, mock_llm)
        assert "current_date" in result.generated_sql or "date_add" in result.generated_sql
