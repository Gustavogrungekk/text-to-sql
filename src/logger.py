"""Logging utilities for agent observability."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger("text_to_sql")


def log_agent_action(agent_name: str, action: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create a structured log entry for an agent action."""
    entry = {
        "agent": agent_name,
        "action": action,
        "timestamp": time.time(),
        "details": details or {},
    }
    logger.info(f"[{agent_name}] {action}: {details}")
    return entry


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
