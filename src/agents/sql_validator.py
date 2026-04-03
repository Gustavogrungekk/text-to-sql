"""SQL Validator Agent — validates generated SQL using LLM + heuristics."""

from __future__ import annotations

import re

from src.config import GuardrailsConfig
from src.llm_client import LLMClient
from src.logger import log_agent_action
from src.state import AgentState, ValidationResult

SYSTEM_PROMPT = """Você é um agente de validação de SQL para AWS Athena.

Valide a seguinte consulta SQL contra o schema fornecido. Verifique:
1. Todas as tabelas referenciadas existem no schema
2. Todas as colunas referenciadas existem nas respectivas tabelas
3. Sintaxe SQL correta para Athena/Presto
4. Uso adequado de filtros de partição em tabelas particionadas
5. Presença de cláusula LIMIT
6. Nenhuma operação perigosa (DROP, DELETE, INSERT, UPDATE, ALTER, CREATE)
7. A consulta é apenas um SELECT

Schema:
{schema}

Colunas de partição:
{partitions}

Regras de negócio:
{rules}

SQL para validar:
{sql}

Retorne um objeto JSON com:
- is_valid: boolean
- errors: lista de strings de erro (vazia se válido)
- warnings: lista de strings de aviso
- corrected_sql: string com SQL corrigido se puder corrigir os erros, senão null

Sempre retorne JSON válido. Não envolva em blocos de código markdown."""


_DANGEROUS_PATTERNS = [
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|MERGE)\b",
]
_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


def _is_select_query(sql: str) -> bool:
    return sql.upper().lstrip().startswith("SELECT")


def _contains_dangerous_operation(sql: str) -> bool:
    return any(re.search(pattern, sql, re.IGNORECASE) for pattern in _DANGEROUS_PATTERNS)


def _apply_limit_guardrails(
    sql: str,
    guardrails: GuardrailsConfig,
    warnings: list[str],
    errors: list[str],
) -> str:
    matches = list(_LIMIT_PATTERN.finditer(sql))
    if not matches:
        if guardrails.require_limit:
            warnings.append(
                f"Cláusula LIMIT não encontrada. Auto-ajustada para {guardrails.default_limit}."
            )
            return sql.rstrip().rstrip(";") + f"\nLIMIT {guardrails.default_limit}"
        return sql

    last_match = matches[-1]
    current_limit = int(last_match.group(1))

    if current_limit <= 0:
        errors.append("O valor de LIMIT deve ser maior que zero.")
        return sql

    if current_limit > guardrails.max_limit:
        warnings.append(
            f"LIMIT {current_limit} acima do máximo permitido ({guardrails.max_limit}). "
            f"Auto-ajustado para {guardrails.max_limit}."
        )
        start, end = last_match.span(1)
        return sql[:start] + str(guardrails.max_limit) + sql[end:]

    return sql


def validate_sql(state: AgentState, llm: LLMClient, guardrails: GuardrailsConfig | None = None) -> AgentState:
    """Validate the generated SQL both heuristically and via LLM."""
    guardrails = guardrails or GuardrailsConfig()
    errors: list[str] = []
    warnings: list[str] = []

    sql = state.generated_sql.strip()

    if not sql:
        errors.append("SQL está vazio.")
        state.validation = ValidationResult(is_valid=False, errors=errors)
        return state

    # Heuristic checks
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            errors.append(f"Operação SQL perigosa detectada: corresponde ao padrão {pattern}")

    if not _is_select_query(sql):
        errors.append("A consulta deve ser um SELECT.")

    if errors:
        state.validation = ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        state.agent_logs.append(log_agent_action("sql_validator", "heuristic_fail", {"errors": errors}))
        return state

    sql = _apply_limit_guardrails(sql, guardrails, warnings, errors)
    if errors:
        state.validation = ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        state.agent_logs.append(log_agent_action("sql_validator", "heuristic_fail", {"errors": errors}))
        return state
    state.generated_sql = sql

    # LLM-based semantic validation
    schema_text = ""
    partitions_text = ""
    rules_text = ""
    if state.schema_context:
        for table, cols in state.schema_context.columns.items():
            schema_text += f"Table: {table}\n"
            for c in cols:
                schema_text += f"  - {c['name']} ({c['type']})\n"
        for table, parts in state.schema_context.partitions.items():
            if parts:
                partitions_text += f"{table}: {', '.join(parts)}\n"
        rules_text = "\n".join(state.schema_context.business_rules)

    prompt = SYSTEM_PROMPT.format(
        schema=schema_text or "Not available",
        partitions=partitions_text or "None",
        rules=rules_text or "None",
        sql=state.generated_sql,
    )

    result = llm.chat_json(
        system_prompt=prompt,
        user_message="Validate this SQL query.",
    )

    llm_corrected_sql = result.get("corrected_sql")
    validation = ValidationResult(
        is_valid=bool(result.get("is_valid", False)),
        errors=result.get("errors", []),
        warnings=result.get("warnings", []) + warnings,
        corrected_sql=llm_corrected_sql,
    )

    if validation.corrected_sql:
        candidate_errors: list[str] = []
        candidate_sql = _apply_limit_guardrails(
            validation.corrected_sql,
            guardrails,
            validation.warnings,
            candidate_errors,
        )
        if candidate_errors:
            validation.is_valid = False
            validation.errors.extend(candidate_errors)
        validation.corrected_sql = candidate_sql

    state.validation = validation

    # If LLM provided a correction, only accept it after heuristic safety checks.
    if not validation.is_valid and validation.corrected_sql:
        corrected_sql = validation.corrected_sql.strip()
        correction_errors: list[str] = []
        if _contains_dangerous_operation(corrected_sql):
            correction_errors.append("SQL corrigido contém operação perigosa.")
        if not _is_select_query(corrected_sql):
            correction_errors.append("SQL corrigido não é um SELECT.")

        if correction_errors:
            validation.errors.extend(correction_errors)
            validation.is_valid = False
        else:
            state.generated_sql = corrected_sql
            validation.is_valid = True
            validation.errors = []
    elif validation.is_valid and validation.corrected_sql:
        state.generated_sql = validation.corrected_sql

    state.agent_logs.append(
        log_agent_action("sql_validator", "validated", {
            "is_valid": validation.is_valid,
            "num_errors": len(validation.errors),
            "num_warnings": len(validation.warnings),
        })
    )
    return state
