"""Locust 容量测试数据契约；不依赖 Locust，便于 CI 静态验证。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True)
class LoadAccount:
    username: str
    password: str


@dataclass(frozen=True)
class LoadScenario:
    project_id: UUID
    year: int
    account_code: str
    workpaper_id: UUID | None = None


@dataclass(frozen=True)
class LoadConfig:
    accounts: tuple[LoadAccount, ...]
    scenarios: tuple[LoadScenario, ...]
    allow_writes: bool


def _json_input(env: Mapping[str, str], inline_key: str, file_key: str):
    inline = (env.get(inline_key) or "").strip()
    file_name = (env.get(file_key) or "").strip()
    if bool(inline) == bool(file_name):
        raise ValueError(f"必须且只能设置 {inline_key} 或 {file_key}")
    raw = inline if inline else Path(file_name).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{inline_key}/{file_key} 必须是非空 JSON 数组")
    return value


def load_config(env: Mapping[str, str] | None = None) -> LoadConfig:
    source = os.environ if env is None else env
    raw_accounts = _json_input(
        source,
        "GT_LOAD_ACCOUNTS_JSON",
        "GT_LOAD_ACCOUNTS_FILE",
    )
    raw_scenarios = _json_input(
        source,
        "GT_LOAD_SCENARIOS_JSON",
        "GT_LOAD_SCENARIOS_FILE",
    )

    accounts: list[LoadAccount] = []
    for index, item in enumerate(raw_accounts):
        if not isinstance(item, dict):
            raise ValueError(f"账号池第 {index + 1} 项必须是对象")
        username = str(item.get("username") or "").strip()
        password = str(item.get("password") or "")
        if not username or not password:
            raise ValueError(f"账号池第 {index + 1} 项缺 username/password")
        accounts.append(LoadAccount(username, password))

    scenarios: list[LoadScenario] = []
    for index, item in enumerate(raw_scenarios):
        if not isinstance(item, dict):
            raise ValueError(f"场景池第 {index + 1} 项必须是对象")
        try:
            project_id = UUID(str(item["project_id"]))
            workpaper_raw = item.get("workpaper_id")
            workpaper_id = UUID(str(workpaper_raw)) if workpaper_raw else None
            year = int(item["year"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"场景池第 {index + 1} 项 UUID/year 无效") from exc
        if not 2000 <= year <= 2100:
            raise ValueError(f"场景池第 {index + 1} 项 year 超出 2000..2100")
        account_code = str(item.get("account_code") or "1001").strip()
        if not account_code:
            raise ValueError(f"场景池第 {index + 1} 项缺 account_code")
        scenarios.append(LoadScenario(project_id, year, account_code, workpaper_id))

    allow_writes = (source.get("GT_LOAD_ALLOW_WRITES") or "").strip() == "1"
    disposable = (source.get("GT_LOAD_DISPOSABLE_ENV") or "").strip() == "YES"
    if allow_writes and not disposable:
        raise ValueError("启用写压测必须同时设置 GT_LOAD_DISPOSABLE_ENV=YES")
    if allow_writes and not any(item.workpaper_id for item in scenarios):
        raise ValueError("启用写压测时至少一个场景必须提供 workpaper_id")

    return LoadConfig(tuple(accounts), tuple(scenarios), allow_writes)
