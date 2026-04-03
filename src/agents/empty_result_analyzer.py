"""Empty Result Analyzer — classifies why a query returned zero rows and suggests next steps."""

from __future__ import annotations

import json

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, EmptyResultAnalysis

SYSTEM_PROMPT = """Você é um analista de dados experiente. Uma consulta SQL foi executada com sucesso no AWS Athena, mas retornou ZERO linhas.

Sua tarefa é analisar a situação e classificar a causa provável.

Considere:
1. A pergunta original do usuário
2. O SQL gerado (filtros WHERE, JOINs, funções de data, partições)
3. O schema das tabelas disponíveis
4. As regras de negócio aplicáveis

Classifique o resultado vazio em uma das categorias:
- "expected": É plausível que não existam dados para essa combinação de filtros. Exemplo: consultar vendas em um feriado, período muito recente sem ingestão, produto novo sem histórico.
- "suspicious": Há indícios de que filtros excessivos ou incorretos causam o resultado vazio. Exemplo: filtro de data no futuro, JOIN entre tabelas sem relação clara, filtro de partição em formato errado, condição WHERE muito restritiva.
- "ambiguous": Não é possível determinar a causa sem mais contexto do usuário.

Regras:
- NUNCA invente dados ou sugira que existam dados quando não há evidência.
- Seja específico nas sugestões (cite colunas, filtros e valores concretos do SQL).
- Sempre responda em português brasileiro.

Retorne um objeto JSON com:
- classification: string ("expected", "suspicious", "ambiguous")
- reason: string explicando por que classificou assim
- suggestions: lista de strings com sugestões concretas ao usuário (pode ser vazia para "expected")
- filters_analysis: string resumindo os filtros aplicados no SQL

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


def analyze_empty_result(state: AgentState, llm: LLMClient) -> AgentState:
    """Analyze why a query returned zero rows and classify the situation."""
    if not state.execution or not state.execution.success or state.execution.row_count != 0:
        return state

    schema_info = ""
    if state.schema_context:
        schema_info = json.dumps(
            {
                "columns": state.schema_context.columns,
                "partitions": state.schema_context.partitions,
                "business_rules": state.schema_context.business_rules,
            },
            indent=2,
            default=str,
        )

    user_msg = (
        f"Pergunta do usuário: {state.user_message}\n\n"
        f"SQL executado:\n{state.generated_sql}\n\n"
        f"Schema das tabelas:\n{schema_info}\n\n"
        f"Data atual: {state.current_date}\n"
        f"A consulta executou com sucesso mas retornou 0 linhas."
    )

    result = llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
    )

    classification = result.get("classification", "ambiguous")
    if classification not in ("expected", "suspicious", "ambiguous"):
        classification = "ambiguous"

    raw_suggestions = result.get("suggestions", [])
    if isinstance(raw_suggestions, str):
        suggestions = [raw_suggestions] if raw_suggestions else []
    elif isinstance(raw_suggestions, list):
        suggestions = [str(s) for s in raw_suggestions if s]
    else:
        suggestions = []

    state.empty_result_analysis = EmptyResultAnalysis(
        classification=classification,
        reason=str(result.get("reason", "")),
        suggestions=suggestions,
        filters_analysis=str(result.get("filters_analysis", "")),
    )

    state.agent_logs.append(
        log_agent_action("empty_result_analyzer", "analyzed", {
            "classification": classification,
            "num_suggestions": len(state.empty_result_analysis.suggestions),
        })
    )
    return state
