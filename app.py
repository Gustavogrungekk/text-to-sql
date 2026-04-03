"""Interface Streamlit para o sistema multi-agente Text-to-SQL."""

from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import load_config
from src.knowledge.loader import get_databases, get_tables
from src.llm_client import LLMClient
from src.pipeline import Pipeline

MAX_PERSISTED_ROWS = 100


def _safe_json_loads(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _generate_sql_commentary(user_message: str, sql: str, database: str = "") -> str:
    if not sql:
        return ""

    llm: LLMClient | None = st.session_state.get("llm")
    if llm is None:
        return ""

    system_prompt = """Voce e um analista SQL. Explique a consulta em portugues brasileiro de forma curta e util.
Retorne no maximo 4 bullets cobrindo:
1) objetivo da consulta
2) principais filtros e periodo
3) joins/agregacoes importantes
4) observacoes de qualidade/cuidado
Nao invente nada que nao esteja no SQL."""

    prompt = (
        f"Pergunta do usuario: {user_message}\n"
        f"Banco: {database or 'nao informado'}\n"
        f"SQL:\n{sql}"
    )
    try:
        return llm.chat(system_prompt=system_prompt, user_message=prompt).strip()
    except Exception:
        return "Nao foi possivel gerar comentarios adicionais da consulta neste momento."


def _plotly_table(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Table(
                header=dict(values=list(df.columns), align="left"),
                cells=dict(values=[df[c].tolist() for c in df.columns], align="left"),
            )
        ]
    )
    fig.update_layout(title=title, margin=dict(l=8, r=8, t=36, b=8), height=420)
    return fig


def _render_chart(data: list[dict], chart_type: str, chart_config: dict, key: str):
    try:
        df = pd.DataFrame(data)
        chart_fn = getattr(px, chart_type, px.bar)
        fig = chart_fn(df, **chart_config)
        st.plotly_chart(
            fig,
            use_container_width=True,
            key=key,
            config={
                "displaylogo": False,
                "toImageButtonOptions": {"format": "png", "filename": "grafico"},
            },
        )
    except Exception as exc:
        st.warning(f"Nao foi possivel renderizar o grafico: {exc}")


def _render_sql_expander(sql: str, commentary: str, key_suffix: str):
    if not sql:
        return
    with st.expander("Mostrar query e comentarios", expanded=False):
        st.code(sql, language="sql")
        if commentary:
            st.markdown(commentary)


def _render_download_buttons(df: pd.DataFrame, key_suffix: str):
    """Render CSV, XLSX, JSON download buttons for a DataFrame."""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="dados.csv",
            mime="text/csv",
            key=f"dl-csv-{key_suffix}",
        )
    with col2:
        buf = __import__("io").BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "Excel",
            buf.getvalue(),
            file_name="dados.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl-xlsx-{key_suffix}",
        )
    with col3:
        st.download_button(
            "JSON",
            df.to_json(orient="records", force_ascii=False, indent=2),
            file_name="dados.json",
            mime="application/json",
            key=f"dl-json-{key_suffix}",
        )


def _render_table_expander(data: list[dict], row_count: int, title: str, key_suffix: str):
    if not data:
        return
    with st.expander("Mostrar tabela (Plotly)", expanded=False):
        df = pd.DataFrame(data)
        table_fig = _plotly_table(df, f"{title} - {row_count} linhas")
        st.plotly_chart(
            table_fig,
            use_container_width=True,
            key=f"table-{key_suffix}",
            config={
                "displaylogo": False,
                "toImageButtonOptions": {"format": "png", "filename": "tabela"},
            },
        )
        _render_download_buttons(df, key_suffix)


def _render_assistant_payload(payload: dict | None, key_prefix: str):
    if not payload:
        return

    if payload.get("multi_database_mode"):
        for idx, item in enumerate(payload.get("results", [])):
            db_name = item.get("database", "desconhecido")
            st.markdown(f"**Base `{db_name}`**")

            if item.get("chart"):
                chart = item["chart"]
                _render_chart(
                    data=item.get("data", []),
                    chart_type=chart.get("type", "bar"),
                    chart_config=chart.get("config", {}),
                    key=f"{key_prefix}-chart-{idx}",
                )

            _render_table_expander(
                data=item.get("data", []),
                row_count=int(item.get("row_count", 0)),
                title=f"Resultado {db_name}",
                key_suffix=f"{key_prefix}-tbl-{idx}",
            )
            _render_sql_expander(
                sql=item.get("sql", ""),
                commentary=item.get("sql_commentary", ""),
                key_suffix=f"{key_prefix}-sql-{idx}",
            )

            if item.get("error"):
                st.warning(f"Erro em {db_name}: {item['error']}")
        return

    chart = payload.get("chart")
    data = payload.get("data", [])
    if chart and data:
        _render_chart(
            data=data,
            chart_type=chart.get("type", "bar"),
            chart_config=chart.get("config", {}),
            key=f"{key_prefix}-chart",
        )

    _render_table_expander(
        data=data,
        row_count=int(payload.get("row_count", 0)),
        title="Resultado da consulta",
        key_suffix=f"{key_prefix}-tbl",
    )

    empty_analysis = payload.get("empty_result_analysis")
    if empty_analysis:
        classification = empty_analysis.get("classification", "ambiguous")
        icon = {"expected": "\u2139\ufe0f", "suspicious": "\u26a0\ufe0f", "ambiguous": "\u2753"}.get(classification, "\u2753")
        with st.expander(f"{icon} Analise de resultado vazio ({classification})", expanded=True):
            st.markdown(f"**Motivo:** {empty_analysis.get('reason', '')}")
            filters_text = empty_analysis.get("filters_analysis", "")
            if filters_text:
                st.markdown(f"**Filtros aplicados:** {filters_text}")
            suggestions = empty_analysis.get("suggestions", [])
            if suggestions:
                st.markdown("**Sugestoes:**")
                for s in suggestions:
                    st.markdown(f"- {s}")

    _render_sql_expander(
        sql=payload.get("sql", ""),
        commentary=payload.get("sql_commentary", ""),
        key_suffix=f"{key_prefix}-sql",
    )


def _build_assistant_payload(state, user_message: str) -> dict:
    if state.multi_database_mode:
        results = []
        for item in state.multi_db_results:
            sql_text = item.get("sql", "")
            db_name = item.get("database", "")
            results.append(
                {
                    "database": db_name,
                    "data": item.get("data", [])[:MAX_PERSISTED_ROWS],
                    "row_count": int(item.get("row_count", 0)),
                    "sql": sql_text,
                    "sql_commentary": _generate_sql_commentary(
                        user_message=user_message,
                        sql=sql_text,
                        database=db_name,
                    ),
                    "error": item.get("error", ""),
                }
            )
        return {"multi_database_mode": True, "results": results}

    chart_payload = None
    if (
        state.visualization
        and state.visualization.should_visualize
        and state.visualization.chart_json
        and state.execution
        and state.execution.success
        and state.execution.data
    ):
        chart_payload = {
            "type": state.visualization.chart_type,
            "config": _safe_json_loads(state.visualization.chart_json),
        }

    sql_text = state.generated_sql or ""

    empty_analysis_payload = None
    if state.empty_result_analysis:
        empty_analysis_payload = {
            "classification": state.empty_result_analysis.classification,
            "reason": state.empty_result_analysis.reason,
            "suggestions": state.empty_result_analysis.suggestions,
            "filters_analysis": state.empty_result_analysis.filters_analysis,
        }

    return {
        "multi_database_mode": False,
        "data": (state.execution.data if state.execution and state.execution.success else [])[:MAX_PERSISTED_ROWS],
        "row_count": state.execution.row_count if state.execution else 0,
        "sql": sql_text,
        "sql_commentary": _generate_sql_commentary(
            user_message=user_message,
            sql=sql_text,
            database=state.routing.database if state.routing else "",
        ),
        "chart": chart_payload,
        "empty_result_analysis": empty_analysis_payload,
    }


# --- Configuracao da pagina ---
st.set_page_config(
    page_title="Analista Text-to-SQL",
    page_icon="🔍",
    layout="wide",
)

st.title("Analista Text-to-SQL")
st.caption("Sistema multi-agente para AWS Athena — faca perguntas em linguagem natural")


# --- Session state init ---
if "conversation" not in st.session_state:
    st.session_state.conversation = []
if "pipeline" not in st.session_state:
    config = load_config()
    llm = LLMClient(config.llm)
    st.session_state.pipeline = Pipeline(config, llm)
    st.session_state.llm = llm
    st.session_state.config = config
if "last_state" not in st.session_state:
    st.session_state.last_state = None


# --- Sidebar ---
with st.sidebar:
    st.header("Configuracao")

    databases = get_databases(config=st.session_state.config)
    selected_db = st.selectbox("Banco de dados", databases if databases else ["analytics"])

    if selected_db:
        tables = get_tables(selected_db, config=st.session_state.config)
        st.write(f"**Tabelas disponiveis:** {', '.join(tables) if tables else 'N/A'}")

    st.divider()
    if st.button("Limpar conversa"):
        st.session_state.conversation = []
        st.session_state.last_state = None
        st.rerun()


# --- Historico do chat ---
for idx, msg in enumerate(st.session_state.conversation):
    with st.chat_message(msg["role"]):
        st.markdown(msg.get("content", ""))
        if msg["role"] == "assistant":
            _render_assistant_payload(msg.get("payload"), key_prefix=f"history-{idx}")


# --- Input do chat ---
user_input = st.chat_input("Faca uma pergunta sobre seus dados...")

if user_input:
    user_entry = {"role": "user", "content": user_input}
    st.session_state.conversation.append(user_entry)
    with st.chat_message("user"):
        st.markdown(user_input)

    visualization_requested = False
    requested_chart_type = ""
    lower_input = user_input.lower()
    chart_keywords = ["grafico", "chart", "plot", "visualizacao", "visualizar"]
    if any(kw in lower_input for kw in chart_keywords):
        visualization_requested = True
        chart_type_map = {
            "barra": "bar",
            "barras": "bar",
            "bar": "bar",
            "linha": "line",
            "linhas": "line",
            "line": "line",
            "pizza": "pie",
            "pie": "pie",
            "torta": "pie",
            "dispersao": "scatter",
            "scatter": "scatter",
            "heatmap": "heatmap",
            "calor": "heatmap",
        }
        for keyword, chart_type in chart_type_map.items():
            if keyword in lower_input:
                requested_chart_type = chart_type
                break

    with st.chat_message("assistant"):
        with st.spinner("Analisando sua pergunta..."):
            pipeline: Pipeline = st.session_state.pipeline
            state = pipeline.run(
                user_message=user_input,
                conversation_history=st.session_state.conversation[:-1],
                export_requested=False,
                export_format="",
                visualization_requested=visualization_requested,
                requested_chart_type=requested_chart_type,
                preferred_database=selected_db or "",
            )
            st.session_state.last_state = state

        st.markdown(state.final_response)
        payload = _build_assistant_payload(state, user_input)
        _render_assistant_payload(payload, key_prefix="current")

    st.session_state.conversation.append(
        {
            "role": "assistant",
            "content": state.final_response,
            "payload": payload,
        }
    )
