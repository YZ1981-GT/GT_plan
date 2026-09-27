# -*- coding: utf-8 -*-
"""8 家 sync provider 的 golden digest 基线 —— 行表引擎抽取前后逐字节零回归门。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 1 · Requirements 4.1 / 4.2 / 4.5

═══ 这条基线钉的是什么 ═══

本 spec 要把「一底稿一份 900 行 provider」收敛成「框架层单一引擎 + 声明」。收敛的安全性来源
是：抽取前后，8 个已交付 contract 的三段 canonical JSON **逐字节不变**。本脚本在抽取**前**先
取 24 个 digest 存盘（此时必绿，是**基线**不是判据），抽取**后**每家过一次门；任一 digest 变
即打印 `disk vs source` 并 exit 1，供落全量 diff 排查（Requirement 4.2）。

三段 digest（每家取三个 canonical JSON 的 sha256）：
  1. `build_contract_payload()`      —— per-entry 契约 canonical payload
  2. `build_store_projection(合成 payload)` —— HTML store → Projection 的投影结果
  3. `instrumentation_spec(s)()`      —— Excel 注入几何声明

🔴 合成 payload（Requirement 4.5）：D3/D5/D6 的 store item 真库 0 行，**不得**因无数据而跳过
该 contract；本脚本用「每家两行、字段全填占位值」的合成 payload 驱动 build_store_projection，
确保投影路径被真实走过。合成 payload 由 `_synthetic_rows()` 按各家 field_specs 现造，不手抄。

🔴 provider 命名差异（照实处理，不强行统一）：
  * B60（`pilot_simple_checklist`）是 simple_checklist 形态，**无** `build_store_projection`
    （它的 store 不是行数组投影）⇒ 第 2 段记 `null` 并注明「不适用」，不假造 digest。
  * D2（`pilot_d2_large_json`）用 `PILOT_ADAPTER_ID`；其余六家用 `ADAPTER_ID`。
  * D4 有 `instrumentation_specs()`（复数，多受管 sheet）⇒ 第 3 段取复数；其余取单数。

🔴 为什么落 `backend/scripts/check/` 而不是只放 pytest：`tests/workpaper_sync/` 有大量与本
spec 无关的既存失败，在那个分母上「pytest 红了」不是可归因信号。本门禁可独立红、可独立归因
（照 `check_store_item_ids_fully_wired.py` 已验证的口径）。

用法：
  取基线（首次，抽取前）：  python backend/scripts/check/check_sync_provider_golden_digest.py --update
  过门（抽取后每家）：      python backend/scripts/check/check_sync_provider_golden_digest.py
  写报告：                  ... --json <path>

digest 存 `backend/scripts/check/_sync_provider_golden_digest.json`（同目录，随代码入库）。
自测：`backend/tests/scripts/test_check_sync_provider_golden_digest.py`。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_DIGEST_PATH = Path(__file__).resolve().parent / "_sync_provider_golden_digest.json"


#: 8 家已交付 provider 的模块名 + adapter_id 常量名（照实登记命名差异，不强行统一）。
#: (标签, 模块名, adapter_id 常量名, 是否有 build_store_projection, instrumentation 复数否)
PROVIDERS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("b60", "pilot_simple_checklist", "PILOT_ADAPTER_ID", False, False),
    # 🔴 D1/D3/D5/D6/D7 同 D2 切复数（2026-09-26）：这五家的
    #    `instrumentation_definition_payload()` 已改走 `build_instrumentation_payload_for_sheets
    #    (specs=instrumentation_specs())`，注册路径读的是**复数**。`plural_instr` 留 False 会
    #    让本判据只核主 sheet 单 spec ⇒ 扩容面（行表 sibling + 审定表 static_sheets）对判据
    #    完全不可见，正是 D2 注释警告的那种假绿：真实发布的 instrumentation 变了而门不红。
    ("d1", "phase5_d1_notes_receivable", "ADAPTER_ID", True, True),
    # 🔴 D2 已切多 sheet 复数 instrumentation（d22 + 灰度控 d23 双区 + d21 静态区，spec
    #    workpaper-sync-registration-isolation-and-d2-republish）——`plural_instr=True` 才能
    #    让本判据核到真实注册路径用的 `instrumentation_specs()`（含 d21 static_sheets），
    #    否则只核 d22 单 spec，republish 后的扩容面对判据不可见（假绿）。
    ("d2", "pilot_d2_large_json", "PILOT_ADAPTER_ID", True, True),
    ("d3", "phase5_d3_prepaid_receipts", "ADAPTER_ID", True, True),
    ("d4", "phase5_d4_revenue_detail", "ADAPTER_ID", True, True),
    ("d5", "phase5_d5_receivables_financing", "ADAPTER_ID", True, True),
    ("d6", "phase5_d6_contract_assets", "ADAPTER_ID", True, True),
    ("d7", "phase5_d7_contract_liabilities", "ADAPTER_ID", True, True),
    # 🔴 E1（2026-09-26 纳入）：spec e1-sync-coverage-and-first-canary 交付的第 9 个 contract。
    #    它是**引擎落地后新建的第一个 entry** ⇒ 把它纳入零回归门，可在后续引擎改动时立刻发现
    #    「薄转发层」是否被破坏（它的投影/合并全是 ≤3 行转发，任何 digest 漂移都来自引擎本身）。
    #    instrumentation 取复数（两个受管 sheet：e12-managed / e14-managed）。
    ("e1", "phase5_e1_monetary_fund", "ADAPTER_ID", True, True),
    # ── F1 canary（spec: f1-sync-coverage-and-first-canary）──────
    ("f1", "phase5_f1_prepayment", "ADAPTER_ID", True, True),
    # ── G2 canary（spec: g-cycle-sync-foundation-and-first-canary · Task 14）──
    #    🔴 G 循环**首条**纳入零回归门的 provider。`plural_instr=True`：它的
    #    `instrumentation_definition_payload()` 走
    #    `build_instrumentation_payload_for_sheets(specs=instrumentation_specs())`，
    #    注册路径读的是**复数**。留 False 会让本判据只核主 sheet 单 spec ⇒
    #    将来灰度开关打开 G2-3/G2-5/G2-6/G2-8 时扩容面对判据完全不可见（D2 注释警告过的假绿）。
    ("g2", "phase5_g2_interest_receivable", "ADAPTER_ID", True, True),
    # ── H9 canary（spec: h-cycle-sync-foundation-and-first-canary · Task 20）──
    #    🔴 H 循环**首条**纳入零回归门的 provider。`plural_instr=True`：它的
    #    `instrumentation_definition_payload()` 走 `build_instrumentation_payload_for_sheets`，
    #    注册路径读的是**复数**。留 False 会让本判据只核主 sheet 单 spec ⇒
    #    将来打开 H9-1/H9-3/H9-4 等灰度开关时扩容面对判据完全不可见（D2 注释警告过的假绿）。
    #    🔴 H9 是首个 `header_rows` 域扩容（3→4）之后落地的契约 —— 它本身是 2 级，
    #    但同循环的 H2/H4/H5/H7/H8 是 4 级；本门的 digest 会在扩容被回退时打红。
    ("h9", "phase5_h9_lease_liabilities", "ADAPTER_ID", True, True),
    # ── G9（spec: g-cycle-single-region-detail-lanes · Task 8 / C-5）────────
    #    🔴 全库**首个「一个 store 键 × 三个受管区」** provider：`明细表G9-2` 的
    #    R12-16 / R19-23 / R26-28 三区行都存在同一个 `G9-detail-rows` 数组里，区归属由
    #    行的 `section` 字段表达（引擎 `row_section_field`）。
    #    `plural_instr=True` 是**硬要求**（不是像 G2 那样的前瞻性）：它的
    #    `instrumentation_specs()` 恒返 3 条（逐区不同 `uuid_col` AC/AD/AE 与
    #    `template_id` G92R1/R2/R3）；留 False 只核第一条 ⇒ 区②③的 definedName
    #    与 UUID 列声明对本门完全不可见。
    #    `has_projection=True`：`build_store_projection` 缺省合并三段（见 provider
    #    docstring —— 只投区①会让 digest 算得出来却漏掉三分之二的行，假绿）。
    ("g9", "phase5_g9_other_noncurrent", "ADAPTER_ID", True, True),
    # ── G10（spec: g-cycle-single-region-detail-lanes · Task 9 / C-7）───────
    #    单区（`明细表G10-2` R11-R20）⇒ `instrumentation_specs()` 恒返 1 条，但
    #    `plural_instr=True` 仍是**必需**的：provider 的
    #    `instrumentation_definition_payload()` 走
    #    `build_instrumentation_payload_for_sheets(specs=…)`，注册路径读的是复数形态；
    #    留 False 会让本门按单 spec 口径现算，digest 与注册路径实际用的那份不同源
    #    （形态同 G2 —— 单 sheet 也走复数 API）。
    ("g10", "phase5_g10_trading_liabilities", "ADAPTER_ID", True, True),
    # ── G8（spec: g-cycle-single-region-detail-lanes · Task 9b / C-8）────────
    #    与 G10 同形（单区 + 复数 instrumentation API）⇒ 两个 True 同理。
    #    🔴 本条的 digest 会在「R/T 两列被误改回 mode=formula」时变动 —— 那种改动会让
    #    `excel_materialize` 在 R13-R20/R12 上抛 ProtectedRegionWriteError（模板那几格
    #    没有公式），本门先一步把它拦在 digest 漂移上。
    ("g8", "phase5_g8_other_equity", "ADAPTER_ID", True, True),
    # ── G14（spec: g-cycle-single-region-detail-lanes · Task 10 / C-9）───────
    #    与 G8/G10 同形（单区 + 复数 instrumentation API）⇒ 两个 True 同理。
    #    🔴 本条的 projection digest 会在两种误改上打红：① 行身份被从 `rowKey` 改成
    #    `rowId`（`_synthetic_rows` 现取 `spec.row_identity_key` 造行）② `L` 列的
    #    `value_type` 被从 boolean 改回 amount（裁决 G1R-H4 的布尔列会退化成数值列）。
    ("g14", "phase5_g14_credit_impairment", "ADAPTER_ID", True, True),
    # ── G11（spec: g-cycle-single-region-detail-lanes · Task 11 / C-10）──────
    #    🔴 本条的 contract digest 会在三种误改上打红：① `header_rows` 从 **1** 被改成 2
    #    （G11 是九条唯一的单级表头，R8 是段标题不是组行）② `G`/`K` 从 `auto_source` 被改回
    #    `formula`（受管表自带 44 格裸 IF，中性化后那两列无公式 ⇒ materialize 会抛
    #    `ProtectedRegionWriteError`，本门先一步拦在 digest 漂移上）③ 行身份从 `id` 改成 `rowId`。
    ("g11", "phase5_g11_investment_income", "ADAPTER_ID", True, True),
    # ── G13（spec: g-cycle-single-region-detail-lanes · Task 12 / C-11）───────
    #    🔴 本条的 contract digest 会在四种误改上打红：① store item 从
    #    `G13-detail-skeleton` 被改回工具明细键 `G13-detail-rows`（接错载体 ⇒ 模板固定
    #    10 行会按序吃到动态工具行，产出错数）② `header_rows` 从 **2** 被改成 1
    #    ③ `B`/`C` 从 `editable` 被改成 `formula`（两列只有父行 R11/R14/R17 三格有公式，
    #    判 formula 会让 materialize 对其余 7 格抛 `ProtectedRegionWriteError`）
    #    ④ 行身份从 `rowKey` 改成 `rowId`。
    ("g13", "phase5_g13_fair_value_changes", "ADAPTER_ID", True, True),
    # ── G12（spec: g-cycle-single-region-detail-lanes · Task 13 / C-12）───────
    #    🔴 本条的 contract digest 会在五种误改上打红：① `header_rows` 从 **2** 被改回 0/1
    #    （spec 原文的「无表头行」前提已被 Task 2 实测推翻 —— R7/R8 是两级表头）
    #    ② `formula_mask` 从**空**变成非空（数据区没有任何一列每行都有公式：`G` 只 R9 一格、
    #    `I` 只 R9/R10 两格 ⇒ 判 formula 会让 materialize 抛）③ `G` 从 `editable+boolean`
    #    被改成 `formula` ④ `uuid_col` 从 **K** 变成 `P`（有效列 10 < max_column=15，
    #    按有效列右移一列取；取 P 会把 5 个空尾列圈进受管区）⑤ 行身份从 `rowId` 改成 `rowKey`。
    ("g12", "phase5_g12_net_hedge_gains", "ADAPTER_ID", True, True),
)


def _canonical_sha256(payload: Any) -> str:
    """canonical JSON（sort_keys + 紧凑分隔符 + 非 ASCII 原样）的 sha256。"""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _import_provider(module_name: str) -> Any:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    # 🔴 事故教训（2026-09-26）：实测一次 `--update` 曾在 __pycache__ 存在过期/竞态 .pyc 时
    # 读到与当前源码不一致的 build_contract_payload 输出（D2-3 双区开关那次改动一度被漏掉，
    # 直接 `python -c "import ...; m.build_contract_payload()"` 验证是正常的，但本脚本走
    # importlib 却报 NameError）。手动清空 __pycache__ 后复现消失、结果与直接 import 一致。
    # 为避免复发，本函数在同进程重复调用时强制 reload；调用方（run()）额外建议先手动清一次缓存。
    module = f"app.services.workpaper_sync.{module_name}"
    if module in sys.modules:
        importlib.reload(sys.modules[module])
        return sys.modules[module]
    return importlib.import_module(module)


def _field_specs_and_row_key(mod: Any) -> tuple[tuple, str]:
    """取该 provider 的字段清单与行身份键，**兼容两种形态**。

    * **未声明化 / 部分声明化的家**（D1/D2/D5/D6/D7/D4）：模块级 `MANAGED_FIELD_SPECS`
      （6 或 7 元组）+ `ROW_IDENTITY_STORE_KEY`。
    * **引擎落地后新建的家**（E1）：没有那两个模块级常量 —— 字段在 `RowTableSheetSpec` 上。
      从 `managed_row_table_specs()` 取第一个受管 spec（= `STORE_ITEM_ID` 对应的 canary），
      用引擎的 `managed_field_specs()` 展开。

    🔴 不用 `hasattr` 试探链而是**按形态二分**：前者有 MANAGED_FIELD_SPECS 就一定是前者，
       没有就必须能给出 spec —— 两者都拿不到时显式抛，不静默返回空清单（空清单会让合成
       payload 变成「只有 rowId 的行」，digest 照样算得出来却什么都没覆盖到）。
    """
    specs = getattr(mod, "MANAGED_FIELD_SPECS", None)
    if specs:
        return tuple(specs), getattr(mod, "ROW_IDENTITY_STORE_KEY", "rowId"), {}

    get_specs = getattr(mod, "managed_row_table_specs", None)
    if callable(get_specs):
        row_specs = get_specs()
        if row_specs:
            from app.services.workpaper_sync.phase5_row_table_sheet import (
                managed_field_specs,
            )

            target_item = getattr(mod, "STORE_ITEM_ID", None)
            spec = next(
                (s for s in row_specs if s.store_item_id == target_item), row_specs[0]
            )
            # 🔴 分段受管（`row_section_field`，G9 首例）：合成行必须带上段标记，否则
            #    引擎的 `iter_store_rows` 会把每一行都当「不属本段」过滤掉 ⇒ projection
            #    为空、digest 照样算得出来却什么都没覆盖到（本函数 docstring 警告的假绿
            #    的另一种形态）。段值从 spec 现取，不按 provider 名硬编码。
            stamp: dict[str, Any] = {}
            section_field = getattr(spec, "row_section_field", "") or ""
            if section_field:
                stamp[section_field] = getattr(spec, "row_section_value", "")
            return managed_field_specs(spec), spec.row_identity_key, stamp

    raise RuntimeError(
        f"{mod.__name__} 既无 MANAGED_FIELD_SPECS 也无 managed_row_table_specs() 受管清单 —— "
        "无法造合成 payload；空清单会让 digest 算得出来却什么都没覆盖到（假绿）"
    )


def _synthetic_rows(mod: Any) -> list[dict[str, Any]]:
    """按 provider 的字段清单现造两行合成载荷（不手抄，字段全填占位值）。

    field_specs 第 4 列是 store json 键/路径（camelCase 或 nested `a/b`）。text/enum
    填字符串占位，amount/integer 填数值占位；nested 路径逐级建 dict。每行带稳定行身份。
    """
    specs, row_key, stamp = _field_specs_and_row_key(mod)
    rows: list[dict[str, Any]] = []
    for i in range(2):
        row: dict[str, Any] = {row_key: f"synthetic-{i}", **stamp}
        for spec in specs:
            # spec: (column_key, column, mode, value_type, json_key/path, header_text[, group])
            value_type = spec[3]
            json_path = spec[4]
            val: Any = (i + 1) * 100 if value_type in {"amount", "integer"} else f"v{i}"
            parts = str(json_path).split("/")
            cursor = row
            for seg in parts[:-1]:
                nxt = cursor.get(seg)
                if not isinstance(nxt, dict):
                    nxt = {}
                    cursor[seg] = nxt
                cursor = nxt
            cursor[parts[-1]] = val
        rows.append(row)
    return rows


def _digests_for(label: str, module_name: str, adapter_const: str,
                 has_projection: bool, plural_instr: bool) -> dict[str, Any]:
    mod = _import_provider(module_name)
    adapter_id = getattr(mod, adapter_const)

    # 1. contract payload（整体 digest + 🔴 per-sheet 粒度 digest）
    contract_payload = mod.build_contract_payload()
    contract_digest = _canonical_sha256(contract_payload)
    # 🔴 P1-4 复盘修复：sheet 粒度 digest —— 扩容一张 sheet 只应改动那一张的 digest，
    # 其余 sheet（如 D2-2）逐字节不变才是 Q1 的干净证明。整体 digest 无法区分「扩容
    # 新 sheet」与「改动已有 sheet」，sheet 粒度才能。
    sheet_digests = {
        str(s.get("sheet_key") or s.get("excel_name") or i): _canonical_sha256(s)
        for i, s in enumerate(contract_payload.get("sheets") or [])
    }

    # 2. store projection（合成 payload 驱动；B60 无该路径 ⇒ null）
    if has_projection:
        from app.services.workpaper_sync.contracts import parse_contract

        contract = parse_contract(contract_payload, adapter_id=adapter_id)
        rows = _synthetic_rows(mod)
        projection = mod.build_store_projection(rows, contract=contract)
        # Projection 的 canonical 形态：按 stable_key 排序的 (key, value, value_type, mode, row_key)
        proj_canonical = {
            "contract_id": projection.contract_id,
            "semantic_version": projection.semantic_version,
            "document_type": projection.document_type,
            "values": sorted(
                (
                    [
                        k,
                        (fv.value if (fv := projection.get(k)) else None),
                        (fv.value_type if fv else None),
                        (fv.mode if fv else None),
                        (fv.row_key if fv else None),
                    ]
                    for k in projection.stable_keys()
                ),
                key=lambda e: e[0],
            ),
            "row_keys": {k: list(v) for k, v in sorted(projection.row_keys.items())},
        }
        projection_digest: str | None = _canonical_sha256(proj_canonical)
    else:
        projection_digest = None

    # 3. instrumentation spec(s)
    if plural_instr and hasattr(mod, "instrumentation_specs"):
        specs = mod.instrumentation_specs()
        instr_canonical = [_instr_to_dict(s) for s in specs]
    else:
        instr_canonical = _instr_to_dict(mod.instrumentation_spec())
    instr_digest = _canonical_sha256(instr_canonical)

    return {
        "label": label,
        "adapter_id": adapter_id,
        "contract_payload_sha256": contract_digest,
        "sheet_digests": sheet_digests,
        "store_projection_sha256": projection_digest,
        "instrumentation_sha256": instr_digest,
    }


def _instr_to_dict(spec: Any) -> dict[str, Any]:
    """ExcelInstrumentationSpec → 稳定 dict（按其 dataclass 字段名，缺则跳过）。"""
    fields = (
        "entry_id", "template_id", "template_relative_path", "managed_sheet",
        "sheet_key", "table_key", "first_data_row", "last_data_row", "footer_row",
        "header_row", "managed_last_col", "uuid_col", "table_name",
        # 🔴 静态区寄生声明（D2-1 的 `static_sheets`）也必须进 digest —— 否则 D2-1 扩容面
        #    对判据不可见（假绿）。值本身是 list[dict]，canonical_sha256 会稳定序列化。
        "static_sheets",
    )
    out: dict[str, Any] = {}
    for f in fields:
        if hasattr(spec, f):
            v = getattr(spec, f)
            # static_sheets 是 tuple → 转 list 保证 JSON 稳定；None/() 一律省略保持向后兼容。
            if f == "static_sheets":
                if not v:
                    continue
                v = [dict(s) for s in v]
            out[f] = v
    return out


def run() -> dict[str, Any]:
    entries = [
        _digests_for(label, mod, const, hp, pl)
        for (label, mod, const, hp, pl) in PROVIDERS
    ]
    # digest 总数：每家 contract + instrumentation（必有）+ projection（B60 无）
    #   + 🔴 P1-4 sheet 粒度 digest（第二轮复盘问题 5 修复：此前 sheet_digests 字段已被
    #     _compare 消费用于判定漂移，但从未计入 digest_count/--update 打印摘要，数字失真、
    #     低估了本判据实际覆盖的判据面）。
    total = sum(
        1  # contract
        + 1  # instrumentation
        + (1 if e["store_projection_sha256"] is not None else 0)
        + len(e.get("sheet_digests") or {})
        for e in entries
    )
    return {"digest_count": total, "providers": entries}


def _load_baseline() -> dict[str, Any] | None:
    if not _DIGEST_PATH.exists():
        return None
    return json.loads(_DIGEST_PATH.read_text(encoding="utf-8"))


def _compare(current: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    base_by_label = {p["label"]: p for p in baseline.get("providers", [])}
    for cur in current["providers"]:
        base = base_by_label.get(cur["label"])
        if base is None:
            drift.append({"label": cur["label"], "field": "*", "disk": "<缺基线>", "source": "<新增>"})
            continue
        for field in ("store_projection_sha256", "instrumentation_sha256"):
            if cur.get(field) != base.get(field):
                drift.append({
                    "label": cur["label"],
                    "field": field,
                    "disk": str(base.get(field)),
                    "source": str(cur.get(field)),
                })
        # 🔴 P1-4：contract 整体 digest 变化时，用 sheet 粒度定位 —— 只对**已有 sheet 被改动**
        # 报 drift；新增 sheet（base 无该 key）是 additive，不算回归（扩容的预期形态）。
        base_sheets = base.get("sheet_digests") or {}
        cur_sheets = cur.get("sheet_digests") or {}
        for sk, base_sd in base_sheets.items():
            cur_sd = cur_sheets.get(sk)
            if cur_sd is None:
                drift.append({"label": cur["label"], "field": f"sheet[{sk}]", "disk": str(base_sd), "source": "<被删>"})
            elif cur_sd != base_sd:
                drift.append({"label": cur["label"], "field": f"sheet[{sk}]", "disk": str(base_sd), "source": str(cur_sd)})
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="把当前 digest 写为新基线（抽取前首次）")
    parser.add_argument("--json", type=str, default=None, help="把报告写到该路径")
    args = parser.parse_args()

    current = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.update:
        _DIGEST_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✅ 已写基线：{current['digest_count']} 个 digest → {_DIGEST_PATH.name}")
        for p in current["providers"]:
            print(f"   {p['label']:>4}  contract={p['contract_payload_sha256'][:12]} "
                  f"projection={(p['store_projection_sha256'] or 'N/A')[:12]:>12} "
                  f"instr={p['instrumentation_sha256'][:12]}")
        return 0

    baseline = _load_baseline()
    if baseline is None:
        print("❌ 未找到基线文件 —— 请先 --update 取抽取前基线")
        return 1

    drift = _compare(current, baseline)
    if not drift:
        print(f"✅ golden digest 零回归：{current['digest_count']} 个 digest 逐个不变")
        return 0

    print("❌ golden digest 发生漂移（引擎抽取改变了已交付 contract 的行为，"
          "或基线取样时间点落后于并发改动 —— 两种情况都要先排查是哪个）：")
    for d in drift:
        print(f"   [{d['label']}] {d['field']}: 基线={d['disk'][:16]} 现算={d['source'][:16]}")
    print("\n排查顺序：")
    print("  1. `git status --porcelain -- app/services/workpaper_sync/<该 provider 模块>.py`")
    print("     —— 若该文件有非你本次改动的未提交改动（并发会话），基线本身已过期，")
    print("        应先 `--update` 重取真实当前基线，再验证你自己的改动是否零回归。")
    print("  2. 若该 provider 正是你本次改动的对象，落全量 diff 排查：对比抽取前后的")
    print("     build_contract_payload/build_store_projection/instrumentation_spec 输出")
    print("     （Requirement 4.2）—— 这才是真实回归。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
