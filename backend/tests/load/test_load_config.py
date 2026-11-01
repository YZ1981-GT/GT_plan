"""容量压测输入必须来自真实 UUID/账号池并保护共享环境。"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.load.load_config import load_config


def _env(**updates):
    project_id = str(uuid.uuid4())
    workpaper_id = str(uuid.uuid4())
    base = {
        "GT_LOAD_ACCOUNTS_JSON": json.dumps([
            {"username": "load-1", "password": "secret-1"},
            {"username": "load-2", "password": "secret-2"},
        ]),
        "GT_LOAD_SCENARIOS_JSON": json.dumps([{
            "project_id": project_id,
            "workpaper_id": workpaper_id,
            "year": 2025,
            "account_code": "1001",
        }]),
    }
    base.update(updates)
    return base


def test_load_config_accepts_uuid_pools_and_defaults_to_read_only():
    config = load_config(_env())
    assert len(config.accounts) == 2
    assert len(config.scenarios) == 1
    assert isinstance(config.scenarios[0].project_id, uuid.UUID)
    assert isinstance(config.scenarios[0].workpaper_id, uuid.UUID)
    assert config.allow_writes is False


def test_integer_placeholder_ids_are_rejected():
    env = _env()
    env["GT_LOAD_SCENARIOS_JSON"] = json.dumps([{
        "project_id": 1,
        "workpaper_id": 1,
        "year": 2025,
    }])
    with pytest.raises(ValueError, match="UUID/year 无效"):
        load_config(env)


def test_write_load_requires_explicit_disposable_environment_gate():
    with pytest.raises(ValueError, match="GT_LOAD_DISPOSABLE_ENV=YES"):
        load_config(_env(GT_LOAD_ALLOW_WRITES="1"))

    config = load_config(_env(
        GT_LOAD_ALLOW_WRITES="1",
        GT_LOAD_DISPOSABLE_ENV="YES",
    ))
    assert config.allow_writes is True


def test_missing_or_ambiguous_input_source_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="必须且只能设置"):
        load_config({})

    accounts = tmp_path / "accounts.json"
    accounts.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="必须且只能设置"):
        load_config({
            **_env(),
            "GT_LOAD_ACCOUNTS_FILE": str(accounts),
        })
