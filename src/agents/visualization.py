"""Visualization Agent — gera gráficos Plotly SOMENTE quando o usuário solicitar."""

from __future__ import annotations

import json

from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, VisualizationResult

SYSTEM_PROMPT = """Você é um especialista em visualização de dados. O usuário PEDIU explicitamente um gráfico.

Com base na consulta SQL, nos resultados retornados e na pergunta do usuário, você deve:
1. Analisar o DataFrame retornado (colunas, tipos de dados, distribuição)
2. Analisar o contexto da pergunta do usuário
3. Decidir o MELHOR tipo de gráfico possível para representar esses dados

Regras para escolha do gráfico:
- Gráfico de barras: comparações entre categorias
- Gráfico de linha: séries temporais, tendências ao longo do tempo
- Gráfico de pizza: proporções/distribuição percentual (máximo 7 fatias)
- Gráfico de dispersão (scatter): correlação entre duas variáveis numéricas
- Heatmap: relação entre duas dimensões categóricas com valores numéricos

Se o usuário pediu um tipo específico de gráfico, use EXATAMENTE o tipo que ele pediu.
Se o usuário pediu apenas "um gráfico" sem especificar tipo, escolha o melhor com base nos dados.

Gere uma especificação de gráfico Plotly Express.

Retorne um objeto JSON com:
- should_visualize: true (o usuário já pediu o gráfico)
- chart_type: string (bar, line, pie, scatter, heatmap)
- reasoning: explicação breve de por que esse tipo de gráfico foi escolhido
- chart_config: objeto com configuração estilo Plotly Express ou null
  - chart_config deve conter: x, y, title, labels, e opcionalmente color, barmode, etc.
  - Para pie charts: use names e values ao invés de x e y
  - x e y devem referenciar nomes de colunas do resultado

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


def generate_visualization(state: AgentState, llm: LLMClient) -> AgentState:
    """Gera visualização SOMENTE quando o usuário pediu explicitamente."""
    # Se o usuário NÃO pediu gráfico, não gerar
    if not state.visualization_requested:
        state.visualization = VisualizationResult(
            should_visualize=False,
            reasoning="Usuário não solicitou visualização.",
        )
        return state

    if not state.execution or not state.execution.success or state.execution.row_count == 0:
        state.visualization = VisualizationResult(
            should_visualize=False,
            reasoning="Sem dados disponíveis para visualização.",
        )
        return state

    sample_data = state.execution.data[:30]

    # Incluir tipo de gráfico solicitado se houver
    chart_type_hint = ""
    if state.requested_chart_type:
        chart_type_hint = f"\n\nO usuário pediu ESPECIFICAMENTE um gráfico do tipo: {state.requested_chart_type}. Use este tipo."

    user_msg = (
        f"Pergunta do usuário: {state.user_message}\n\n"
        f"SQL:\n{state.generated_sql}\n\n"
        f"Colunas do resultado: {state.execution.columns}\n"
        f"Quantidade de linhas: {state.execution.row_count}\n"
        f"Amostra dos dados:\n{json.dumps(sample_data, indent=2, default=str)}"
        f"{chart_type_hint}"
    )

    result = llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
    )

    state.visualization = VisualizationResult(
        should_visualize=bool(result.get("should_visualize", True)),
        chart_type=result.get("chart_type", ""),
        chart_json=json.dumps(result.get("chart_config")) if result.get("chart_config") else None,
        reasoning=result.get("reasoning", ""),
    )

    state.agent_logs.append(
        log_agent_action("visualization", "generated", {
            "should_visualize": state.visualization.should_visualize,
            "chart_type": state.visualization.chart_type,
            "requested_type": state.requested_chart_type,
        })
    )
    return state
