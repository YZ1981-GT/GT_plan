# -*- coding: utf-8 -*-
"""Property 15 的后端侧判据：受管 sheet 清单下发通道的取数链与幂等。

spec: d567-sync-coverage-via-row-table-engine · Task 22 · Property 15

═══ 下发通道的裁决（原 tasks.md 记为「卡设计裁决」，本文件是裁决落地后的守卫）═══

受管清单**不**走新端点、**不**改 render-config、**不**扩 155-entry 的共享
`workpaperSyncManifest.generated.ts`，而是新建专用生成产物
`workpaperSyncManagedSheets.generated.ts`。取数链三段全是既有真源：

    entry_id
      → `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS`（lane 裁决 L3 用的同一张表）
      → `contracts.contract_path_for(contract_id)`（全仓唯一拼契约路径处）
      → 契约 `sheets[].{sheet_key, excel_name}`

🔴 **该链不依赖 adapter 是否已注册**：登记行的 `adapter_registered` 是独立字段
（D5/D6/D7 当前均为 `False`）。「契约已交付」与「adapter 已注册」是**两个分母** ——
受管清单属前者、现在就能下发；OO 能否真用属后者。把两者混成一个门，就等于要求
「adapter 注册完才能修前端写死」，那是本 Property 迟迟没做的真正原因。

🔴 本文件同时钉住**输出幂等**：`--check` 在无违规时必须绿。不幂等的生成器接进 CI
就是永假门（本仓 `disclosure-payload` 五轮复盘 T29 实测过：`--apply` + `git diff`
配上带时间戳的产物 ⇒ 该 step 必然失败 ⇒ 长期全红 ⇒ 等于门不存在）。
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.adapters.registry import (  # noqa: E402
    DELIVERED_PER_ENTRY_CONTRACTS,
)
from app.services.workpaper_sync.contracts import contract_path_for  # noqa: E402

_GENERATOR = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_managed_sheets.py"
_TARGET = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncManagedSheets.generated.ts"
)
_GOVERNANCE = _REPO / ".github" / "workflows" / "governance-checks.yml"

_D567_ENTRIES = (
    "xlsx/gt-d5-receivables-financing",
    "xlsx/gt-d6-contract-assets",
    "xlsx/gt-d7-contract-liabilities",
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("_gen_managed_sheets", _GENERATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frontend_entries() -> list[dict]:
    """从生成产物里解析出 entries（判据要比对前后端一致，不能只看后端现算）。"""
    text = _TARGET.read_text(encoding="utf-8")
    m = re.search(
        r"MANAGED_SHEETS: readonly WorkpaperSyncManagedSheetsEntry\[\] =\s*(\[.*?\]) as const",
        text,
        re.S,
    )
    assert m, "产物里找不到 MANAGED_SHEETS 数组 —— 解析器与产物形态脱钩"
    return json.loads(m.group(1))


# ═══════════════════════════════════════════════════════════════════════════
# 一、取数链三段成立
# **Validates: Requirements 8.1（Property 15）**
# ═══════════════════════════════════════════════════════════════════════════


def test_delivered_contracts_registry_is_the_bridge() -> None:
    """`DELIVERED_PER_ENTRY_CONTRACTS` 覆盖三家，且给出可解析的 contract_id。"""
    rows = {r["entry_id"]: r for r in DELIVERED_PER_ENTRY_CONTRACTS}
    assert rows, "登记表为空 ⇒ 取数链断了（空分母）"
    for entry_id in _D567_ENTRIES:
        row = rows.get(entry_id)
        assert row is not None, f"{entry_id} 不在 DELIVERED_PER_ENTRY_CONTRACTS ⇒ 桥断了"
        contract_id = row.get("contract_id")
        assert contract_id, f"{entry_id} 登记行无 contract_id"
        path = contract_path_for(contract_id)
        assert path.is_file(), f"{entry_id}: 契约文件不存在 {path}"


def test_managed_sheets_are_independent_of_adapter_registration() -> None:
    """🔴 两个分母分开：三家 `adapter_registered=False`，但受管清单必须非空。

    这条是裁决的核心 —— 若清单被注册状态门控，Property 15 在 adapter 注册前根本交付不了。
    """
    rows = {r["entry_id"]: r for r in DELIVERED_PER_ENTRY_CONTRACTS}
    for entry_id in _D567_ENTRIES:
        row = rows[entry_id]
        assert row.get("adapter_registered") is False, (
            f"{entry_id} 的 adapter_registered 现状变了 —— 本判据的前提需复核"
        )
        contract = json.loads(contract_path_for(row["contract_id"]).read_text(encoding="utf-8"))
        sheets = contract.get("sheets") or []
        assert sheets, f"{entry_id}: 契约无 sheets ⇒ 清单空"
        assert len(sheets) > 1, (
            f"{entry_id}: 受管 sheet 只有 {len(sheets)} 张 —— 本 Property 要修的正是"
            f"「前端只认一张」，分母为 1 时判据无意义"
        )


def test_every_contract_sheet_carries_authoritative_excel_name() -> None:
    """全部契约的每个受管 sheet 都有 `excel_name`（前端据它归一，禁字符串推演）。"""
    missing: list[str] = []
    total = 0
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        path = contract_path_for(row["contract_id"])
        if not path.is_file():
            continue
        contract = json.loads(path.read_text(encoding="utf-8"))
        for sheet in contract.get("sheets") or []:
            total += 1
            if not sheet.get("excel_name"):
                missing.append(f"{row['contract_id']}:{sheet.get('sheet_key')}")
    assert total > 0, "扫不到任何受管 sheet（空分母）"
    assert missing == [], f"{len(missing)} 个受管 sheet 缺 excel_name：{missing[:20]}"


# ═══════════════════════════════════════════════════════════════════════════
# 二、产物与后端现算一致 + 幂等
# ═══════════════════════════════════════════════════════════════════════════


def test_generated_artifact_matches_backend_recompute() -> None:
    """产物 == 后端现算（`--check` 的语义），防手工编辑/漂移。"""
    gen = _load_generator()
    facts = gen.collect_facts()
    assert _TARGET.is_file(), f"产物缺失：{_TARGET}"
    assert _TARGET.read_text(encoding="utf-8") == gen.render(facts), (
        "产物与后端现算不一致 ⇒ 运行 "
        "py -3 backend/scripts/gen/generate_workpaper_sync_managed_sheets.py --apply"
    )


def test_generator_output_is_idempotent() -> None:
    """🔴 两次 render 逐字节相同（无时间戳/随机量）⇒ `--check` 无违规时必绿。

    不幂等的生成器接进 CI 就是**永假门**；本条是那条 CI step 有效性的前提。
    """
    gen = _load_generator()
    first = gen.render(gen.collect_facts())
    second = gen.render(gen.collect_facts())
    assert first == second, "两次 render 不同 ⇒ 输出不幂等，--check 会变成永假门"
    for token in ("generated_at", "datetime", "timestamp", "now()"):
        assert token not in first, f"产物含易漂移标记 {token!r} ⇒ 幂等会被破坏"


def test_frontend_projection_agrees_with_registry() -> None:
    """产物里的 entry 集合与登记表逐条一致（不多不少），三家受管张数逐个对齐契约。"""
    fe = {e["entryId"]: e for e in _frontend_entries()}
    reg = {r["entry_id"]: r for r in DELIVERED_PER_ENTRY_CONTRACTS}
    assert set(fe) == set(reg), (
        f"产物与登记表 entry 集合不一致；仅产物有={sorted(set(fe) - set(reg))[:10]}；"
        f"仅登记表有={sorted(set(reg) - set(fe))[:10]}"
    )
    for entry_id in _D567_ENTRIES:
        contract = json.loads(contract_path_for(reg[entry_id]["contract_id"]).read_text(encoding="utf-8"))
        expected = sorted(s["sheet_key"] for s in contract["sheets"])
        actual = sorted(s["sheetKey"] for s in fe[entry_id]["managedSheets"])
        assert actual == expected, f"{entry_id} 受管键不一致：产物 {actual} vs 契约 {expected}"


# ═══════════════════════════════════════════════════════════════════════════
# 三、CI 门禁真的接上了（且用的是 --check 不是 apply-后比较）
# ═══════════════════════════════════════════════════════════════════════════


def test_ci_gate_is_wired_with_check_mode() -> None:
    """🔴 治理 CI 必须调本生成器的 `--check`，且**不得**用 `--apply` + `git diff` 写法。

    后者只要产物含时间戳就变成永假门（本仓实测过一次，长期全红等于门不存在）。
    """
    text = _GOVERNANCE.read_text(encoding="utf-8")
    assert "generate_workpaper_sync_managed_sheets.py --check" in text, (
        "governance-checks.yml 未接受管清单产物的 --check 门 ⇒ 产物会静默漂移"
    )
    # 同一生成器不得出现 apply-后比较的写法。
    assert not re.search(
        r"generate_workpaper_sync_managed_sheets\.py\s+--apply[\s\S]{0,200}?git diff", text
    ), "受管清单门用了 --apply + git diff ⇒ 幂等一破就是永假门"


# ═══════════════════════════════════════════════════════════════════════════
# 四、变异自检
# ═══════════════════════════════════════════════════════════════════════════


def test_mutation_missing_excel_name_fails_generation_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 真变异：让某个契约的 sheet 缺 `excel_name` ⇒ `collect_facts()` 必须**抛错**。

    静默跳过会让前端少一张受管 sheet 且无任何报错 —— 正是本 Property 要消灭的形态。

    🔴 **不能**在 `pytest.raises` 里自己 `raise` 那个异常 —— 那是恒真装饰（本文件首版就是
    这么写的，自查时抓出来了）。这里真的改一份契约副本，再让生成器去读它。
    """
    gen = _load_generator()

    # 取一份真实契约，抽掉第一个 sheet 的 excel_name，写到 tmp。
    row = next(r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["entry_id"] == _D567_ENTRIES[0])
    real = json.loads(contract_path_for(row["contract_id"]).read_text(encoding="utf-8"))
    assert real["sheets"][0].get("excel_name"), "样本契约本就缺 excel_name，变异无意义"
    real["sheets"][0]["excel_name"] = ""
    broken = tmp_path / f"{row['contract_id']}.json"
    broken.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")

    real_resolver = gen.__dict__.get("contract_path_for")

    def _fake_path_for(contract_id: str) -> Path:
        if contract_id == row["contract_id"]:
            return broken
        return contract_path_for(contract_id)

    # 生成器在函数体内 `from ... import contract_path_for`，故 patch 源模块的符号。
    monkeypatch.setattr(
        "app.services.workpaper_sync.contracts.contract_path_for", _fake_path_for
    )
    try:
        with pytest.raises(gen.ManagedSheetsGenerationError) as ei:
            gen.collect_facts()
        assert "excel_name" in str(ei.value), f"错误文案未点名 excel_name：{ei.value}"
    finally:
        if real_resolver is not None:  # pragma: no cover - 仅保守复原
            gen.__dict__["contract_path_for"] = real_resolver


def test_mutation_probe_itself_is_not_vacuous() -> None:
    """🔴 上一条的反向自检：**未**变异时 `collect_facts()` 必须正常返回（不抛）。

    若它在干净状态下也抛，上一条的 `pytest.raises` 就成了恒真 —— 这条钉住那个前提。
    """
    gen = _load_generator()
    facts = gen.collect_facts()
    assert facts["entry_count"] > 0 and facts["sheet_count"] > 0


def test_mutation_registry_without_entry_would_be_caught() -> None:
    """🔴 变异：若某 entry 从登记表消失，一致性判据必红（证明它不是恒真装饰）。"""
    fe = {e["entryId"] for e in _frontend_entries()}
    reg = {r["entry_id"] for r in DELIVERED_PER_ENTRY_CONTRACTS}
    assert fe == reg
    shrunk = reg - {_D567_ENTRIES[0]}
    assert fe != shrunk, "抽掉一个 entry 后集合仍相等 ⇒ 比较无鉴别力"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
