"""Configuration module."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class AthenaConfig:
    output_bucket: str = os.getenv("ATHENA_OUTPUT_BUCKET", "s3://athena-results/")
    workgroup: str = os.getenv("ATHENA_WORKGROUP", "primary")
    region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    catalog_name: str = os.getenv("ATHENA_CATALOG_NAME", "AwsDataCatalog")


@dataclass
class LLMConfig:
    model: str = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 4096
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))


@dataclass
class GuardrailsConfig:
    default_limit: int = 10000
    max_limit: int = 10000
    max_export_rows: int = 50000
    retry_attempts: int = 3
    cost_threshold_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB
    require_filter: bool = True
    require_limit: bool = True


@dataclass
class AppConfig:
    athena: AthenaConfig = field(default_factory=AthenaConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    allowed_databases: List[str] = field(default_factory=list)
    allowed_tables: Dict[str, List[str]] = field(default_factory=dict)
    catalog_cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("CATALOG_CACHE_TTL_SECONDS", 300)
    )
    log_level: str = "INFO"


def load_config() -> AppConfig:
    """Load application configuration."""
    return AppConfig()
