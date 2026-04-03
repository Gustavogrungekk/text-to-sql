# Text-to-SQL Multi-Agent System for AWS Athena

Production-grade multi-agent system that translates natural language into optimized SQL for AWS Athena, executes queries, generates business insights, creates visualizations, and supports data export.

Now includes multi-database orchestration: when a single question explicitly mentions more than one database, the system runs one SQL query per database sequentially and consolidates the response.

## Architecture

```
User Message
    │
    ▼
┌─────────────┐
│  Classifier  │  ← LLM-driven intent classification
└──────┬──────┘
       │
   ┌───┴───┐
   │ Router │  ← Selects database/tables via LLM
   └───┬───┘
       │
┌──────┴───────┐
│Schema Retrieval│ ← Loads columns, examples, rules
└──────┬───────┘
       │
┌──────┴──────┐
│SQL Generator │ ← LLM generates Athena SQL
└──────┬──────┘
       │
┌──────┴──────┐
│SQL Validator │ ← Heuristic + LLM validation
└──────┬──────┘
       │ (retry up to 3x)
┌──────┴──────┐
│  Execution   │ ← boto3 Athena execution
└──────┬──────┘
       │
┌──────┴──────┐
│   Insight    │ ← LLM generates business insights
└──────┬──────┘
       │
┌──────┴───────┐
│Visualization │ ← LLM decides chart type + Plotly config
└──────┬───────┘
       │
┌──────┴──────┐
│   Export     │ ← CSV, XLSX, JSON
└──────┬──────┘
       │
┌──────┴───────┐
│  Response    │ ← Assembles final answer
│  Composer    │
└──────────────┘
```

## Tech Stack

- **LLM**: OpenAI GPT-4o via `openai` SDK
- **Orchestration**: LangGraph (state machine)
- **Cloud**: AWS Athena via `boto3`
- **UI**: Streamlit
- **Charts**: Plotly Express
- **Data**: Pandas
- **Tests**: pytest with mocked LLM + Athena

## Project Structure

```
text-to-sql/
├── app.py                          # Streamlit UI
├── pytest.ini                      # pytest config
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── config.py                   # App configuration
│   ├── state.py                    # Pydantic state models
│   ├── llm_client.py               # OpenAI wrapper
│   ├── logger.py                   # Observability
│   ├── pipeline.py                 # LangGraph orchestrator
│   ├── agents/
│   │   ├── classifier.py           # Intent classification
│   │   ├── router.py               # Database/table routing
│   │   ├── schema_retrieval.py     # Schema context loading
│   │   ├── sql_generator.py        # SQL generation
│   │   ├── sql_validator.py        # SQL validation
│   │   ├── execution.py            # Athena execution
│   │   ├── insight.py              # Business insights
│   │   ├── visualization.py        # Chart generation
│   │   ├── export.py               # Data export
│   │   └── response_composer.py    # Response assembly
│   └── knowledge/
│       ├── loader.py               # Knowledge base reader
│       └── data/
│           ├── databases.json      # Table/column metadata
│           ├── sql_examples.json   # Example queries
│           └── business_rules.json # Business rules
└── tests/
    ├── conftest.py                 # Shared fixtures & mocks
    ├── test_classifier.py
    ├── test_router.py
    ├── test_sql_generator.py
    ├── test_sql_validator.py
    ├── test_execution.py
    ├── test_insight.py
    ├── test_visualization.py
    ├── test_export.py
    └── test_e2e.py
```

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your API keys and AWS credentials

# 4. Run tests
pytest

# 5. Launch UI
streamlit run app.py
```

## Configuration

Edit `.env`:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `AWS_DEFAULT_REGION` | AWS region (default: us-east-1) |
| `ATHENA_OUTPUT_BUCKET` | S3 bucket for Athena results |
| `ATHENA_WORKGROUP` | Athena workgroup name |
| `ATHENA_CATALOG_NAME` | Athena data catalog (default: AwsDataCatalog) |
| `CATALOG_CACHE_TTL_SECONDS` | Catalog cache TTL in seconds (default: 300) |

## Adding New Databases

1. Prefer creating/updating tables in Athena/Glue Catalog (dynamic source used by routing).
2. Optionally enrich table descriptions in `src/knowledge/data/databases.json`.
3. Add SQL examples to `src/knowledge/data/sql_examples.json`.
4. Add business rules to `src/knowledge/data/business_rules.json`.

## Guardrails

- All SQL validated before execution (heuristic + LLM)
- Multi-statement SQL (for example `SELECT ...; SELECT ...`) is blocked
- LIMIT clause auto-added when missing (default 10,000)
- LIMIT hard-capped to 10,000 rows
- Dangerous operations blocked (DROP, DELETE, etc.)
- Retry up to 3 attempts with error feedback
- Partition filters enforced on partitioned tables
- Export row limits enforced
- Multi-database questions are executed as sequential single-statement Athena runs (one per database)

## Extração Automática de Datas

O classifier extrai automaticamente períodos de datas da pergunta do usuário, usando a data atual como referência:

| Pergunta do usuário | date_start | date_end |
|---|---|---|
| "Vendas de janeiro 2024" | 2024-01-01 | 2024-01-31 |
| "Últimos 7 dias" | (calculado) | (data atual) |
| "Último mês" | (primeiro dia mês anterior) | (último dia mês anterior) |
| "Ontem" | (dia anterior) | (dia anterior) |
| Sem menção de data | null | null |

Quando nenhuma data é informada, o SQL generator utiliza automaticamente os dados mais recentes (últimos 7 dias via partição).

## Testing

```bash
# All tests
pytest

# Specific agent
pytest tests/test_classifier.py -v

# E2E only
pytest tests/test_e2e.py -v
```

All tests use mocked LLM and Athena clients — no real API calls needed.
