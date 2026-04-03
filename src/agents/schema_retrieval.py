"""Schema Retrieval Agent — gathers schema context for SQL generation."""

from __future__ import annotations

from src.config import AppConfig
from src.knowledge.loader import (
    get_business_rules,
    get_partitions,
    get_sql_examples,
    get_table_schema,
    load_catalog_snapshot,
)
from src.logger import log_agent_action
from src.state import AgentState, SchemaContext


def retrieve_schema(state: AgentState, config: AppConfig | None = None) -> AgentState:
    """Retrieve schema, examples, and business rules for routed tables."""
    if not state.routing:
        state.error = "No routing result available for schema retrieval."
        return state

    db = state.routing.database
    tables = state.routing.tables

    columns: dict = {}
    partitions: dict = {}
    all_examples: list = []
    rules: list = get_business_rules(db)

    catalog = state.catalog_metadata or load_catalog_snapshot(config)
    state.catalog_metadata = catalog

    for table in tables:
        schema = get_table_schema(db, table, catalog=catalog)
        columns[table] = schema.get("columns", [])
        partitions[table] = get_partitions(db, table, catalog=catalog)
        all_examples.extend(get_sql_examples(db, table))

    # Deduplicate examples
    all_examples = list(dict.fromkeys(all_examples))

    state.schema_context = SchemaContext(
        columns=columns,
        examples=all_examples,
        business_rules=rules,
        partitions=partitions,
    )

    state.agent_logs.append(
        log_agent_action("schema_retrieval", "retrieved", {
            "tables": tables,
            "num_examples": len(all_examples),
            "num_rules": len(rules),
        })
    )
    return state
