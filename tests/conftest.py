"""Shared test fixtures and mocks."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.config import AppConfig, AthenaConfig, GuardrailsConfig, LLMConfig
from src.llm_client import LLMClient
from src.state import AgentState


class MockLLMClient:
    """Deterministic mock for LLMClient that returns pre-configured responses."""

    def __init__(self, responses: Dict[str, Any] | None = None):
        self._responses = responses or {}
        self._call_count = 0
        self._calls: List[Dict[str, Any]] = []

    def set_response(self, key: str, value: Any):
        self._responses[key] = value

    def set_default_response(self, value: Any):
        self._responses["__default__"] = value

    def chat(self, system_prompt: str, user_message: str, **kwargs) -> str:
        self._call_count += 1
        self._calls.append({
            "method": "chat",
            "system_prompt": system_prompt[:100],
            "user_message": user_message[:100],
        })
        # Try to match by keyword in system_prompt
        for key, val in self._responses.items():
            if key != "__default__" and key.lower() in system_prompt.lower():
                return val if isinstance(val, str) else json.dumps(val)
        default = self._responses.get("__default__", "")
        return default if isinstance(default, str) else json.dumps(default)

    def chat_json(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        self._call_count += 1
        self._calls.append({
            "method": "chat_json",
            "system_prompt": system_prompt[:100],
            "user_message": user_message[:100],
        })
        for key, val in self._responses.items():
            if key != "__default__" and key.lower() in system_prompt.lower():
                return val if isinstance(val, dict) else json.loads(val)
        default = self._responses.get("__default__", {})
        return default if isinstance(default, dict) else json.loads(default)


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def app_config():
    return AppConfig(
        athena=AthenaConfig(
            output_bucket="s3://test-bucket/",
            workgroup="test",
            region="us-east-1",
        ),
        llm=LLMConfig(api_key="test-key"),
        guardrails=GuardrailsConfig(
            default_limit=100,
            max_limit=1000,
            retry_attempts=3,
        ),
    )


@pytest.fixture
def base_state():
    return AgentState(
        user_message="Show me the top 10 events by count for January 2024",
        conversation_history=[],
    )


@pytest.fixture
def state_with_routing(base_state):
    from src.state import RoutingResult
    base_state.routing = RoutingResult(
        database="analytics",
        tables=["events"],
        reasoning="User wants event data",
    )
    return base_state


@pytest.fixture
def state_with_schema(state_with_routing):
    from src.state import SchemaContext
    state_with_routing.schema_context = SchemaContext(
        columns={
            "events": [
                {"name": "event_id", "type": "STRING", "description": "Unique event identifier"},
                {"name": "user_id", "type": "STRING", "description": "User identifier"},
                {"name": "event_type", "type": "STRING", "description": "Type of event"},
                {"name": "event_timestamp", "type": "TIMESTAMP", "description": "When the event occurred"},
                {"name": "dt", "type": "STRING", "description": "Partition key"},
            ]
        },
        examples=[
            "SELECT event_type, COUNT(*) AS total FROM analytics.events WHERE dt = '2024-01-15' GROUP BY event_type ORDER BY total DESC LIMIT 10"
        ],
        business_rules=[
            "Always filter partitioned tables by the 'dt' partition column.",
            "Event types include: click, view, purchase, signup.",
        ],
        partitions={"events": ["dt"]},
    )
    return state_with_routing


@pytest.fixture
def state_with_sql(state_with_schema):
    state_with_schema.generated_sql = (
        "SELECT event_type, COUNT(*) AS total "
        "FROM analytics.events "
        "WHERE dt BETWEEN '2024-01-01' AND '2024-01-31' "
        "GROUP BY event_type "
        "ORDER BY total DESC "
        "LIMIT 10"
    )
    state_with_schema.sql_attempt = 1
    return state_with_schema


@pytest.fixture
def state_with_execution(state_with_sql):
    from src.state import ExecutionResult
    state_with_sql.execution = ExecutionResult(
        success=True,
        data=[
            {"event_type": "view", "total": "15230"},
            {"event_type": "click", "total": "8745"},
            {"event_type": "purchase", "total": "3210"},
            {"event_type": "signup", "total": "1890"},
        ],
        columns=["event_type", "total"],
        row_count=4,
        execution_time_ms=1250,
        query_execution_id="test-query-123",
        bytes_scanned=52428800,
    )
    return state_with_sql


@pytest.fixture
def mock_athena_client():
    """Mock boto3 Athena client."""
    client = MagicMock()

    client.start_query_execution.return_value = {
        "QueryExecutionId": "test-exec-001"
    }

    client.get_query_execution.return_value = {
        "QueryExecution": {
            "Status": {"State": "SUCCEEDED"},
            "Statistics": {"DataScannedInBytes": 1024000},
        }
    }

    client.get_paginator.return_value.paginate.return_value = [
        {
            "ResultSet": {
                "ResultSetMetadata": {
                    "ColumnInfo": [
                        {"Label": "event_type"},
                        {"Label": "total"},
                    ]
                },
                "Rows": [
                    {"Data": [{"VarCharValue": "event_type"}, {"VarCharValue": "total"}]},
                    {"Data": [{"VarCharValue": "view"}, {"VarCharValue": "15230"}]},
                    {"Data": [{"VarCharValue": "click"}, {"VarCharValue": "8745"}]},
                ],
            }
        }
    ]

    return client
