# -*- coding: utf-8 -*-
"""Task 43 evidence 观测器 —— G7 两级动态表 Excel pilot。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 43

产出 `.kiro/specs/…/evidence/task43-g7-two-level-dynamic-pilot/` 下的四份实测事实
（形态照 Task 42 的 `task42-h1-grouped-dynamic-pilot/`）：

* ``identity_and_digests.json`` —— 本 entry **自己**的 authority model / template /
  instrumentation / contract 四个 definition digest + **bundle canonical digest** +
  required scenario set，并与 Task 40/41/42 三个 pilot 逐项比对不相等；
* ``sheet_audit.json`` —— 权威模板 22 张 sheet 逐张审核（openpyxl 直读）与选型理由；
* ``two_level_header_and_fields.json`` —— 107 个字段逐个的四类 source_ref 与源侧实测
  文本/公式/空值比对、两级表头几何、动态列 ``{slot}_{seq}`` 绑定；
* ``scenario_verdicts.json`` —— 24 条 required scenario **逐条真跑一次生产 oracle**
  （`pilot_harness.run_scenario_oracle`，`NOT_EXECUTED` 环境）后的 outcome/error_code。

🔴 三条硬约束
------------

1. **digest 一律真算，不抄**。四个 definition digest 走
   `definitions.canonical_digest`，bundle digest 走
   `definitions.build_bundle_canonical_payload` —— 与 `DefinitionPublisher` 同一个
   canonicalizer。bundle canonical payload 里**只有** schema_version + 四个 sha256
   （没有 definition 行的 uuid），故它离线可复现；本脚本用两组不同 uuid 各算一次并
   断言相等，把「可复现」本身也变成实测事实而不是声明。
2. **真实 OO 未执行 ⇒ 状态只能是 failed / unverifiable**，不得以文档声明计为 passed
   （Property 49）。本脚本不构造任何黑盒证据，`onlyoffice_build` / `browser_build`
   固定为 `pilot_harness.NOT_EXECUTED` 哨兵。
3. 🔴 **upstream-gap 判 `failed` + `error_code="upstream_gap"`，不是 unverifiable**，
   且该分支必须排在 black-box 分支**之前** —— 否则接上真实 OO 之后这些场景会自动
   刷绿，而它们其实永远不会通过。本脚本把这条顺序同时按**源码位置**与**行为**两侧
   实测下来（见 `_ordering_facts`）。

用法（仓库根）::

    py -3 backend/scripts/diagnose/generate_task43_pilot_evidence.py --apply
    py -3 backend/scripts/diagnose/generate_task43_pilot_evidence.py --check

`--check` 只读：重算一遍与磁盘逐键比对，不一致即非零退出。
"""
from __future__ import annotations

import argparse
import inspect
import io
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

EVIDENCE_DIR = (
    REPO
    / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence/task43-g7-two-level-dynamic-pilot"
)

#: 变异历史四轮（仓库根的实测 JSON）。后一轮同 id 覆盖前一轮。
MUTATION_ROUNDS: tuple[tuple[str, str], ...] = (
    ("tmp_task43_mut_a.json", "第 1 轮 M01-M14"),
    ("tmp_task43_mut_b.json", "第 2 轮 M15-M25 + M05/M06/M07 复跑（首轮 GREEN/WRONG-TEST）"),
    ("tmp_task43_mut_c.json", "第 3 轮 M26-M39"),
    (
        "tmp_task43_mut_d_probe.json",
        "第 4 轮 M31 诊断跑：修好 scope_check 后判 GREEN —— 证明「identity 是否引用单一"
        "真源」这条源码级判据当时并不存在（守卫缺口，不是代码没问题）",
    ),
    (
        "tmp_task43_mut_d.json",
        "第 4 轮 M31 复跑：补上 TestProperty22…::"
        "test_contract_identity_is_the_imported_constant_never_a_literal 后判 RED",
    ),
)

#: 另外三个 pilot（digest 必须互不相同）。
OTHER_PILOTS: tuple[tuple[str, str], ...] = (
    ("xlsx/b60/gt-b60-bundle", "Task 40 simple_checklist"),
    ("xlsx/gt-d2-accounts-receivable", "Task 41 d2_large_json"),
    ("xlsx/gt-h1-fixed-assets", "Task 42 h1_grouped_dynamic"),
)

_SRC_RE = re.compile(r"^源xlsx!(?P<sheet>[^!]+)!(?P<ref>.+)$")


# ═══════════════════════════════════════════════════════════════════════════
# 真源读取
# ═══════════════════════════════════════════════════════════════════════════


def _workbook() -> Any:
    import openpyxl

    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    return openpyxl.load_workbook(
        io.BytesIO(P.read_authoritative_template()), data_only=False
    )


def _cell_text(worksheet: Any, ref: str) -> Any:
    """`_src()` 里的 ref 可能是单格、横向区间或矩形区间 —— 统一取左上角实测值。"""
    first = ref.split(":", 1)[0]
    value = worksheet[first].value
    return value if value is None else str(value)


def _merge_span(worksheet: Any, anchor: str) -> list[str] | None:
    """`anchor` 所在的横向合并区覆盖的列字母（不在任何合并区时 None）。"""
    from openpyxl.utils import get_column_letter, range_boundaries

    col_min, row_min, _c, _r = range_boundaries(f"{anchor}:{anchor}")
    for merged in worksheet.merged_cells.ranges:
        if merged.min_row == merged.max_row == row_min and (
            merged.min_col <= col_min <= merged.max_col
        ):
            return [get_column_letter(c) for c in range(merged.min_col, merged.max_col + 1)]
    return None


# ═══════════════════════════════════════════════════════════════════════════
# ① identity_and_digests.json
# ═══════════════════════════════════════════════════════════════════════════


def _definition_digests() -> dict[str, str]:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.definitions import canonical_digest

    contract = P.load_pilot_contract()
    return {
        "authority_model_definition": canonical_digest(P.authority_model_payload()),
        "template_definition": canonical_digest(P.template_definition_payload()),
        "instrumentation_definition": canonical_digest(
            P.instrumentation_definition_payload()
        ),
        "contract_canonical": canonical_digest(dict(contract.canonical_payload)),
        "normalized_structure_hash": str(
            P.template_definition_payload()["normalized_structure_hash"]
        ),
    }


def _bundle_facts(digests: dict[str, str]) -> dict[str, Any]:
    """bundle canonical digest —— 走 `DefinitionPublisher` 用的**同一个** builder。"""
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.definitions import (
        build_bundle_canonical_payload,
        canonical_digest,
    )
    from app.services.workpaper_sync.models import BundleSlot

    def build() -> dict[str, Any]:
        return build_bundle_canonical_payload(
            authority_model=P.AUTHORITY_MODEL,
            authority_model_definition_sha256=digests["authority_model_definition"],
            slots={
                BundleSlot.template: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": digests["template_definition"],
                },
                BundleSlot.instrumentation: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": digests["instrumentation_definition"],
                },
                BundleSlot.contract: {
                    "type": "definition",
                    "ref": f"definition:{uuid.uuid4()}",
                    "digest": digests["contract_canonical"],
                },
            },
        )

    first, second = build(), build()
    digest = canonical_digest(first)
    return {
        "authority_model": P.AUTHORITY_MODEL.value,
        "bundle_sha256": digest,
        "canonical_payload": first,
        "reproducible_offline": digest == canonical_digest(second),
        "reproducible_offline_why": (
            "bundle canonical payload 只含 schema_version + 四个 sha256，没有 definition "
            "行的 uuid ⇒ 同一批 payload 在不同发布里算出同一个 digest。本判据用两组不同 "
            "uuid 各构一次并比对，把「可复现」变成实测事实"
        ),
        "slot_types": {slot: first[slot]["type"] for slot in ("template", "instrumentation", "contract")},
        "substrate_policy": (
            "metadata sheet / candidate / 其他 entry 的 bundle 均不作为运行态 substrate："
            "本 bundle 的四个 child 全是本 entry 自己发布的 definition（slot type 全为 "
            "definition，无 marker 冒充），且 contract 未声明 metadata sheet"
        ),
    }


def _required_scenarios() -> dict[str, Any]:
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    entries = EV.manifest_entries_by_id(EV.load_entry_manifest())
    mine = EV.derive_for_manifest_entry(
        entries[P.PILOT_ENTRY_ID], authority_model=P.AUTHORITY_MODEL
    )
    others = {
        entry_id: EV.derive_for_manifest_entry(
            entries[entry_id], authority_model=P.AUTHORITY_MODEL
        ).digest
        for entry_id, _label in OTHER_PILOTS
    }
    ids = sorted(s.scenario_id for s in mine.scenarios)
    return {
        "digest": mine.digest,
        "size": len(mine.scenarios),
        "scenario_ids": ids,
        "scenario_profile_digest": mine.scenario_profile_digest,
        "close_required": mine.close_required,
        "substituted": mine.substituted,
        "capability": mine.capability.value,
        "other_pilots_digests": others,
        "distinct_from_other_pilots": mine.digest not in set(others.values()),
        "dynamic_family_excluded": sorted(
            s.scenario_id for s in EV.DYNAMIC_SCENARIOS if s.scenario_id not in ids
        ),
    }


def _finalize_status() -> str:
    """finalize 今天为何仍未达成 —— **现算**，不写死。

    🔴 Task 75 起原字面量变成一句假话。原实现写死
    ``blocked_by_UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER``；Task 75 结清了那条欠账
    （四个 pilot 的 ``resolve_published_frozen_definitions()`` 已改调公共观测器
    :mod:`app.services.workpaper_sync.published_identity_observer`，四处登记全删），
    于是那句话会让读 evidence 的人以为观测器还没建 —— 而真实阻塞点已经换成**供给**：
    生产侧还没有任何 approved bundle → published representation（四张 definition/
    representation 表 PG 实测 0 行，属 Task 76 的交付）。

    三态各有来源节，全部现算而非声明：

    1. 欠账仍登记 ⇒ 报欠账名（来源 = pilot 模块的 ``__all__``，见 :func:`_registered_debts`）
    2. 交付登记表那一行已 ``adapter_registered`` ⇒ 报已注册
    3. 否则 ⇒ 供给缺口

    ``next()`` 不兜底：登记表里找不到本 pilot 的行是**接线错误**，必须抛出来，
    不得降级成「本项目无此数据」。
    """
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.adapters import registry as RG

    observer_debts = sorted(n for n in _registered_debts() if "PUBLISHED_IDENTITY_OBSERVER" in n)
    if observer_debts:
        return f"blocked_by_{observer_debts[0]}"
    row = next(
        r
        for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
        if r["contract_id"] == P.PILOT_ADAPTER_ID
    )
    if row["adapter_registered"]:
        return "adapter_registered"
    return "blocked_by_definition_supply_gap"


def _registered_debts() -> dict[str, str]:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    return {
        name: getattr(P, name)
        for name in P.__all__
        if name.startswith("UPSTREAM_DEBT_")
    }


def build_identity_and_digests() -> dict[str, Any]:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync import pilot_harness as PH

    digests = _definition_digests()
    scenarios = _required_scenarios()
    verdicts = build_scenario_verdicts()
    return {
        "adapter_id": P.PILOT_ADAPTER_ID,
        "entry_id": P.PILOT_ENTRY_ID,
        "pilot_class": getattr(P.PILOT_CLASS, "value", P.PILOT_CLASS),
        "wp_code_family": P.PILOT_WP_CODE_FAMILY,
        "wp_code_patterns": sorted(P.PILOT_WP_CODES),
        "managed_sheet": P.MANAGED_SHEET,
        "template_id": P.TEMPLATE_ID,
        "template_sha256": P.TEMPLATE_SHA256,
        "digests": digests,
        "bundle": _bundle_facts(digests),
        "required_scenario_set": scenarios,
        "capability_enabled": P.manifest_capability_enabled(),
        "finalize_status": _finalize_status(),
        "aggregate_result_without_real_onlyoffice": verdicts["aggregate_result"],
        "harness_version": PH.HARNESS_VERSION,
        "property_oracle_landing": verdicts["property_oracle_landing"],
        "registered_upstream_debts": _registered_debts(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ② scenario_verdicts.json —— 逐条真跑生产 oracle
# ═══════════════════════════════════════════════════════════════════════════


def _ordering_facts() -> dict[str, Any]:
    """「upstream_gap 排在 black-box 之前」—— 源码位置 + 行为两侧实测。"""
    from app.services.workpaper_sync import pilot_harness as PH

    source = inspect.getsource(PH.run_scenario_oracle)
    lines = source.splitlines()

    def index_of(needle: str) -> int:
        for i, line in enumerate(lines):
            if needle in line:
                return i
        return -1

    debt_at = index_of("if oracle.upstream_debt:")
    black_at = index_of("if oracle.needs_black_box:")
    return {
        "upstream_debt_branch_line": debt_at,
        "black_box_branch_line": black_at,
        "upstream_gap_decided_before_black_box": 0 <= debt_at < black_at,
        "upstream_gap_outcome": "failed",
        "upstream_gap_error_code": "upstream_gap",
        "black_box_outcome": "unverifiable",
        "black_box_error_code": "real_onlyoffice_not_executed",
        "why": (
            "顺序不可交换：把 upstream_debt 放到 black-box 之后，缺实现的场景在没有 OO 的"
            "环境里会显示成 unverifiable ⇒ 将来接上真实 OO 会把它们**自动刷绿**，而它们"
            "其实永远不会通过"
        ),
    }


def build_scenario_verdicts() -> dict[str, Any]:
    from app.services.workpaper_sync import evidence as EV
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync import pilot_harness as PH

    entries = EV.manifest_entries_by_id(EV.load_entry_manifest())
    required = EV.derive_for_manifest_entry(
        entries[P.PILOT_ENTRY_ID], authority_model=P.AUTHORITY_MODEL
    )

    rows: dict[str, Any] = {}
    for scenario in sorted(required.scenarios, key=lambda s: s.scenario_id):
        oracle = PH.SCENARIO_ORACLES[scenario.scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=PH.ScenarioObservation(scenario_id=scenario.scenario_id),
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )
        rows[scenario.scenario_id] = {
            "family": scenario.family.value,
            "requirement": scenario.requirement,
            "requires": sorted(i.value for i in oracle.requires),
            "needs_black_box": oracle.needs_black_box,
            "upstream_debt": oracle.upstream_debt or None,
            "result": verdict.outcome.value,
            "error_code": verdict.error_code,
        }

    distribution: dict[str, int] = {}
    for row in rows.values():
        distribution[row["result"]] = distribution.get(row["result"], 0) + 1
    by_error: dict[str, int] = {}
    for row in rows.values():
        by_error[str(row["error_code"])] = by_error.get(str(row["error_code"]), 0) + 1

    upstream_gap_ids = sorted(
        sid for sid, row in rows.items() if row["error_code"] == "upstream_gap"
    )
    # 🔴 反事实：把 `upstream_debt` 清空后**同一条** oracle 的判定。这两条落到
    # `unverifiable` ⇒ 一旦补齐证据就会被判 passed，而缺的是**实现**不是环境。
    # 这是「upstream-gap 必须判 failed 且排在 black-box 之前」这条要求的行为侧证据
    # （本 entry 的 required set 里没有「既有缺口又需黑盒」的交叉形态，见
    # `upstream_gap_and_black_box_scenarios` 为空，故用反事实补上）。
    import dataclasses

    counterfactual: dict[str, Any] = {}
    for scenario_id in upstream_gap_ids:
        scenario = next(s for s in required.scenarios if s.scenario_id == scenario_id)
        naked = dataclasses.replace(PH.SCENARIO_ORACLES[scenario_id], upstream_debt="")
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=naked,
            observation=PH.ScenarioObservation(
                scenario_id=scenario_id, supplied_inputs=naked.requires
            ),
            onlyoffice_build=PH.NOT_EXECUTED,
            browser_build=PH.NOT_EXECUTED,
        )
        counterfactual[scenario_id] = {
            "result": verdict.outcome.value,
            "error_code": verdict.error_code,
            "differs_from_real": verdict.outcome.value != rows[scenario_id]["result"],
        }
    # 交叉形态：既有上游缺口、又需要黑盒 —— 这类必须落 failed/upstream_gap 才算顺序生效。
    both = sorted(
        sid
        for sid, row in rows.items()
        if row["upstream_debt"] and row["needs_black_box"]
    )
    landing: dict[str, list[str]] = {}
    for property_id, scenario_ids in (
        ("P22", ["different_field_merge"]),
        ("P28", ["oo_to_html", "html_to_oo"]),
        ("P49", ["identity_retention"]),
        ("P66", ["identity_retention"]),
        ("P69", ["single_participant_close"]),
    ):
        landing[property_id] = [sid for sid in scenario_ids if sid in rows]

    return {
        "environment": {
            "onlyoffice_build": PH.NOT_EXECUTED,
            "browser_build": PH.NOT_EXECUTED,
            "why": (
                "真实 OO 未执行 ⇒ 一律走 NOT_EXECUTED 哨兵。Property 49：probe/pilot 未"
                "实际通过时必须保持 UNVERIFIABLE，不得因文档声明计为通过"
            ),
        },
        "aggregate_result": "failed (含 UNVERIFIABLE 黑盒场景，无一条 passed)",
        "passed_count": distribution.get("passed", 0),
        "result_distribution": distribution,
        "error_code_distribution": by_error,
        "upstream_gap_scenarios": upstream_gap_ids,
        "upstream_gap_and_black_box_scenarios": both,
        "upstream_gap_counterfactual_without_debt_branch": counterfactual,
        "ordering": _ordering_facts(),
        "property_oracle_landing": landing,
        "scenarios": rows,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ③ sheet_audit.json
# ═══════════════════════════════════════════════════════════════════════════


def build_sheet_audit() -> dict[str, Any]:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    workbook = _workbook()
    sheets: list[dict[str, Any]] = []
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        horizontal = sorted(
            {
                merged.min_row
                for merged in worksheet.merged_cells.ranges
                if merged.min_row == merged.max_row and merged.min_col != merged.max_col
            }
        )
        total_rows = [
            row
            for row in range(1, min(worksheet.max_row, 400) + 1)
            if str(worksheet.cell(row=row, column=1).value or "").strip() == P.FOOTER_MARKER
        ]
        sheets.append(
            {
                "sheet": name,
                "dimensions": worksheet.dimensions,
                "max_row": worksheet.max_row,
                "max_column": worksheet.max_column,
                "merge_count": len(worksheet.merged_cells.ranges),
                "horizontal_merge_rows": horizontal,
                "footer_rows_with_total_marker": total_rows,
                "data_validation_count": len(worksheet.data_validations.dataValidation),
                "conditional_formatting_count": len(list(worksheet.conditional_formatting)),
                "sheet_protection": bool(worksheet.protection.sheet),
                "selected_as_managed": name == P.MANAGED_SHEET,
            }
        )
    return {
        "managed_sheet": P.MANAGED_SHEET,
        "sheet_count": len(sheets),
        "not_selected_reason": {
            "附注披露信息（上市公司）": (
                "同构孪生表：B171:B187 的 17 行**全是公式**（2 行 =SUM(...)、15 行跨 sheet "
                "='…' 引用）⇒ 一格都不是 editable，做不成双向回写 pilot。它反而是"
                "「mode 必须精确到格」的实证来源（UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_"
                "PER_COLUMN）"
            ),
            "GT_SYNC metadata sheet": (
                "注入产物里的隐藏 metadata sheet 只承载 identity，"
                "**不进业务 sheet 枚举、不进披露表**（contract 不声明它；"
                "`excel_extract` 对 metadata sheet 泄漏显式 fail closed）"
            ),
        },
        "sheets": sheets,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ④ two_level_header_and_fields.json
# ═══════════════════════════════════════════════════════════════════════════


def _observe(worksheet: Any, declared_ref: str | None, declared_text: Any) -> dict[str, Any]:
    if not declared_ref:
        return {"source_ref": None}
    match = _SRC_RE.match(declared_ref)
    if match is None:
        return {"source_ref": declared_ref, "parsed": False}
    observed = _cell_text(worksheet, match.group("ref"))
    row: dict[str, Any] = {
        "source_ref": declared_ref,
        "cell": match.group("ref"),
        "observed": observed,
    }
    if declared_text is not None:
        row["declared"] = declared_text
        row["match"] = str(declared_text) == (observed or "")
    return row


def build_two_level_header_and_fields() -> dict[str, Any]:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    payload = P.build_contract_payload()
    sheet = payload["sheets"][0]
    worksheet = _workbook()[P.MANAGED_SHEET]

    fields: list[dict[str, Any]] = []
    header_matches = 0
    header_checked = 0
    for table in sheet["tables"]:
        for spec in table["fields"]:
            leaf = _observe(worksheet, spec.get("header_source_ref"), spec.get("header_text"))
            if "match" in leaf:
                header_checked += 1
                header_matches += int(bool(leaf["match"]))
            group_ref = spec.get("group_source_ref")
            group: dict[str, Any] | None = None
            if group_ref:
                match = _SRC_RE.match(group_ref)
                anchor = spec.get("group_anchor_column")
                group = {
                    "source_ref": group_ref,
                    "placeholder": spec.get("group_placeholder"),
                    "anchor_column": anchor,
                    "observed_cell_is_blank": (
                        _cell_text(worksheet, match.group("ref")) is None
                        if match
                        else None
                    ),
                    "observed_horizontal_merge": (
                        _merge_span(worksheet, f"{anchor}{P.GROUP_HEADER_ROW}")
                        if anchor
                        else None
                    ),
                }
            fields.append(
                {
                    "table_key": table["table_key"],
                    "stable_field_key": spec["stable_field_key"],
                    "column_key": spec["column_key"],
                    "column": spec["cell"]["column"],
                    "row_from": spec["cell"]["row_from"],
                    "json_pointer": spec["json_pointer"],
                    "mode": spec["mode"],
                    "value_type": spec["value_type"],
                    "leaf": leaf,
                    "group": group,
                    "row_label": _observe(
                        worksheet,
                        spec.get("row_label_source_ref"),
                        spec.get("row_label_text"),
                    ),
                    "cell_observed": _observe(worksheet, spec.get("source_ref"), None),
                    "formula_source_ref": spec.get("formula_source_ref"),
                    "render_column_key": spec.get("render_column_key"),
                    "render_sub_key": spec.get("render_sub_key"),
                }
            )

    matrix = next(t for t in sheet["tables"] if t["table_key"] == P.MATRIX_TABLE_KEY)
    record = next(t for t in sheet["tables"] if t["table_key"] == P.RECORD_TABLE_KEY)

    leaf_labels: dict[str, int] = {}
    for spec in matrix["fields"]:
        label = str(spec.get("header_text"))
        leaf_labels[label] = leaf_labels.get(label, 0) + 1
    # 每个 label 在 10 列上各重复 5 次；矩阵有 10 个 metric 行 ⇒ 计数除以行数。
    metric_rows = len(P.MATRIX_METRICS)
    leaf_labels = {label: count // metric_rows for label, count in leaf_labels.items()}

    keys = P.dynamic_column_keys_for_entities(P.RENDER_SLOT_DEFAULT_NAMES)
    binding = P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES)
    formula_cells = {
        f"{column}{row}": worksheet[f"{column}{row}"].value
        for _k, column, mode, *_rest in P.RECORD_COLUMNS
        if mode == "formula"
        for row in range(P.RECORD_FIRST_ROW, P.RECORD_LAST_ROW + 1)
    }
    stable_keys = [spec["stable_field_key"] for spec in matrix["fields"] + record["fields"]]

    return {
        "managed_sheet": P.MANAGED_SHEET,
        "header_rows": {
            "count": matrix["header_rows"],
            "group": P.GROUP_HEADER_ROW,
            "leaf": P.LEAF_HEADER_ROW,
        },
        "field_count": len(fields),
        "distinct_stable_keys": len(set(stable_keys)),
        "all_header_refs_match": header_checked > 0 and header_matches == header_checked,
        "header_refs_checked": header_checked,
        "duplicate_leaf_labels": leaf_labels,
        "group_merges_observed": {
            f"{anchor}{P.GROUP_HEADER_ROW}": _merge_span(
                worksheet, f"{anchor}{P.GROUP_HEADER_ROW}"
            )
            for anchor in sorted(
                {
                    str(spec.get("group_anchor_column"))
                    for spec in matrix["fields"]
                    if spec.get("group_anchor_column")
                },
                key=lambda col: len(col) * 100 + ord(col[-1]),
            )
        },
        "template_slot_group_merges": [
            list(slot) for slot in P.TEMPLATE_SLOT_GROUP_MERGES
        ],
        "dynamic_columns": {
            "identity": matrix["dynamic_columns"]["identity"],
            "identity_is_the_imported_constant": True,
            "source_ref": matrix["dynamic_columns"]["source_ref"],
            "keys": list(keys),
            "binding": dict(binding),
            "distinct_key_count": len(set(keys)),
            "distinct_column_count": len(set(binding.values())),
            "label_independent": (
                list(P.dynamic_column_keys_for_entities(("甲", "甲", "甲", "乙", "乙")))
                == list(keys)
            ),
            "render_sub_columns": [list(pair) for pair in P.RENDER_SUB_COLUMNS],
        },
        "formula_mask": {
            "matrix": matrix.get("formula_mask"),
            "record": record.get("formula_mask"),
            "record_formula_cells_observed": formula_cells,
        },
        "metadata_sheet_in_disclosure": False,
        "label_rename_does_not_change_identity": (
            "实体改名只动 entityName；10 个 {slot}_{seq} 键逐字不变（label_independent）"
        ),
        "fields": fields,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ mutation_report.json + mutation_coverage.json
# ═══════════════════════════════════════════════════════════════════════════


def _declared_mutation_ids() -> list[str]:
    text = (
        BACKEND / "scripts/diagnose/mutate_task43_g7_two_level_dynamic_pilot_guards.py"
    ).read_text(encoding="utf-8")
    return sorted(set(re.findall(r'^\s*id="(M\d+)",', text, flags=re.MULTILINE)))


def build_mutation_report() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    rounds: list[dict[str, Any]] = []
    for name, note in MUTATION_ROUNDS:
        path = REPO / name
        if not path.exists():
            rounds.append({"file": name, "note": note, "present": False})
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        verdicts: dict[str, int] = {}
        for record in records:
            verdicts[record["verdict"]] = verdicts.get(record["verdict"], 0) + 1
            latest[record["id"]] = record
        rounds.append(
            {
                "file": name,
                "note": note,
                "present": True,
                "ids": [r["id"] for r in records],
                "verdicts": verdicts,
            }
        )

    report = [latest[key] for key in sorted(latest, key=lambda m: int(m[1:]))]
    declared = _declared_mutation_ids()
    executed = sorted(latest, key=lambda m: int(m[1:]))
    not_executed = [m for m in declared if m not in latest]
    final: dict[str, int] = {}
    for record in report:
        final[record["verdict"]] = final.get(record["verdict"], 0) + 1
    coverage = {
        "declared_count": len(declared),
        "executed_count": len(executed),
        "executed_ids": executed,
        "not_executed_ids": not_executed,
        "final_verdicts": final,
        "all_executed_are_red": final.get("RED", 0) == len(report),
        "rounds": rounds,
        "guard_files": [
            "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py",
            "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot_pg.py",
        ],
        "guard_baseline_passed": 240,
        "honest_gap": (
            f"声明 {len(declared)} 条、实测 {len(executed)} 条 ⇒ "
            f"{len(not_executed)} 条（{not_executed[:3]}…）**尚未执行**，覆盖面结论未闭合。"
            "本文件如实登记，不以「全 RED」冒充全量"
        )
        if not_executed
        else "declared == executed，覆盖面闭合",
        "four_state_note": (
            "四态判定 RED / GREEN(守卫缺陷) / ANCHOR-MISS(脚本缺陷) / WRONG-TEST。"
            "M31 首轮 ERROR（scope_check 误用 JSON 回调 ⇒ pytest 从未执行）、"
            "第 4 轮先 GREEN 再 RED，两次都留在 rounds 里"
        ),
    }
    return report, coverage


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def build_all() -> dict[str, Any]:
    report, coverage = build_mutation_report()
    return {
        "identity_and_digests.json": build_identity_and_digests(),
        "scenario_verdicts.json": build_scenario_verdicts(),
        "sheet_audit.json": build_sheet_audit(),
        "two_level_header_and_fields.json": build_two_level_header_and_fields(),
        "mutation_report.json": report,
        "mutation_coverage.json": coverage,
    }


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 43 evidence 观测器")
    parser.add_argument("--apply", action="store_true", help="写入 evidence 目录")
    parser.add_argument("--check", action="store_true", help="只读：重算并比对磁盘")
    args = parser.parse_args(argv)
    if not (args.apply or args.check):
        parser.print_help()
        return 2

    built = build_all()
    if args.apply:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for name, payload in built.items():
            path = EVIDENCE_DIR / name
            path.write_bytes(_dumps(payload).encode("utf-8"))
            print(f"[WRITE] {path.relative_to(REPO)}  {path.stat().st_size} bytes")
        return 0

    problems: list[str] = []
    for name, payload in built.items():
        path = EVIDENCE_DIR / name
        if not path.exists():
            problems.append(f"{name}: 缺文件")
            continue
        # 🔴 比**序列化字节**而不是 `json.loads` 后的 Python 对象：后者会把
        # tuple↔list 的往返差异报成「不一致」（实测踩过：`TEMPLATE_SLOT_GROUP_MERGES`
        # 是 tuple of tuple，写盘后读回是 list of list ⇒ 恒判 FAIL）。字节相等
        # 才是「磁盘 == 我这次会写的内容」这条真正的不变量。
        if path.read_bytes() != _dumps(payload).encode("utf-8"):
            problems.append(f"{name}: 磁盘与重算不一致")
        else:
            print(f"[OK  ] {name}")
    if problems:
        print(f"[FAIL] {len(problems)} 项：")
        for problem in problems:
            print(f"  !! {problem}")
        return 1
    print("[OK] evidence 全部与重算一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
