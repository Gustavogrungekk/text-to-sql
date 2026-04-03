"""Router Agent — selects the correct database and tables using LLM."""

from __future__ import annotations

from src.config import AppConfig
from src.knowledge.loader import get_all_metadata_summary, get_tables, load_catalog_snapshot
from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, RoutingResult

SYSTEM_PROMPT = """Você é um agente de roteamento de banco de dados para um sistema Text-to-SQL rodando no AWS Athena.

Dada a pergunta do usuário e os metadados de bancos/tabelas disponíveis abaixo, selecione qual banco de dados e quais tabelas são relevantes para responder à pergunta.

Metadados disponíveis:
{metadata}

Retorne um objeto JSON com:
- database: nome do banco de dados a consultar
- tables: lista de nomes de tabelas necessárias
- reasoning: breve explicação do porquê dessas escolhas

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


def _sanitize_tables(raw_tables: list[str], valid_tables: list[str]) -> list[str]:
    valid_set = set(valid_tables)
    normalized: list[str] = []
    for table in raw_tables:
        if table in valid_set and table not in normalized:
            normalized.append(table)
    return normalized


def route(state: AgentState, llm: LLMClient, config: AppConfig | None = None) -> AgentState:
    """Route the query to the correct database and tables."""
    catalog = state.catalog_metadata or load_catalog_snapshot(config)
    state.catalog_metadata = catalog

    available_databases = list(catalog.get("databases", {}).keys())
    if not available_databases:
        state.error = "Nenhum banco de dados disponível no catálogo para roteamento."
        return state

    metadata = get_all_metadata_summary(
        config=config,
        catalog=catalog,
        preferred_database=state.preferred_database,
    )
    prompt = SYSTEM_PROMPT.format(metadata=metadata or "Catálogo vazio")

    result = llm.chat_json(
        system_prompt=prompt,
        user_message=state.user_message,
    )

    selected_database = result.get("database", "")
    if state.forced_database and state.forced_database in available_databases:
        selected_database = state.forced_database
    elif selected_database not in available_databases:
        if state.preferred_database and state.preferred_database in available_databases:
            selected_database = state.preferred_database
        else:
            selected_database = available_databases[0]

    valid_tables = get_tables(selected_database, catalog=catalog)
    llm_tables = result.get("tables", [])
    if not isinstance(llm_tables, list):
        llm_tables = []
    sanitized_tables = _sanitize_tables(llm_tables, valid_tables)

    if not sanitized_tables and valid_tables:
        user_text = state.user_message.lower()
        mentioned_tables = [
            table for table in valid_tables if table.lower() in user_text
        ]
        sanitized_tables = mentioned_tables[:3] if mentioned_tables else valid_tables[:3]

    routing = RoutingResult(
        database=selected_database,
        tables=sanitized_tables,
        reasoning=result.get("reasoning", ""),
    )

    state.routing = routing
    state.agent_logs.append(
        log_agent_action("router", "routed", {
            "database": routing.database,
            "tables": routing.tables,
            "catalog_databases": len(available_databases),
        })
    )
    return state
