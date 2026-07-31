#!/usr/bin/env python
"""附注「固定资产」章节补齐 columns 列元数据（幂等修订）。

**目标**：附注模板固定资产章节（上市 §五、22 / 国企 §八、22）的所有子表此前
**全部缺 `columns`**（只有 `headers` + `rows`）→ seed 路径（新建项目 / 重新生成附注）
会走 `note_sub_table_projector._infer_groups_from_headers` 前缀推断，把国企「固定资产
情况」的 `本期增加 / 本期减少` 凭空归到「本期」父表头，且金额列无 `format=amount`。

源模板固定资产各表**全部是单行表头**（无两级）→ 一律显式 `flat`。列 `key` 逐字
镜像同步载荷（`h1DisclosureSyncPayload.ts` 的 `H1_SOE_COLUMNS` / `buildH1ListedColumns`），
使 seed 路径与推送路径列键一致、附注 TAB 首列名（`columns[0].label`）= `headers[0]`。

本脚本**只补 columns**（+派生 `_column_groups` 恒空=单级）：rows / guidance /
text_sections 已由既有模板正确承载，不改动。

权威源（三者互证）：

- `backend/wp_templates/H/H1 固定资产.xlsx` 的两张披露 sheet（上市 6 表 / 国企 5 表）；
- `note_template_{listed,soe}.json` §五、22 / §八、22 既有 headers（交付物权威）；
- `h1DisclosureSyncPayload.ts`（列 key 权威——推送路径已验证）。

裁决要点：

- 国企比上市少一张「通过经营租赁租出的固定资产」（源模板国企 sheet 无此段）；
- 汇总 / 清理两表列名两版不同：上市「期末余额 / 上年年末余额」，
  国企「期末账面价值 / 期初账面价值」（源 xlsx 实测，不可统一）；
- 上市「固定资产情况」列 = 资产类别（房屋及建筑物 / 机器设备 / 运输设备 / 办公设备 /
  其他设备）+ 合计；seed 保留五类，底稿同步时按项目实际类别整表覆盖。

Usage::

    python backend/scripts/fix/fix_note_h1_fixed_assets_structure.py --dry-run
    python backend/scripts/fix/fix_note_h1_fixed_assets_structure.py
    python backend/scripts/fix/fix_note_h1_fixed_assets_structure.py --check
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    flat_columns,
    rule,
    run_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、22"
SOE_SECTION = "八、22"
ALIGNED_BY = "h1-fixed-assets-mapping-and-disclosure-alignment"

# ── 表名（与 h1NoteSectionMap.ts 的 H1_*_SUBTABLE 及模板 tables[].name 逐字一致）──
T_SUMMARY = "固定资产"
T_MOVEMENT = "固定资产情况"
T_IDLE = "暂时闲置的固定资产情况"
T_LEASE = "通过经营租赁租出的固定资产"  # 仅上市
T_TITLE = "未办妥产权证书的固定资产情况"
T_CLEARING = "固定资产清理"

# 上市「固定资产情况」资产类别列（seed 默认五类；同步时按项目实际类别整表覆盖）
_LISTED_MOVEMENT_CATEGORIES = ("房屋及建筑物", "机器设备", "运输设备", "办公设备", "其他设备")

_IDLE_COLS = flat_columns([
    ("label", "项目", None),
    ("cost", "账面原值", AMOUNT),
    ("dep", "累计折旧", AMOUNT),
    ("impairment", "减值准备", AMOUNT),
    ("book_value", "账面价值", AMOUNT),
    ("remark", "备注", None),
])
_SOE_IDLE_COLS = flat_columns([
    ("label", "项目", None),
    ("original_cost", "账面原值", AMOUNT),
    ("accum_dep", "累计折旧", AMOUNT),
    ("impairment", "减值准备", AMOUNT),
    ("carrying", "账面价值", AMOUNT),
    ("remark", "备注", None),
])


def _listed_plan() -> list[dict]:
    return [
        rule(T_SUMMARY, flat_columns([
            ("label", "项目", None),
            ("end_balance", "期末余额", AMOUNT),
            ("prior_balance", "上年年末余额", AMOUNT),
        ]), None, ""),
        rule(T_MOVEMENT, flat_columns([
            ("label", "项目", None),
            *[(c, c, AMOUNT) for c in _LISTED_MOVEMENT_CATEGORIES],
            ("合计", "合计", AMOUNT),
        ]), None, ""),
        rule(T_IDLE, _IDLE_COLS, None, ""),
        rule(T_LEASE, flat_columns([
            ("label", "项目", None),
            ("book_value", "账面价值", AMOUNT),
        ]), None, ""),
        rule(T_TITLE, flat_columns([
            ("label", "项目", None),
            ("book_value", "账面价值", AMOUNT),
            ("reason", "未办妥产权证书原因", None),
        ]), None, ""),
        rule(T_CLEARING, flat_columns([
            ("label", "项目", None),
            ("end_balance", "期末余额", AMOUNT),
            ("prior_balance", "上年年末余额", AMOUNT),
            ("reason", "转入清理的原因", None),
        ]), None, ""),
    ]


def _soe_plan() -> list[dict]:
    return [
        rule(T_SUMMARY, flat_columns([
            ("label", "项目", None),
            ("end_carrying", "期末账面价值", AMOUNT),
            ("begin_carrying", "期初账面价值", AMOUNT),
        ]), None, ""),
        rule(T_MOVEMENT, flat_columns([
            ("label", "项目", None),
            ("begin", "期初余额", AMOUNT),
            ("increase", "本期增加", AMOUNT),
            ("decrease", "本期减少", AMOUNT),
            ("end", "期末余额", AMOUNT),
        ]), None, ""),
        rule(T_IDLE, _SOE_IDLE_COLS, None, ""),
        rule(T_TITLE, flat_columns([
            ("label", "项目", None),
            ("carrying", "账面价值", AMOUNT),
            ("reason", "未办妥产权证书原因", None),
        ]), None, ""),
        rule(T_CLEARING, flat_columns([
            ("label", "项目", None),
            ("end_carrying", "期末账面价值", AMOUNT),
            ("begin_carrying", "期初账面价值", AMOUNT),
            ("reason", "转入清理的原因", None),
        ]), None, ""),
    ]


EXPECTED = {
    "listed": [T_SUMMARY, T_MOVEMENT, T_IDLE, T_LEASE, T_TITLE, T_CLEARING],
    "soe": [T_SUMMARY, T_MOVEMENT, T_IDLE, T_TITLE, T_CLEARING],
}

_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan),
}
_LABELS = {
    "listed": "note_template_listed.json §五、22 固定资产（上市）",
    "soe": "note_template_soe.json §八、22 固定资产（国企）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


main = build_cli("附注固定资产章节补齐 columns（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
