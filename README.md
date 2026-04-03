# Text-to-SQL Multi-Agent System

> Sistema multi-agente de producao que converte perguntas em linguagem natural em SQL otimizado para AWS Athena, executa queries, gera insights de negocio, cria graficos e oferece download de dados (CSV, XLSX, JSON).

---

## TL;DR

Voce faz uma pergunta em portugues, o sistema entende a intencao, escolhe o banco e tabelas certos, gera e valida o SQL, executa no Athena, analisa os resultados e responde com texto, tabela interativa, grafico (se pedido) e botoes de download. Tudo dentro de um chat Streamlit.

**Em uma frase:** _"Linguagem natural entra, dados analisados saem."_

---

## O que e?

Um pipeline de agentes inteligentes (LLM-driven) orquestrado por LangGraph que:

1. **Classifica** a intencao da pergunta (query, saudacao, follow-up, esclarecimento, export, visualizacao, fora de escopo).
2. **Roteia** para o banco de dados e tabelas corretos usando metadados do Glue Catalog.
3. **Gera SQL** seguro e otimizado para Athena, com exemplos e regras de negocio no contexto.
4. **Valida** o SQL (heuristica + LLM) e retenta ate 3x em caso de erro.
5. **Executa** no Athena via boto3.
6. **Analisa resultado vazio** — classifica se e esperado, suspeito ou ambiguo (nunca inventa dados).
7. **Gera insights** de negocio a partir dos dados retornados.
8. **Cria graficos** Plotly (bar, line, pie, scatter, heatmap) quando o usuario solicita.
9. **Oferece download** direto de CSV, XLSX e JSON na interface.
10. **Suporta multi-base** — detecta quando a pergunta menciona 2+ bancos e executa uma query por banco.

## Para que serve?

- **Analistas de negocio** que querem consultar dados sem escrever SQL.
- **Times de dados** que precisam de um assistente de self-service analytics.
- **Prototipagem rapida** de interfaces conversacionais sobre data lakes no Athena.

---

## Fluxograma do Agente

```
                                    ┌──────────────┐
                                    │   Usuario     │
                                    └──────┬───────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │  Classifier   │  Classifica intencao + extrai datas
                                    └──────┬───────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                     nao precisa      precisa SQL      precisa
                       de SQL              │           esclarecimento
                          │                │                │
                          v                v                v
                   ┌────────────┐   ┌───────────┐   ┌────────────────┐
                   │  Resposta  │   │  Router    │   │  Pede mais     │
                   │  direta    │   │            │   │  contexto      │
                   └────────────┘   └─────┬─────┘   └────────────────┘
                                          │
                                          v
                                   ┌──────────────┐
                                   │   Schema      │  Carrega colunas, exemplos, regras
                                   │  Retrieval    │
                                   └──────┬───────┘
                                          │
                                          v
                              ┌──────────────────────┐
                              │    SQL Generator      │ ◄─── retry (ate 3x)
                              └──────────┬───────────┘            │
                                         │                        │
                                         v                        │
                              ┌──────────────────────┐            │
                              │    SQL Validator      │───────────┘
                              │  (heuristica + LLM)   │  invalido + tentativas restantes
                              └──────────┬───────────┘
                                         │ valido
                                         v
                              ┌──────────────────────┐
                              │  Execution (Athena)   │
                              └──────────┬───────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                        falha       0 linhas       N linhas
                          │              │              │
                          v              v              v
                   ┌──────────┐  ┌─────────────┐  ┌──────────┐
                   │ Response │  │ Empty Result │  │ Insight  │
                   │ Composer │  │  Analyzer    │  │ Generator│
                   └──────────┘  └──────┬──────┘  └────┬─────┘
                                        │              │
                                        v         ┌────┴────────────┐
                                 ┌──────────┐     │                 │
                                 │ Response │  pediu grafico?   nao pediu
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

**Modo multi-base:** quando a pergunta menciona explicitamente 2+ bancos, o pipeline roda uma query completa por banco (sequencialmente) e consolida as respostas. Athena aceita apenas 1 statement por execucao — multi-statement com `;` e bloqueado pelo validator.

---

## Stack Tecnologica

| Camada | Tecnologia |
|---|---|
| LLM | OpenAI GPT-4o (`openai` SDK) |
| Orquestracao | LangGraph (maquina de estados) |
| Cloud | AWS Athena via `boto3` |
| UI | Streamlit |
| Graficos | Plotly Express |
| Dados | Pandas |
| Validacao | Pydantic v2 |
| Testes | pytest (mocks de LLM + Athena, sem chamadas reais) |

---

## Pre-requisitos

- **Python** 3.10+ (recomendado 3.12)
- **Conta AWS** com permissao de Athena + Glue Catalog
- **Bucket S3** para output do Athena
- **Chave OpenAI** valida (GPT-4o)

---

## Instalacao Passo a Passo

### 1. Clone o repositorio

```bash
git clone <url-do-repo>
cd text-to-sql
```

### 2. Crie e ative o ambiente virtual

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

### 3. Instale dependencias

```bash
pip install -r requirements.txt
```

### 4. Configure as variaveis de ambiente

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Edite o `.env` com os seus dados:

```env
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
ATHENA_OUTPUT_BUCKET=s3://seu-bucket-athena-results/
ATHENA_WORKGROUP=primary
ATHENA_CATALOG_NAME=AwsDataCatalog
CATALOG_CACHE_TTL_SECONDS=300
```

### 5. Rode os testes

```bash
pytest
```

Todos os testes usam mocks — nenhuma chamada real a APIs e feita.

### 6. Inicie a aplicacao

```bash
streamlit run app.py
```

---

## Configuracao e Personalizacao

### Variaveis de ambiente (`.env`)

| Variavel | Descricao | Default |
|---|---|---|
| `OPENAI_API_KEY` | Chave da API OpenAI | — |
| `AWS_ACCESS_KEY_ID` | Credencial AWS | — |
| `AWS_SECRET_ACCESS_KEY` | Credencial AWS | — |
| `AWS_DEFAULT_REGION` | Regiao do Athena | `us-east-1` |
| `ATHENA_OUTPUT_BUCKET` | Bucket S3 para resultados | `s3://athena-results/` |
| `ATHENA_WORKGROUP` | Workgroup do Athena | `primary` |
| `ATHENA_CATALOG_NAME` | Data catalog do Glue | `AwsDataCatalog` |
| `CATALOG_CACHE_TTL_SECONDS` | TTL do cache do catalogo (segundos) | `300` |

### Metadados de negocio

Enriquecer estes arquivos melhora diretamente a qualidade do SQL gerado:

| Arquivo | O que colocar |
|---|---|
| `src/knowledge/data/databases.json` | Descricoes de tabelas e colunas |
| `src/knowledge/data/sql_examples.json` | Exemplos de queries reais por dominio |
| `src/knowledge/data/business_rules.json` | Regras que o gerador deve respeitar (ex.: "sempre filtrar por particao dt") |

### Guardrails e limites (`src/config.py` → `GuardrailsConfig`)

| Parametro | Descricao | Default |
|---|---|---|
| `default_limit` | LIMIT adicionado automaticamente quando ausente | `10000` |
| `max_limit` | Teto maximo de linhas por query | `10000` |
| `retry_attempts` | Tentativas de regeneracao de SQL apos falha de validacao | `3` |
| `max_export_rows` | Maximo de linhas para export | `50000` |
| `require_filter` | Exige clausula WHERE | `True` |
| `require_limit` | Exige clausula LIMIT | `True` |
| `cost_threshold_bytes` | Limite em bytes escaneados para alerta | `10 GB` |

### Modelo LLM (`src/config.py` → `LLMConfig`)

| Parametro | Descricao | Default |
|---|---|---|
| `model` | Modelo OpenAI | `gpt-4o` |
| `temperature` | Criatividade (0 = deterministico) | `0.0` |
| `max_tokens` | Limite de tokens na resposta | `4096` |

### Interface (`app.py`)

| Item | O que faz |
|---|---|
| `MAX_PERSISTED_ROWS` | Linhas mantidas no historico do chat por resposta (default: `100`) |
| `chart_keywords` | Palavras que ativam geracao de grafico (ex.: "grafico", "chart", "plot") |
| `chart_type_map` | Mapeamento de palavras para tipo Plotly (ex.: "pizza" → `pie`) |

### Restringir bancos/tabelas (opcional)

Em `src/config.py` → `AppConfig`, preencha `allowed_databases` e `allowed_tables` para limitar o escopo em producao.

---

## Guardrails de Seguranca

| Guardrail | Descricao |
|---|---|
| SQL somente SELECT | Operacoes DML/DDL (DROP, DELETE, INSERT, UPDATE, ALTER) sao bloqueadas |
| Statement unico | Multi-statement com `;` e rejeitado (requisito Athena) |
| LIMIT automatico | Adicionado quando ausente (default: 10.000) |
| LIMIT maximo | Hard-cap de 10.000 linhas por query |
| Filtro de particao | Exigido em tabelas particionadas |
| Retry com feedback | Ate 3 tentativas com erros anteriores injetados no prompt |
| Export limitado | Maximo de 50.000 linhas para download |
| Resultado vazio analisado | Classifica se e esperado, suspeito ou ambiguo — nunca inventa dados |

---

## Resultado Vazio (0 Linhas)

Quando a query executa com sucesso mas retorna 0 linhas, o agente `empty_result_analyzer` avalia:

| Classificacao | Significado | Acao |
|---|---|---|
| `expected` | Plausivel que nao existam dados (feriado, periodo recente, produto novo) | Informa o usuario |
| `suspicious` | Filtros excessivos, data no futuro, JOIN sem relacao | Sugere ajustes concretos de filtros |
| `ambiguous` | Impossivel determinar a causa sem mais contexto | Pede mais informacoes ao usuario |

O analyzer nunca inventa dados. Ele analisa o SQL, schema, regras de negocio e data atual para classificar.

---

## Extracao Automatica de Datas

O classifier extrai periodos de datas da pergunta do usuario, usando a data atual como referencia:

| Pergunta | `date_start` | `date_end` |
|---|---|---|
| "Vendas de janeiro 2024" | `2024-01-01` | `2024-01-31` |
| "Ultimos 7 dias" | *(calculado)* | *(data atual)* |
| "Ultimo mes" | *(1o dia mes anterior)* | *(ultimo dia mes anterior)* |
| "Ontem" | *(dia anterior)* | *(dia anterior)* |
| Sem mencao de data | `null` | `null` |

Quando nenhuma data e informada, o SQL generator usa automaticamente os dados mais recentes (ultimos 7 dias via particao).

---

## Estrutura do Projeto

```
text-to-sql/
├── app.py                              # UI Streamlit (chat + graficos + download)
├── pytest.ini                          # Configuracao do pytest
├── requirements.txt                    # Dependencias Python
├── .env.example                        # Template de variaveis de ambiente
├── exports/                            # Diretorio de arquivos exportados
├── src/
│   ├── config.py                       # Configuracao da aplicacao (Pydantic)
│   ├── state.py                        # Modelos de estado do pipeline
│   ├── pipeline.py                     # Orquestrador LangGraph (grafo + multi-base)
│   ├── llm_client.py                   # Wrapper OpenAI
│   ├── logger.py                       # Observabilidade estruturada
│   ├── agents/
│   │   ├── classifier.py              # Classificacao de intencao + extracao de datas
│   │   ├── router.py                  # Roteamento para banco/tabelas
│   │   ├── schema_retrieval.py        # Carga de schema, exemplos e regras
│   │   ├── sql_generator.py           # Geracao de SQL com contexto
│   │   ├── sql_validator.py           # Validacao heuristica + LLM
│   │   ├── execution.py               # Execucao no Athena (boto3)
│   │   ├── empty_result_analyzer.py   # Analise de resultado vazio
│   │   ├── insight.py                 # Geracao de insights de negocio
│   │   ├── visualization.py           # Geracao de graficos (Plotly Express)
│   │   ├── export.py                  # Export CSV/XLSX/JSON
│   │   └── response_composer.py       # Montagem da resposta final
│   └── knowledge/
│       ├── loader.py                  # Leitor da base de conhecimento
│       └── data/
│           ├── databases.json         # Metadados de tabelas/colunas
│           ├── sql_examples.json      # Exemplos de queries
│           └── business_rules.json    # Regras de negocio
└── tests/
    ├── conftest.py                    # Fixtures e mocks compartilhados
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

## Testes

Todos os testes usam mocks de LLM e Athena — nenhuma chamada real e feita.

```bash
# Rodar todos
pytest

# Rodar com output detalhado
pytest -v

# Rodar um modulo especifico
pytest tests/test_empty_result_analyzer.py -v

# Rodar apenas E2E
pytest tests/test_e2e.py -v
```

---

## Adicionando Novos Bancos de Dados

1. Crie/atualize as tabelas no Athena/Glue Catalog (fonte principal do roteamento).
2. Opcionalmente enriqueca `src/knowledge/data/databases.json` com descricoes.
3. Adicione exemplos SQL em `src/knowledge/data/sql_examples.json`.
4. Adicione regras de negocio em `src/knowledge/data/business_rules.json`.

---

## Troubleshooting

| Problema | Verificacao |
|---|---|
| Erro de credencial AWS | Valide `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e permissoes do Athena/S3 |
| Query falha por bucket | Confira `ATHENA_OUTPUT_BUCKET` (formato: `s3://bucket-name/`) |
| Sem tabelas na UI | Valide catalog, workgroup, regiao e permissoes de leitura no Glue Catalog |
| Sem resposta da LLM | Valide `OPENAI_API_KEY` e conectividade com a API |
| Timeout no Athena | Verifique se a query nao escaneia dados demais — ajuste `cost_threshold_bytes` |
| Grafico nao aparece | Certifique-se que a pergunta contem palavras-chave de visualizacao (ex.: "grafico", "chart") |

---

## Licenca

Este projeto e de uso interno. Consulte o time responsavel para detalhes de licenciamento.
