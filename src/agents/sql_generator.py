"""SQL Generator Agent — generates Athena SQL using LLM + context."""

from __future__ import annotations

import json

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState

SYSTEM_PROMPT = """Você é um especialista em geração de SQL para AWS Athena (dialeto Presto/Trino).

Data atual: {current_date}

Gere uma única consulta SQL que responda à pergunta do usuário usando SOMENTE o schema, exemplos e regras fornecidos abaixo. NÃO invente colunas, tabelas ou dados.

Banco de dados: {database}

Schema:
{schema}

Colunas de partição:
{partitions}

Exemplos de SQL:
{examples}

Regras de negócio:
{rules}

PERÍODO DE DATAS EXTRAÍDO DA PERGUNTA:
{date_context}

Requisitos:
- Use nomes de tabela totalmente qualificados: {database}.nome_tabela
- Sempre inclua uma cláusula LIMIT (padrão 10000, a menos que o usuário especifique outro valor)
- Nunca use LIMIT acima de 10000 linhas
- Sempre filtre tabelas particionadas pela coluna de partição
- Se um período de datas foi extraído (date_start/date_end acima), USE ESSAS DATAS no filtro da coluna de partição
- Se NENHUM período de datas foi informado, traga os dados MAIS RECENTES usando: WHERE coluna_partição >= date_format(date_add('day', -7, current_date), '%Y-%m-%d') para trazer os últimos 7 dias
- Use o dialeto SQL do Athena/Presto
- NÃO use window functions a menos que seja necessário
- Retorne SOMENTE a consulta SQL, sem explicação, sem markdown, sem blocos de código
- A consulta deve ser um único SELECT
"""


def _format_schema(schema_context) -> str:
    lines = []
    for table, cols in schema_context.columns.items():
        lines.append(f"Table: {table}")
        for c in cols:
            lines.append(f"  - {c['name']} ({c['type']}): {c.get('description', '')}")
    return "\n".join(lines)


def _format_partitions(schema_context) -> str:
    lines = []
    for table, parts in schema_context.partitions.items():
        if parts:
            lines.append(f"{table}: {', '.join(parts)}")
    return "\n".join(lines) if lines else "None"


def generate_sql(state: AgentState, llm: LLMClient) -> AgentState:
    """Generate SQL from user question and schema context."""
    if not state.schema_context or not state.routing:
        state.error = "Contexto de schema ou roteamento ausente para geração de SQL."
        return state

    # Build date context from classifier output
    date_start = None
    date_end = None
    if state.classification:
        date_start = state.classification.date_start
        date_end = state.classification.date_end

    if date_start and date_end:
        date_context = f"Período: de {date_start} até {date_end}. Use essas datas no filtro de partição."
    elif date_start:
        date_context = f"Data inicial: {date_start}. Traga dados a partir dessa data."
    elif date_end:
        date_context = f"Data final: {date_end}. Traga dados até essa data."
    else:
        date_context = (
            "NENHUM período de datas foi informado pelo usuário. "
            "Traga os dados MAIS RECENTES. Para tabelas particionadas, "
            "use a partição mais recente. Exemplo: WHERE dt >= date_format(date_add('day', -7, current_date), '%Y-%m-%d')"
        )

    current_date = state.current_date or ""

    prompt = SYSTEM_PROMPT.format(
        database=state.routing.database,
        schema=_format_schema(state.schema_context),
        partitions=_format_partitions(state.schema_context),
        examples="\n".join(state.schema_context.examples[:5]),
        rules="\n".join(state.schema_context.business_rules),
        date_context=date_context,
        current_date=current_date,
    )

    # Include previous validation errors for retry
    user_msg = state.user_message
    if state.validation and not state.validation.is_valid and state.sql_attempt > 0:
        user_msg += f"\n\nA tentativa anterior de SQL falhou na validação com os seguintes erros:\n"
        user_msg += "\n".join(state.validation.errors)
        user_msg += f"\n\nSQL anterior:\n{state.generated_sql}"
        user_msg += "\n\nPor favor, corrija o SQL e tente novamente."

    sql = llm.chat(
        system_prompt=prompt,
        user_message=user_msg,
    ).strip()

    # Clean markdown wrappers if LLM wraps them
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    state.generated_sql = sql.strip()
    state.sql_attempt += 1

    state.agent_logs.append(
        log_agent_action("sql_generator", "generated", {
            "attempt": state.sql_attempt,
            "sql_length": len(state.generated_sql),
        })
    )
    return state
