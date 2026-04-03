"""Interface Streamlit para o sistema multi-agente Text-to-SQL."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import load_config
from src.knowledge.loader import get_databases, get_tables
from src.llm_client import LLMClient
from src.pipeline import Pipeline

# --- Configuração da página ---
st.set_page_config(
    page_title="Analista Text-to-SQL",
    page_icon="🔍",
    layout="wide",
)

st.title("Analista Text-to-SQL")
st.caption("Sistema multi-agente para AWS Athena — faça perguntas em linguagem natural")


# --- Session state init ---
if "conversation" not in st.session_state:
    st.session_state.conversation = []
if "pipeline" not in st.session_state:
    config = load_config()
    llm = LLMClient(config.llm)
    st.session_state.pipeline = Pipeline(config, llm)
    st.session_state.config = config
if "last_state" not in st.session_state:
    st.session_state.last_state = None


# --- Sidebar ---
with st.sidebar:
    st.header("Configuração")

    databases = get_databases(config=st.session_state.config)
    selected_db = st.selectbox("Banco de dados", databases if databases else ["analytics"])

    if selected_db:
        tables = get_tables(selected_db, config=st.session_state.config)
        st.write(f"**Tabelas disponíveis:** {', '.join(tables) if tables else 'N/A'}")

    st.divider()

    st.subheader("Guardrails")
    st.write(f"LIMIT padrão: {st.session_state.config.guardrails.default_limit}")
    st.write(f"LIMIT máximo: {st.session_state.config.guardrails.max_limit}")
    st.write(f"Máx. linhas exportação: {st.session_state.config.guardrails.max_export_rows}")
    st.write(f"Tentativas de retry: {st.session_state.config.guardrails.retry_attempts}")

    st.divider()
    if st.button("Limpar conversa"):
        st.session_state.conversation = []
        st.session_state.last_state = None
        st.rerun()


# --- Histórico do chat ---
for msg in st.session_state.conversation:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# --- Input do chat ---
user_input = st.chat_input("Faça uma pergunta sobre seus dados...")

if user_input:
    # Display user message
    st.session_state.conversation.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Verificar solicitação de exportação
    export_requested = False
    export_format = ""
    lower_input = user_input.lower()
    if any(kw in lower_input for kw in ["export", "exportar", "download", "baixar"]):
        if "xlsx" in lower_input or "excel" in lower_input:
            export_format = "xlsx"
        elif "json" in lower_input:
            export_format = "json"
        else:
            export_format = "csv"
        export_requested = True

    # Verificar solicitação de visualização
    visualization_requested = False
    requested_chart_type = ""
    chart_keywords = ["gráfico", "grafico", "chart", "plot", "visualização", "visualizacao", "visualizar"]
    if any(kw in lower_input for kw in chart_keywords):
        visualization_requested = True
        # Detectar tipo específico de gráfico
        chart_type_map = {
            "barra": "bar", "barras": "bar", "bar": "bar",
            "linha": "line", "linhas": "line", "line": "line",
            "pizza": "pie", "pie": "pie", "torta": "pie",
            "dispersão": "scatter", "dispersao": "scatter", "scatter": "scatter",
            "heatmap": "heatmap", "calor": "heatmap",
        }
        for keyword, chart_type in chart_type_map.items():
            if keyword in lower_input:
                requested_chart_type = chart_type
                break

    # Executar pipeline
    with st.chat_message("assistant"):
        with st.spinner("Analisando sua pergunta..."):
            pipeline: Pipeline = st.session_state.pipeline
            state = pipeline.run(
                user_message=user_input,
                conversation_history=st.session_state.conversation[:-1],
                export_requested=export_requested,
                export_format=export_format,
                visualization_requested=visualization_requested,
                requested_chart_type=requested_chart_type,
                preferred_database=selected_db or "",
            )
            st.session_state.last_state = state

        # --- Display response ---
        st.markdown(state.final_response)

        # --- SQL ---
        if state.generated_sql and not state.multi_database_mode:
            with st.expander("Consulta SQL", expanded=False):
                st.code(state.generated_sql, language="sql")

        # --- Multi-base details ---
        if state.multi_database_mode and state.multi_db_results:
            for item in state.multi_db_results:
                db_name = item.get("database", "desconhecido")
                sql_text = item.get("sql", "")
                success = bool(item.get("success", False))
                row_count = int(item.get("row_count", 0))
                data = item.get("data", [])

                if sql_text:
                    with st.expander(f"SQL ({db_name})", expanded=False):
                        st.code(sql_text, language="sql")

                if success and data:
                    with st.expander(f"Resultados ({db_name}) - {row_count} linhas", expanded=True):
                        df = pd.DataFrame(data)
                        st.dataframe(df, use_container_width=True)
                elif not success:
                    err = item.get("error", "Falha sem detalhe.")
                    st.warning(f"Base {db_name}: {err}")
        elif state.execution and state.execution.success and state.execution.data:
            # --- Tabela de dados ---
            with st.expander(f"Resultados ({state.execution.row_count} linhas)", expanded=True):
                df = pd.DataFrame(state.execution.data)
                st.dataframe(df, use_container_width=True)

        # --- Visualização (somente se usuário pediu) ---
        if (not state.multi_database_mode
                and state.visualization
                and state.visualization.should_visualize
                and state.visualization.chart_json):
            with st.expander("Gráfico", expanded=True):
                try:
                    chart_config = json.loads(state.visualization.chart_json)
                    df = pd.DataFrame(state.execution.data)

                    chart_type = state.visualization.chart_type
                    chart_fn = getattr(px, chart_type, px.bar)
                    fig = chart_fn(df, **chart_config)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"Não foi possível renderizar o gráfico: {e}")

        # --- Botões de exportação ---
        if (not state.multi_database_mode
                and state.execution
                and state.execution.success
                and state.execution.data):
            col1, col2, col3 = st.columns(3)
            df = pd.DataFrame(state.execution.data)

            with col1:
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button("Baixar CSV", csv_data, "dados.csv", "text/csv")
            with col2:
                json_data = df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8")
                st.download_button("Baixar JSON", json_data, "dados.json", "application/json")
            with col3:
                from io import BytesIO
                buffer = BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                st.download_button("Baixar XLSX", buffer.getvalue(), "dados.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # --- Metadados de execução ---
        if not state.multi_database_mode and state.execution and state.execution.success:
            with st.expander("Detalhes da execução", expanded=False):
                st.write(f"**Tempo de execução:** {state.execution.execution_time_ms}ms")
                st.write(f"**Bytes escaneados:** {state.execution.bytes_scanned:,}")
                st.write(f"**Linhas retornadas:** {state.execution.row_count}")

        # --- Logs dos agentes ---
        if state.agent_logs:
            with st.expander("Agent logs", expanded=False):
                for log in state.agent_logs:
                    st.json(log)

    # Save assistant response
    st.session_state.conversation.append({"role": "assistant", "content": state.final_response})
