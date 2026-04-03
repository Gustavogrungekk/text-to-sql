"""Knowledge base loader — reads metadata from YAML/JSON files."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import boto3

from src.config import AppConfig, AthenaConfig


_KB_DIR = Path(__file__).resolve().parent / "data"
_CATALOG_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_json(filename: str) -> Dict[str, Any]:
    path = _KB_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _static_catalog() -> Dict[str, Any]:
    meta = _load_json("databases.json")
    return {"databases": meta.get("databases", {})}


def _cache_key(config: AppConfig) -> str:
    allowed_tables = json.dumps(config.allowed_tables, sort_keys=True)
    allowed_databases = ",".join(sorted(config.allowed_databases))
    return (
        f"{config.athena.region}|{config.athena.catalog_name}|"
        f"{allowed_databases}|{allowed_tables}"
    )


def _load_catalog_from_athena(
    athena_config: AthenaConfig,
    allowed_databases: list[str] | None = None,
    allowed_tables: dict[str, list[str]] | None = None,
) -> Dict[str, Any]:
    client = boto3.client("athena", region_name=athena_config.region)
    databases: Dict[str, Any] = {}
    db_allowlist = set(allowed_databases or [])
    table_allowlist = allowed_tables or {}

    db_next_token = None
    while True:
        params: Dict[str, Any] = {
            "CatalogName": athena_config.catalog_name,
            "MaxResults": 50,
        }
        if db_next_token:
            params["NextToken"] = db_next_token
        response = client.list_databases(**params)

        for db in response.get("DatabaseList", []):
            db_name = db.get("Name", "")
            if not db_name:
                continue
            if db_allowlist and db_name not in db_allowlist:
                continue

            tables: Dict[str, Any] = {}
            table_next_token = None
            while True:
                table_params: Dict[str, Any] = {
                    "CatalogName": athena_config.catalog_name,
                    "DatabaseName": db_name,
                    "MaxResults": 50,
                }
                if table_next_token:
                    table_params["NextToken"] = table_next_token
                table_resp = client.list_table_metadata(**table_params)

                for table in table_resp.get("TableMetadataList", []):
                    table_name = table.get("Name", "")
                    if not table_name:
                        continue
                    allowed_for_db = set(table_allowlist.get(db_name, []))
                    if allowed_for_db and table_name not in allowed_for_db:
                        continue

                    columns = [
                        {
                            "name": c.get("Name", ""),
                            "type": c.get("Type", ""),
                            "description": c.get("Comment", "") or "",
                        }
                        for c in table.get("Columns", [])
                        if c.get("Name")
                    ]
                    partitions = [
                        p.get("Name", "")
                        for p in table.get("PartitionKeys", [])
                        if p.get("Name")
                    ]

                    tables[table_name] = {
                        "description": table.get("Comment", "") or "",
                        "columns": columns,
                        "partitions": partitions,
                    }

                table_next_token = table_resp.get("NextToken")
                if not table_next_token:
                    break

            if tables:
                databases[db_name] = {
                    "description": db.get("Description", "") or "",
                    "tables": tables,
                }

        db_next_token = response.get("NextToken")
        if not db_next_token:
            break

    return {"databases": databases}


def _enrich_dynamic_with_static(
    dynamic_catalog: Dict[str, Any], static_catalog: Dict[str, Any]
) -> Dict[str, Any]:
    dynamic_databases = dynamic_catalog.get("databases", {})
    static_databases = static_catalog.get("databases", {})

    for db_name, db_info in dynamic_databases.items():
        static_db = static_databases.get(db_name, {})
        if not db_info.get("description"):
            db_info["description"] = static_db.get("description", "")

        dynamic_tables = db_info.get("tables", {})
        static_tables = static_db.get("tables", {})
        for table_name, table_info in dynamic_tables.items():
            static_table = static_tables.get(table_name, {})
            if not table_info.get("description"):
                table_info["description"] = static_table.get("description", "")

            static_columns = {
                c.get("name"): c
                for c in static_table.get("columns", [])
                if c.get("name")
            }
            for col in table_info.get("columns", []):
                col_name = col.get("name")
                if col_name and not col.get("description"):
                    static_col = static_columns.get(col_name, {})
                    col["description"] = static_col.get("description", "") or ""

    return dynamic_catalog


def load_catalog_snapshot(
    config: AppConfig | None = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Load a catalog snapshot. With config, prefer Athena and fallback to static JSON."""
    static_catalog = _static_catalog()
    if config is None:
        return copy.deepcopy(static_catalog)

    key = _cache_key(config)
    ttl = max(0, int(config.catalog_cache_ttl_seconds))
    cached = _CATALOG_CACHE.get(key)
    now = time.time()
    if cached and not force_refresh and now - cached["timestamp"] < ttl:
        return copy.deepcopy(cached["catalog"])

    try:
        dynamic_catalog = _load_catalog_from_athena(
            config.athena,
            allowed_databases=config.allowed_databases,
            allowed_tables=config.allowed_tables,
        )
        if dynamic_catalog.get("databases"):
            merged = _enrich_dynamic_with_static(dynamic_catalog, static_catalog)
            _CATALOG_CACHE[key] = {"timestamp": now, "catalog": merged}
            return copy.deepcopy(merged)
    except Exception:
        # Fallback to local static metadata when Athena catalog is unavailable.
        pass

    _CATALOG_CACHE[key] = {"timestamp": now, "catalog": static_catalog}
    return copy.deepcopy(static_catalog)


def get_databases(
    config: AppConfig | None = None,
    catalog: Dict[str, Any] | None = None,
) -> List[str]:
    """Return list of available databases."""
    meta = catalog or load_catalog_snapshot(config)
    return list(meta.get("databases", {}).keys())


def get_tables(
    database: str,
    config: AppConfig | None = None,
    catalog: Dict[str, Any] | None = None,
) -> List[str]:
    """Return tables for a given database."""
    meta = catalog or load_catalog_snapshot(config)
    db_info = meta.get("databases", {}).get(database, {})
    return list(db_info.get("tables", {}).keys())


def get_table_schema(
    database: str,
    table: str,
    config: AppConfig | None = None,
    catalog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return column metadata for a specific table."""
    meta = catalog or load_catalog_snapshot(config)
    return (
        meta.get("databases", {})
        .get(database, {})
        .get("tables", {})
        .get(table, {})
    )


def get_sql_examples(database: str, table: str | None = None) -> List[str]:
    """Return SQL examples for a database/table pair."""
    examples = _load_json("sql_examples.json")
    db_examples = examples.get(database, [])
    if table:
        return [e for e in db_examples if table.lower() in e.lower()]
    return db_examples


def get_business_rules(database: str) -> List[str]:
    """Return business rules for a database."""
    rules = _load_json("business_rules.json")
    return rules.get(database, [])


def get_partitions(
    database: str,
    table: str,
    config: AppConfig | None = None,
    catalog: Dict[str, Any] | None = None,
) -> List[str]:
    """Return partition columns for a table."""
    schema = get_table_schema(database, table, config=config, catalog=catalog)
    return schema.get("partitions", [])


def get_all_metadata_summary(
    config: AppConfig | None = None,
    catalog: Dict[str, Any] | None = None,
    preferred_database: str = "",
) -> str:
    """Return a text summary of all databases and tables for LLM context."""
    meta = catalog or load_catalog_snapshot(config)
    lines: List[str] = []
    databases = meta.get("databases", {})

    ordered_db_names = list(databases.keys())
    if preferred_database and preferred_database in databases:
        ordered_db_names.remove(preferred_database)
        ordered_db_names.insert(0, preferred_database)

    for db_name in ordered_db_names:
        db_info = databases[db_name]
        lines.append(f"Database: {db_name}")
        desc = db_info.get("description", "")
        if desc:
            lines.append(f"  Description: {desc}")
        for tbl_name, tbl_info in db_info.get("tables", {}).items():
            lines.append(f"  Table: {tbl_name}")
            tbl_desc = tbl_info.get("description", "")
            if tbl_desc:
                lines.append(f"    Description: {tbl_desc}")
            for col in tbl_info.get("columns", []):
                lines.append(f"    - {col['name']} ({col['type']}): {col.get('description', '')}")
            parts = tbl_info.get("partitions", [])
            if parts:
                lines.append(f"    Partitions: {', '.join(parts)}")
    return "\n".join(lines)
