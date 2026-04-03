"""Classifier Agent — classifies user intent using LLM."""

from __future__ import annotations

from datetime import datetime

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, ClassificationResult

SYSTEM_PROMPT = """Você é um classificador de intenções para um sistema Text-to-SQL de analytics.

Data atual: {current_date}

Dada a mensagem do usuário e o histórico da conversa, classifique a intenção em exatamente uma das opções:
- query: o usuário quer dados / analytics / consulta SQL
- follow_up: o usuário está refinando ou continuando uma consulta anterior
- greeting: o usuário está cumprimentando ou se despedindo
- clarification: o usuário está respondendo uma pergunta de esclarecimento que você fez
- export: o usuário quer exportar/baixar dados
- visualization: o usuário quer explicitamente um gráfico ou visualização (ex: "me mostra um gráfico", "faz um gráfico de barras", "quero ver um chart")
- out_of_scope: a solicitação não tem relação com analytics

IMPORTANTE: A intenção 'visualization' só deve ser usada quando o usuário pedir EXPLICITAMENTE um gráfico/chart/visualização. Se o usuário apenas pedir dados sem mencionar gráfico, use 'query'.

Se o usuário pedir um tipo específico de gráfico (barras, linha, pizza, etc.), inclua essa informação no campo clarification_message como "chart_type:tipo_do_grafico".

EXTRAÇÃO DE DATAS:
Você DEVE extrair o período de datas mencionado (explícito ou implícito) na pergunta do usuário.
Use a data atual ({current_date}) como referência para calcular períodos relativos.
Exemplos:
- "dados de janeiro 2024" → date_start: "2024-01-01", date_end: "2024-01-31"
- "últimos 7 dias" → calcule com base na data atual
- "último mês" → calcule o mês anterior completo
- "ontem" → calcule com base na data atual
- "esse ano" / "este ano" → de 01/01 do ano atual até a data atual
- "semana passada" → segunda a domingo da semana anterior
- Sem menção de data → date_start: null, date_end: null (sistema usará dados mais recentes)

Retorne um objeto JSON com os seguintes campos:
- intent: uma das strings acima
- confidence: float de 0.0 a 1.0
- requires_sql: boolean — se é necessário executar SQL
- is_follow_up: boolean — se é continuação de uma conversa anterior
- needs_clarification: boolean — se a solicitação é ambígua demais para prosseguir
- clarification_message: string ou null — pergunta para o usuário se needs_clarification for true, ou "chart_type:tipo" se visualization com tipo específico
- date_start: string no formato "YYYY-MM-DD" ou null se nenhuma data mencionada
- date_end: string no formato "YYYY-MM-DD" ou null se nenhuma data mencionada

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


def classify(state: AgentState, llm: LLMClient) -> AgentState:
    """Classify user intent and extract date range."""
    current_date = state.current_date or datetime.now().strftime("%Y-%m-%d")
    state.current_date = current_date

    history_text = ""
    if state.conversation_history:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in state.conversation_history[-6:]
        )

    prompt = SYSTEM_PROMPT.format(current_date=current_date)
    user_msg = f"Histórico da conversa:\n{history_text}\n\nMensagem atual do usuário:\n{state.user_message}"

    result = llm.chat_json(
        system_prompt=prompt,
        user_message=user_msg,
    )

    classification = ClassificationResult(
        intent=result.get("intent", "out_of_scope"),
        confidence=float(result.get("confidence", 0.0)),
        requires_sql=bool(result.get("requires_sql", False)),
        is_follow_up=bool(result.get("is_follow_up", False)),
        needs_clarification=bool(result.get("needs_clarification", False)),
        clarification_message=result.get("clarification_message"),
        date_start=result.get("date_start"),
        date_end=result.get("date_end"),
    )

    state.classification = classification
    state.agent_logs.append(
        log_agent_action("classifier", "classified", {
            "intent": classification.intent,
            "confidence": classification.confidence,
            "date_start": classification.date_start,
            "date_end": classification.date_end,
        })
    )
    return state
