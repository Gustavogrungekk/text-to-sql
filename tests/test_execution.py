"""Tests for the Execution Agent — uses mocked Athena client."""

import pytest

from src.agents.execution import execute_query
from src.config import AthenaConfig
from src.state import AgentState


class TestExecution:
    def test_successful_execution(self, state_with_sql, mock_athena_client):
        """Execution agent executa query e retorna resultados."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")

        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert result.execution is not None
        assert result.execution.success is True
        assert result.execution.row_count > 0
        assert result.execution.query_execution_id == "test-exec-001"

    def test_returns_correct_columns(self, state_with_sql, mock_athena_client):
        """Execution agent retorna nomes corretos de colunas."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")

        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert result.execution.columns == ["event_type", "total"]

    def test_failed_execution(self, state_with_sql, mock_athena_client):
        """Execution agent lida com falha da query."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")

        mock_athena_client.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {
                    "State": "FAILED",
                    "StateChangeReason": "SYNTAX_ERROR: line 1:1",
                },
            }
        }

        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert result.execution.success is False
        assert result.execution.error is not None

    def test_no_sql_error(self):
        """Execution agent retorna erro quando não há SQL."""
        state = AgentState(user_message="test")
        result = execute_query(state)

        assert result.error is not None

    def test_exception_handling(self, state_with_sql, mock_athena_client):
        """Execution agent lida com exceções do boto3."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")
        mock_athena_client.start_query_execution.side_effect = Exception("Access denied")

        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert result.execution.success is False
        assert "Access denied" in result.execution.error

    def test_bytes_scanned_recorded(self, state_with_sql, mock_athena_client):
        """Execution registra bytes escaneados."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")

        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert result.execution.bytes_scanned == 1024000

    def test_agent_log_created(self, state_with_sql, mock_athena_client):
        """Execution cria entradas no log de agentes."""
        config = AthenaConfig(output_bucket="s3://test/", workgroup="test")
        result = execute_query(state_with_sql, config, client=mock_athena_client)

        assert any(log["agent"] == "execution" for log in result.agent_logs)
