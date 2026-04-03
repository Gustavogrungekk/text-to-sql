"""Response Composer Agent — assembles the final response using LLM."""

from __future__ import annotations

import json

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState

SYSTEM_PROMPT = """Você é um assistente analista de dados amigável. Componha uma resposta clara e bem estruturada para o usuário com base nas informações fornecidas.

Sua resposta deve incluir (quando disponível):
1. Uma breve explicação do que foi feito
2. A consulta SQL utilizada (em bloco de código)
3. Principais achados dos dados
4. Insights de negócio
5. Quaisquer avisos ou observações

Use formatação markdown. Seja conciso mas informativo. Sempre responda em português brasileiro.
Não invente dados. Só referencie informações fornecidas abaixo."""


def compose_response(state: AgentState, llm: LLMClient) -> AgentState:
    """Compose the final user-facing response."""
    # Handle non-SQL intents
    if state.classification:
        if state.classification.needs_clarification:
            state.final_response = state.classification.clarification_message or "Poderia fornecer mais detalhes sobre sua pergunta?"
            state.agent_logs.append(
                log_agent_action("response_composer", "composed", {
                    "response_length": len(state.final_response),
                })
            )
            return state
        if not state.classification.requires_sql:
            if state.classification.intent == "greeting":
                state.final_response = "Olá! Sou seu assistente analista de dados. Pergunte qualquer coisa sobre seus dados de analytics — posso consultar bancos de dados, gerar insights, criar gráficos e exportar dados."
                state.agent_logs.append(
                    log_agent_action("response_composer", "composed", {
                        "response_length": len(state.final_response),
                    })
                )
                return state
            if state.classification.intent == "out_of_scope":
                state.final_response = "Desculpe, mas essa pergunta está fora do meu escopo de analytics. Posso ajudar com consultas de dados, insights, visualizações e exportações dos seus bancos de dados."
                state.agent_logs.append(
                    log_agent_action("response_composer", "composed", {
                        "response_length": len(state.final_response),
                    })
                )
                return state

    # Handle errors
    if state.error:
        state.final_response = f"Ocorreu um erro: {state.error}"
        return state

    # Build context for LLM
    parts = [f"Pergunta do usuário: {state.user_message}"]

    if state.classification and (state.classification.date_start or state.classification.date_end):
        date_info = "Período de datas extraído:"
        if state.classification.date_start:
            date_info += f" de {state.classification.date_start}"
        if state.classification.date_end:
            date_info += f" até {state.classification.date_end}"
        parts.append(date_info)
    elif state.classification and state.classification.requires_sql:
        parts.append("Nenhum período de datas especificado — dados mais recentes foram utilizados.")

    if state.generated_sql:
        parts.append(f"Consulta SQL:\n```sql\n{state.generated_sql}\n```")

    if state.execution:
        if state.execution.success:
            sample = state.execution.data[:20]
            parts.append(f"A consulta retornou {state.execution.row_count} linhas.")
            parts.append(f"Amostra dos resultados:\n{json.dumps(sample, indent=2, default=str)}")
            parts.append(f"Bytes escaneados: {state.execution.bytes_scanned}")
            parts.append(f"Tempo de execução: {state.execution.execution_time_ms}ms")
        else:
            parts.append(f"A consulta falhou: {state.execution.error}")

    if state.insight:
        parts.append(f"Insights:\n- " + "\n- ".join(state.insight.insights))
        parts.append(f"Summary: {state.insight.summary}")

    if state.validation and state.validation.warnings:
        parts.append(f"Avisos: {', '.join(state.validation.warnings)}")

    if state.export:
        parts.append(f"Dados exportados para: {state.export.file_path} ({state.export.row_count} linhas, {state.export.format})")

    context = "\n\n".join(parts)

    response = llm.chat(
        system_prompt=SYSTEM_PROMPT,
        user_message=context,
    )

    state.final_response = response

    state.agent_logs.append(
        log_agent_action("response_composer", "composed", {
            "response_length": len(response),
        })
    )
    return state
