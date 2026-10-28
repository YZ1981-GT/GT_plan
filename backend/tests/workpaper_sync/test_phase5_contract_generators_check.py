# -*- coding: utf-8 -*-
"""phase5 契约生成器 `--check` 守卫（spec oo-writeback-template-parity-closure 批 B2c）。

磁盘契约 `backend/data/workpaper_sync_contracts/*.json` 由各 provider 的 `build_contract_payload()` 生成。改了
provider（json 键 / 列 / 模式）不重跑生成器，磁盘契约就与源码脱钩 —— 线上按磁盘契约走、单测按源码走，各自全绿。
原先没有任何测试或 CI 跑这些生成器的 `--check`；K2 / K4 / K5 / K7 连生成器都没登记（批 B2c 改 K5 借贷两列时发现，
已补登）。

钉住：
1. 每个 `generate_phase5_*` 生成器默认（校验）模式退出 0，且输出里真有校验结论、没有 DRIFT / MISSING
   （只看退出码会被空跑或子进程解码失败骗过）；
2. K 生成器登记了全部 K 循环 provider（`phase5_k<n>_*.py`，共用内核 `phase5_k_adjustment_summary` 除外）；
3. 校验真会拒绝漂移（K：换掉一个 provider 的 payload，`_run_one` 报 DRIFT）。
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_GEN = _BACKEND / "scripts" / "gen"
_SYNC = _BACKEND / "app" / "services" / "workpaper_sync"
_GENERATORS = sorted(p.name for p in _GEN.glob("generate_phase5_*.py"))


def _load_k_generator():
    spec = importlib.util.spec_from_file_location("_gen_phase5_k_contracts", _GEN / "generate_phase5_k_contracts.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generator_set_is_not_empty():
    assert "generate_phase5_k_contracts.py" in _GENERATORS, _GENERATORS


@pytest.mark.parametrize("script", _GENERATORS)
def test_generator_check_passes(script):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(  # noqa: S603 - 固定参数，无 shell
        [sys.executable, str(_GEN / script)],
        cwd=str(_BACKEND.parent), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=600,
    )
    out = proc.stdout or ""
    assert proc.returncode == 0, f"{script} 校验未过（改了 provider 要重跑 --apply）：\n{out[-2000:]}\n{proc.stderr[-1500:]}"
    assert re.search(r"\bOK\b", out), f"{script} 输出里没有校验结论（空跑？）：\n{out[-1000:]}"
    assert "DRIFT" not in out and "MISSING" not in out, out[-2000:]


def test_k_generator_registers_every_k_provider():
    gen = _load_k_generator()
    registered = {m.rsplit(".", 1)[-1] for m in gen._MODULES}
    on_disk = {p.stem for p in _SYNC.glob("phase5_k*.py") if re.fullmatch(r"phase5_k\d+_\w+", p.stem)}
    assert on_disk, "没找到 K 循环 provider（目录或命名变了？）"
    assert sorted(on_disk - registered) == [], "K provider 没登记进生成器 ⇒ 改了它磁盘契约没法重算"
    assert sorted(registered - on_disk) == []


def test_k_check_rejects_drift(monkeypatch):
    gen = _load_k_generator()
    provider = importlib.import_module("app.services.workpaper_sync.phase5_k5_provisions")
    ok, msg = gen._run_one(provider, apply=False)
    assert ok, msg
    drifted = copy.deepcopy(provider.build_contract_payload())
    drifted["semantic_version"] = "0.0.0-drift"
    monkeypatch.setattr(provider, "build_contract_payload", lambda: drifted)
    ok, msg = gen._run_one(provider, apply=False)
    assert not ok and "DRIFT" in msg, msg
