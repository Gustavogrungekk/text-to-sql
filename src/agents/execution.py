"""Execution Agent — runs validated SQL on AWS Athena via boto3."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import boto3

from src.config import AthenaConfig
from src.logger import log_agent_action
from src.state import AgentState, ExecutionResult


def _wait_for_query(client, execution_id: str, max_wait: int = 300) -> Dict[str, Any]:
    """Poll Athena until query completes or fails."""
    elapsed = 0
    while elapsed < max_wait:
        resp = client.get_query_execution(QueryExecutionId=execution_id)
        status = resp["QueryExecution"]["Status"]["State"]
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return resp
        time.sleep(2)
        elapsed += 2
    raise TimeoutError(f"Athena query {execution_id} timed out after {max_wait}s")


def _get_results(client, execution_id: str, max_rows: int = 10000) -> tuple[List[str], List[Dict[str, Any]]]:
    """Fetch results from a completed Athena query."""
    paginator = client.get_paginator("get_query_results")
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count = 0

    for page in paginator.paginate(QueryExecutionId=execution_id):
        if not columns:
            columns = [
                col["Label"] for col in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]

        for i, row in enumerate(page["ResultSet"]["Rows"]):
            # Skip header row (first row of first page)
            if row_count == 0 and i == 0:
                continue
            values = [field.get("VarCharValue", "") for field in row["Data"]]
            rows.append(dict(zip(columns, values)))
            row_count += 1
            if row_count >= max_rows:
                return columns, rows

    return columns, rows


def execute_query(state: AgentState, athena_config: AthenaConfig | None = None, client=None) -> AgentState:
    """Execute the validated SQL on Athena."""
    athena_config = athena_config or AthenaConfig()

    if not state.generated_sql:
        state.error = "Nenhum SQL para executar."
        return state

    start_time = time.time()

    try:
        if client is None:
            client = boto3.client("athena", region_name=athena_config.region)

        response = client.start_query_execution(
            QueryString=state.generated_sql,
            ResultConfiguration={"OutputLocation": athena_config.output_bucket},
            WorkGroup=athena_config.workgroup,
        )
        execution_id = response["QueryExecutionId"]

        completion = _wait_for_query(client, execution_id)
        status = completion["QueryExecution"]["Status"]["State"]

        if status != "SUCCEEDED":
            reason = completion["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
            state.execution = ExecutionResult(
                success=False,
                error=reason,
                query_execution_id=execution_id,
            )
            state.agent_logs.append(
                log_agent_action("execution", "failed", {"error": reason})
            )
            return state

        stats = completion["QueryExecution"].get("Statistics", {})
        bytes_scanned = stats.get("DataScannedInBytes", 0)

        columns, rows = _get_results(client, execution_id)

        elapsed_ms = int((time.time() - start_time) * 1000)

        state.execution = ExecutionResult(
            success=True,
            data=rows,
            columns=columns,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            query_execution_id=execution_id,
            bytes_scanned=bytes_scanned,
        )

        state.agent_logs.append(
            log_agent_action("execution", "succeeded", {
                "row_count": len(rows),
                "bytes_scanned": bytes_scanned,
                "execution_time_ms": elapsed_ms,
            })
        )

    except Exception as e:
        state.execution = ExecutionResult(success=False, error=str(e))
        state.agent_logs.append(
            log_agent_action("execution", "exception", {"error": str(e)})
        )

    return state
