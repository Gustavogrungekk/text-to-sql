# Text-to-SQL Multi-Agent System

> Production-grade multi-agent system that translates natural language questions into optimized SQL for AWS Athena, executes queries, generates business insights, creates charts, and offers data download (CSV, XLSX, JSON).

---

## TL;DR

You ask a question in plain language, the system understands the intent, picks the right database and tables, generates and validates SQL, runs it on Athena, analyzes the results, and replies with text, an interactive table, a chart (if requested), and download buttons. All inside a Streamlit chat UI.

**In one sentence:** _"Natural language in, analyzed data out."_

---

## What Is It?

An LLM-driven agent pipeline orchestrated by LangGraph that:

1. **Classifies** the question intent (query, greeting, follow-up, clarification, export, visualization, out of scope).
2. **Routes** to the correct database and tables using Glue Catalog metadata.
3. **Generates** safe, optimized SQL for Athena with examples and business rules in context.
4. **Validates** the SQL (heuristic + LLM) and retries up to 3 times on failure.
5. **Executes** on Athena via boto3.
6. **Analyzes empty results** — classifies whether it's expected, suspicious, or ambiguous (never fabricates data).
7. **Generates business insights** from the returned data.
8. **Creates Plotly charts** (bar, line, pie, scatter, heatmap) when the user requests them.
9. **Offers direct download** of CSV, XLSX, and JSON from the interface.
10. **Supports multi-database queries** — detects when a question mentions 2+ databases and runs one query per database.

## Who Is It For?

- **Business analysts** who want to query data without writing SQL.
- **Data teams** that need a self-service analytics assistant.
- **Rapid prototyping** of conversational interfaces over Athena data lakes.

---

## Agent Flowchart

```
                                    ┌──────────────┐
                                    │     User      │
                                    └──────┬───────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │  Classifier   │  Classifies intent + extracts dates
                                    └──────┬───────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                     no SQL needed    SQL needed       needs
                          │                │           clarification
                          v                v                v
                   ┌────────────┐   ┌───────────┐   ┌────────────────┐
                   │   Direct   │   │  Router    │   │  Ask for more  │
                   │  Response  │   │            │   │   context      │
                   └────────────┘   └─────┬─────┘   └────────────────┘
                                          │
                                          v
                                   ┌──────────────┐
                                   │   Schema      │  Loads columns, examples, rules
                                   │  Retrieval    │
                                   └──────┬───────┘
                                          │
                                          v
                              ┌──────────────────────┐
                              │    SQL Generator      │ ◄─── retry (up to 3x)
                              └──────────┬───────────┘            │
                                         │                        │
                                         v                        │
                              ┌──────────────────────┐            │
                              │    SQL Validator      │───────────┘
                              │  (heuristic + LLM)    │  invalid + retries left
                              └──────────┬───────────┘
                                         │ valid
                                         v
                              ┌──────────────────────┐
                              │  Execution (Athena)   │
                              └──────────┬───────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                       failure       0 rows         N rows
                          │              │              │
                          v              v              v
                   ┌──────────┐  ┌─────────────┐  ┌──────────┐
                   │ Response │  │ Empty Result │  │ Insight  │
                   │ Composer │  │  Analyzer    │  │ Generator│
                   └──────────┘  └──────┬──────┘  └────┬─────┘
                                        │              │
                                        v         ┌────┴────────────┐
                                 ┌──────────┐     │                 │
                                 │ Response │  chart requested?  not requested
                                 │ Composer │     │                 │
                                 └──────────┘     v                 v
                                           ┌─────────────┐  ┌──────────┐
                                           │Visualization│  │ Response │
                                           │  (Plotly)   │  │ Composer │
                                           └──────┬──────┘  └──────────┘
                                                  │
                                                  v
                                           ┌──────────┐
                                           │ Response │
                                           │ Composer │
                                           └──────────┘
```

**Multi-database mode:** when the question explicitly mentions 2+ databases, the pipeline runs a full query per database (sequentially) and consolidates the responses. Athena only accepts 1 statement per execution — multi-statement SQL with `;` is blocked by the validator.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | OpenAI GPT-4o (`openai` SDK) |
| Orchestration | LangGraph (state machine) |
| Cloud | AWS Athena via `boto3` |
| UI | Streamlit |
| Charts | Plotly Express |
| Data | Pandas |
| Validation | Pydantic v2 |
| Tests | pytest (mocked LLM + Athena, no real API calls) |

---

## Prerequisites

- **Python** 3.10+ (recommended 3.12)
- **AWS account** with Athena + Glue Catalog permissions
- **S3 bucket** for Athena query output
- **OpenAI API key** (GPT-4o)

---

## Step-by-Step Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd text-to-sql
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
ATHENA_OUTPUT_BUCKET=s3://your-athena-results-bucket/
ATHENA_WORKGROUP=primary
ATHENA_CATALOG_NAME=AwsDataCatalog
CATALOG_CACHE_TTL_SECONDS=300
```

### 5. Run the tests

```bash
pytest
```

All tests use mocks — no real API calls are made.

### 6. Start the application

```bash
streamlit run app.py
```

---

## Configuration & Customization

### Environment Variables (`.env`)

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | — |
| `AWS_ACCESS_KEY_ID` | AWS credential | — |
| `AWS_SECRET_ACCESS_KEY` | AWS credential | — |
| `AWS_DEFAULT_REGION` | Athena region | `us-east-1` |
| `ATHENA_OUTPUT_BUCKET` | S3 bucket for query results | `s3://athena-results/` |
| `ATHENA_WORKGROUP` | Athena workgroup | `primary` |
| `ATHENA_CATALOG_NAME` | Glue data catalog | `AwsDataCatalog` |
| `CATALOG_CACHE_TTL_SECONDS` | Catalog cache TTL in seconds | `300` |

### Business Metadata

Enriching these files directly improves the quality of generated SQL:

| File | What to include |
|---|---|
| `src/knowledge/data/databases.json` | Table and column descriptions |
| `src/knowledge/data/sql_examples.json` | Real query examples per domain |
| `src/knowledge/data/business_rules.json` | Rules the generator must follow (e.g., "always filter by partition column dt") |

### Guardrails & Limits (`src/config.py` → `GuardrailsConfig`)

| Parameter | Description | Default |
|---|---|---|
| `default_limit` | LIMIT auto-added when missing | `10000` |
| `max_limit` | Hard cap on rows per query | `10000` |
| `retry_attempts` | SQL regeneration attempts after validation failure | `3` |
| `max_export_rows` | Max rows for data export | `50000` |
| `require_filter` | Require WHERE clause | `True` |
| `require_limit` | Require LIMIT clause | `True` |
| `cost_threshold_bytes` | Scanned bytes threshold for alerts | `10 GB` |

### LLM Model (`src/config.py` → `LLMConfig`)

| Parameter | Description | Default |
|---|---|---|
| `model` | OpenAI model | `gpt-4o` |
| `temperature` | Creativity (0 = deterministic) | `0.0` |
| `max_tokens` | Response token limit | `4096` |

### UI Settings (`app.py`)

| Item | Purpose |
|---|---|
| `MAX_PERSISTED_ROWS` | Rows kept in chat history per response (default: `100`) |
| `chart_keywords` | Words that trigger chart generation (e.g., "grafico", "chart", "plot") |
| `chart_type_map` | Word-to-Plotly-type mapping (e.g., "pizza" → `pie`) |

### Restrict Databases/Tables (optional)

In `src/config.py` → `AppConfig`, populate `allowed_databases` and `allowed_tables` to limit scope in production.

---

## Security Guardrails

| Guardrail | Description |
|---|---|
| SELECT-only SQL | DML/DDL operations (DROP, DELETE, INSERT, UPDATE, ALTER) are blocked |
| Single statement | Multi-statement SQL with `;` is rejected (Athena requirement) |
| Auto LIMIT | Added when missing (default: 10,000) |
| Max LIMIT | Hard-capped at 10,000 rows per query |
| Partition filter | Required on partitioned tables |
| Retry with feedback | Up to 3 attempts with previous errors injected into the prompt |
| Export limit | Maximum 50,000 rows for download |
| Empty result analysis | Classifies as expected, suspicious, or ambiguous — never fabricates data |

---

## Empty Result Handling (0 Rows)

When a query succeeds but returns 0 rows, the `empty_result_analyzer` agent evaluates:

| Classification | Meaning | Action |
|---|---|---|
| `expected` | Plausible that no data exists (holiday, recent period, new product) | Informs the user |
| `suspicious` | Overly restrictive filters, future date, unrelated JOIN | Suggests concrete filter adjustments |
| `ambiguous` | Cannot determine the cause without more context | Asks the user for more information |

The analyzer never fabricates data. It examines the SQL, schema, business rules, and current date to classify.

---

## Automatic Date Extraction

The classifier extracts date ranges from the user's question, using the current date as reference:

| Question | `date_start` | `date_end` |
|---|---|---|
| "January 2024 sales" | `2024-01-01` | `2024-01-31` |
| "Last 7 days" | *(computed)* | *(current date)* |
| "Last month" | *(1st of previous month)* | *(last day of previous month)* |
| "Yesterday" | *(previous day)* | *(previous day)* |
| No date mentioned | `null` | `null` |

When no date is specified, the SQL generator automatically uses the most recent data (last 7 days via partition).

---

## Project Structure

```
text-to-sql/
├── app.py                              # Streamlit UI (chat + charts + download)
├── pytest.ini                          # pytest configuration
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variables template
├── exports/                            # Exported files directory
├── src/
│   ├── config.py                       # Application configuration (Pydantic)
│   ├── state.py                        # Pipeline state models
│   ├── pipeline.py                     # LangGraph orchestrator (graph + multi-db)
│   ├── llm_client.py                   # OpenAI wrapper
│   ├── logger.py                       # Structured observability
│   ├── agents/
│   │   ├── classifier.py              # Intent classification + date extraction
│   │   ├── router.py                  # Database/table routing
│   │   ├── schema_retrieval.py        # Schema, examples, and rules loading
│   │   ├── sql_generator.py           # Context-aware SQL generation
│   │   ├── sql_validator.py           # Heuristic + LLM validation
│   │   ├── execution.py               # Athena execution (boto3)
│   │   ├── empty_result_analyzer.py   # Empty result analysis
│   │   ├── insight.py                 # Business insight generation
│   │   ├── visualization.py           # Chart generation (Plotly Express)
│   │   ├── export.py                  # CSV/XLSX/JSON export
│   │   └── response_composer.py       # Final response assembly
│   └── knowledge/
│       ├── loader.py                  # Knowledge base reader
│       └── data/
│           ├── databases.json         # Table/column metadata
│           ├── sql_examples.json      # Query examples
│           └── business_rules.json    # Business rules
└── tests/
    ├── conftest.py                    # Shared fixtures & mocks
    ├── test_classifier.py
    ├── test_router.py
    ├── test_sql_generator.py
    ├── test_sql_validator.py
    ├── test_execution.py
    ├── test_empty_result_analyzer.py
    ├── test_insight.py
    ├── test_visualization.py
    ├── test_export.py
    ├── test_pipeline_multi_db.py
    └── test_e2e.py
```

---

## Tests

All tests use mocked LLM and Athena clients — no real API calls are made.

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific module
pytest tests/test_empty_result_analyzer.py -v

# Run E2E tests only
pytest tests/test_e2e.py -v
```

---

## Adding New Databases

1. Create or update tables in Athena/Glue Catalog (primary source for routing).
2. Optionally enrich `src/knowledge/data/databases.json` with descriptions.
3. Add SQL examples to `src/knowledge/data/sql_examples.json`.
4. Add business rules to `src/knowledge/data/business_rules.json`.

---

## Troubleshooting

| Problem | What to check |
|---|---|
| AWS credential error | Validate `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and Athena/S3 permissions |
| Query fails on bucket | Check `ATHENA_OUTPUT_BUCKET` format (`s3://bucket-name/`) |
| No tables in UI | Validate catalog, workgroup, region, and Glue Catalog read permissions |
| No LLM response | Validate `OPENAI_API_KEY` and API connectivity |
| Athena timeout | Check if the query scans too much data — adjust `cost_threshold_bytes` |
| Chart not showing | Make sure the question contains visualization keywords (e.g., "chart", "plot", "grafico") |

---

## License

This project is for internal use. Contact the responsible team for licensing details.
