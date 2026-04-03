"""Tests for Pipeline multi-database orchestration."""

from __future__ import annotations

from src.config import AppConfig, LLMConfig
from src.pipeline import Pipeline
from src.state import AgentState, ExecutionResult, InsightResult, RoutingResult


class DummyLLM:
    def chat(self, *args, **kwargs):
        return ""

    def chat_json(self, *args, **kwargs):
        return {}


def _catalog_two_dbs():
    return {
        "databases": {
            "analytics": {"tables": {"events": {"columns": []}}},
            "sales": {"tables": {"orders": {"columns": []}}},
        }
    }


def test_extract_explicit_databases_matches_multiple_names():
    pipeline = Pipeline(config=AppConfig(llm=LLMConfig(api_key="test")), llm=DummyLLM())
    catalog = _catalog_two_dbs()

    result = pipeline._extract_explicit_databases(
        "Me traga dados da analytics e tambem da sales",
        catalog,
    )

    assert result == ["analytics", "sales"]


def test_run_multi_database_executes_one_query_per_database(monkeypatch):
    pipeline = Pipeline(config=AppConfig(llm=LLMConfig(api_key="test")), llm=DummyLLM())
    calls: list[dict] = []

    monkeypatch.setattr("src.pipeline.load_catalog_snapshot", lambda config: _catalog_two_dbs())

    def fake_invoke_graph(**kwargs):
        calls.append(kwargs)
        db = kwargs["forced_database"]

        state = AgentState(user_message=kwargs["user_message"])
        state.routing = RoutingResult(database=db, tables=["events"], reasoning="forced")
        state.generated_sql = f"SELECT * FROM {db}.events LIMIT 10"
        state.execution = ExecutionResult(
            success=True,
            data=[{"source": db, "value": "1"}],
            columns=["source", "value"],
            row_count=1,
            execution_time_ms=10,
            query_execution_id=f"q-{db}",
            bytes_scanned=128,
        )
        state.insight = InsightResult(
            explanation="ok",
            insights=[f"Insight {db}"],
            summary=f"Resumo {db}",
        )
        state.agent_logs = [{"agent": "fake"}]
        return state

    monkeypatch.setattr(pipeline, "_invoke_graph", fake_invoke_graph)

    result = pipeline.run(
        user_message="Me traga analytics e sales",
        conversation_history=[],
        export_requested=True,
        visualization_requested=True,
    )

    assert result.multi_database_mode is True
    assert [c["forced_database"] for c in calls] == ["analytics", "sales"]
    assert len(result.multi_db_results) == 2
    assert "query separada por banco" in result.final_response
    assert "exportacao e visualizacao automatica foram desabilitadas" in result.final_response


def test_run_single_database_keeps_default_flow(monkeypatch):
    pipeline = Pipeline(config=AppConfig(llm=LLMConfig(api_key="test")), llm=DummyLLM())

    monkeypatch.setattr("src.pipeline.load_catalog_snapshot", lambda config: _catalog_two_dbs())

    captured: list[dict] = []

    def fake_invoke_graph(**kwargs):
        captured.append(kwargs)
        return AgentState(user_message=kwargs["user_message"], final_response="ok")

    monkeypatch.setattr(pipeline, "_invoke_graph", fake_invoke_graph)

    result = pipeline.run(
        user_message="Me traga apenas analytics",
        conversation_history=[],
        preferred_database="analytics",
    )

    assert result.multi_database_mode is False
    assert len(captured) == 1
    assert captured[0].get("forced_database", "") == ""
    assert captured[0]["preferred_database"] == "analytics"
