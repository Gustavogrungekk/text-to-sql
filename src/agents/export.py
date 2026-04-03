"""Export Agent — exports query results to CSV, XLSX, or JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from src.config import GuardrailsConfig
from src.logger import log_agent_action
from src.state import AgentState, ExportResult

EXPORT_DIR = Path("exports")


def export_data(state: AgentState, guardrails: GuardrailsConfig | None = None) -> AgentState:
    """Export execution results in the requested format."""
    guardrails = guardrails or GuardrailsConfig()

    if not state.execution or not state.execution.success:
        state.error = "Nenhum resultado de execução bem-sucedida para exportar."
        return state

    fmt = state.export_format.lower().strip()
    if fmt not in ("csv", "xlsx", "json"):
        state.error = f"Formato de exportação não suportado: {fmt}. Use csv, xlsx ou json."
        return state

    data = state.execution.data[: guardrails.max_export_rows]
    df = pd.DataFrame(data)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"export_{state.execution.query_execution_id or 'result'}.{fmt}"
    filepath = EXPORT_DIR / filename

    if fmt == "csv":
        df.to_csv(filepath, index=False, encoding="utf-8")
    elif fmt == "xlsx":
        df.to_excel(filepath, index=False, engine="openpyxl")
    elif fmt == "json":
        df.to_json(filepath, orient="records", force_ascii=False, indent=2)

    state.export = ExportResult(
        format=fmt,
        file_path=str(filepath),
        row_count=len(df),
    )

    state.agent_logs.append(
        log_agent_action("export", "exported", {
            "format": fmt,
            "rows": len(df),
            "path": str(filepath),
        })
    )
    return state
