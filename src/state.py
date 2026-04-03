"""Shared state model for the LangGraph pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    intent: str = Field(description="Classified intent: query, follow_up, greeting, clarification, export, visualization, out_of_scope")
    confidence: float = Field(ge=0.0, le=1.0)
    requires_sql: bool = False
    is_follow_up: bool = False
    needs_clarification: bool = False
    clarification_message: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None


class RoutingResult(BaseModel):
    database: str = ""
    tables: List[str] = Field(default_factory=list)
    reasoning: str = ""


class SchemaContext(BaseModel):
    columns: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    examples: List[str] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)
    partitions: Dict[str, List[str]] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    is_valid: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    corrected_sql: Optional[str] = None


class ExecutionResult(BaseModel):
    success: bool = False
    data: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    query_execution_id: str = ""
    error: Optional[str] = None
    bytes_scanned: int = 0


class InsightResult(BaseModel):
    explanation: str = ""
    insights: List[str] = Field(default_factory=list)
    summary: str = ""


class VisualizationResult(BaseModel):
    chart_type: str = ""
    chart_json: Optional[str] = None
    reasoning: str = ""
    should_visualize: bool = False


class ExportResult(BaseModel):
    format: str = ""
    file_path: str = ""
    row_count: int = 0


class AgentState(BaseModel):
    """Main state object passed through the LangGraph pipeline."""
    # Input
    user_message: str = ""
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    preferred_database: str = ""
    current_date: str = ""

    # Classification
    classification: Optional[ClassificationResult] = None

    # Catalog snapshot used by router/schema retrieval
    catalog_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Routing
    routing: Optional[RoutingResult] = None

    # Schema
    schema_context: Optional[SchemaContext] = None

    # SQL
    generated_sql: str = ""
    sql_attempt: int = 0

    # Validation
    validation: Optional[ValidationResult] = None

    # Execution
    execution: Optional[ExecutionResult] = None

    # Insight
    insight: Optional[InsightResult] = None

    # Visualization
    visualization: Optional[VisualizationResult] = None

    # Export
    export: Optional[ExportResult] = None
    export_requested: bool = False
    export_format: str = ""

    # Visualization control
    visualization_requested: bool = False
    requested_chart_type: str = ""

    # Response
    final_response: str = ""

    # Control
    error: Optional[str] = None
    agent_logs: List[Dict[str, Any]] = Field(default_factory=list)
