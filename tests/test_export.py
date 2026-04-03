"""Tests for the Export Agent."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src.agents.export import EXPORT_DIR, export_data
from src.config import GuardrailsConfig
from src.state import AgentState, ExecutionResult


@pytest.fixture
def execution_state():
    state = AgentState(user_message="export data")
    state.execution = ExecutionResult(
        success=True,
        data=[
            {"event_type": "view", "total": "15230"},
            {"event_type": "click", "total": "8745"},
            {"event_type": "purchase", "total": "3210"},
        ],
        columns=["event_type", "total"],
        row_count=3,
        query_execution_id="export-test-001",
    )
    return state


@pytest.fixture(autouse=True)
def cleanup_exports():
    """Clean up export files after tests."""
    yield
    if EXPORT_DIR.exists():
        for f in EXPORT_DIR.iterdir():
            if f.name.startswith("export_export-test"):
                f.unlink(missing_ok=True)


class TestExport:
    def test_csv_export(self, execution_state):
        """Export agent creates valid CSV."""
        execution_state.export_format = "csv"
        result = export_data(execution_state)

        assert result.export is not None
        assert result.export.format == "csv"
        assert result.export.row_count == 3
        assert Path(result.export.file_path).exists()

        df = pd.read_csv(result.export.file_path)
        assert len(df) == 3
        assert list(df.columns) == ["event_type", "total"]

    def test_xlsx_export(self, execution_state):
        """Export agent creates valid XLSX."""
        execution_state.export_format = "xlsx"
        result = export_data(execution_state)

        assert result.export.format == "xlsx"
        assert Path(result.export.file_path).exists()

        df = pd.read_excel(result.export.file_path, engine="openpyxl")
        assert len(df) == 3

    def test_json_export(self, execution_state):
        """Export agent creates valid JSON."""
        execution_state.export_format = "json"
        result = export_data(execution_state)

        assert result.export.format == "json"
        assert Path(result.export.file_path).exists()

        with open(result.export.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 3
        assert data[0]["event_type"] == "view"

    def test_unsupported_format(self, execution_state):
        """Agente de exportação rejeita formatos não suportados."""
        execution_state.export_format = "pdf"
        result = export_data(execution_state)

        assert result.error is not None
        assert "não suportado" in result.error

    def test_no_execution_data(self):
        """Export agent handles missing execution data."""
        state = AgentState(user_message="export", export_format="csv")
        result = export_data(state)

        assert result.error is not None

    def test_respects_max_export_rows(self, execution_state):
        """Export respects row limit from guardrails."""
        guardrails = GuardrailsConfig(max_export_rows=2)
        execution_state.export_format = "csv"
        result = export_data(execution_state, guardrails)

        assert result.export.row_count == 2

    def test_data_consistency(self, execution_state):
        """Exported data matches the execution result."""
        execution_state.export_format = "json"
        result = export_data(execution_state)

        with open(result.export.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for i, row in enumerate(data):
            assert row == execution_state.execution.data[i]

    def test_agent_log_created(self, execution_state):
        """Export creates agent log."""
        execution_state.export_format = "csv"
        result = export_data(execution_state)
        assert any(log["agent"] == "export" for log in result.agent_logs)
