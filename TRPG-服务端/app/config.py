"""TRPG config loader (MIT).

Loads YAML configs: table_default / llm_providers. Python 3.12 compatible.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = APP_ROOT / "configs"


def load_yaml(name: str, base: Path | None = None) -> dict:
    d = base or CONFIGS_DIR
    p = d / name
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _expand_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        inner = value[2:-1]
        if ":-" in inner:
            var, default = inner.split(":-", 1)
            return os.environ.get(var, default)
        return os.environ.get(inner, "")
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_table_config(base: Path | None = None) -> dict:
    return _expand_env(load_yaml("table_default.yaml", base))


def load_llm_config(base: Path | None = None) -> dict:
    return _expand_env(load_yaml("llm_providers.yaml", base))


def get_version() -> str:
    """版本串唯一真相源 (EX-MISC P3): 默认 app.VERSION, 部署可 TRPG_VERSION 覆盖."""
    from app import VERSION as _VERSION
    return os.environ.get("TRPG_VERSION", _VERSION)
