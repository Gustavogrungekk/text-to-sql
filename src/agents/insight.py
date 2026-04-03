"""Insight Agent — generates business insights from query results using LLM."""

from __future__ import annotations

import json

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, InsightResult

SYSTEM_PROMPT = """Você é um analista de insights de negócio. Dado uma consulta SQL, seus resultados e a pergunta original do usuário, forneça:

1. Uma explicação clara do que os dados mostram
2. De 2 a 5 insights de negócio acionáveis
3. Um breve resumo

Seja conciso e orientado por dados. Referencie números específicos dos resultados.
Não invente ou assuma dados que não estão presentes nos resultados.
Sempre responda em português brasileiro.

Retorne um objeto JSON com:
- explanation: string com a explicação principal
- insights: lista de strings de insights
- summary: breve resumo em uma frase

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


def generate_insights(state: AgentState, llm: LLMClient) -> AgentState:
    """Generate business insights from execution results."""
    if not state.execution or not state.execution.success:
        state.insight = InsightResult(
            explanation="A execução da consulta não foi bem-sucedida. Nenhum insight disponível.",
            insights=[],
            summary="Sem dados para analisar.",
        )
        return state

    # Limit data sent to LLM
    sample_data = state.execution.data[:50]

    user_msg = (
        f"Pergunta do usuário: {state.user_message}\n\n"
        f"SQL executado:\n{state.generated_sql}\n\n"
        f"Resultados ({state.execution.row_count} linhas, exibindo até 50):\n"
        f"{json.dumps(sample_data, indent=2, default=str)}"
    )

    result = llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
    )

    state.insight = InsightResult(
        explanation=result.get("explanation", ""),
        insights=result.get("insights", []),
        summary=result.get("summary", ""),
    )

    state.agent_logs.append(
        log_agent_action("insight", "generated", {
            "num_insights": len(state.insight.insights),
        })
    )
    return state
