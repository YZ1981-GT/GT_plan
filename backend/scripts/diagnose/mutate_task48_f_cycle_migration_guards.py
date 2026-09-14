# -*- coding: utf-8 -*-
"""Task 48 守卫变异检验 —— F 循环 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 48

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本
强制采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填）。

═══ 本脚本的两条硬约束 ═══

1. **数据文件变异一律带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出
   「锚点落在被测判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是
   脚本缺陷。回调解析 JSON 后断言目标字段真的变成了期望值。
2. **重复形态字段用 `scope` + `offset` 相对定位，不用绝对行号**。slice 里
   `"capability": null,` 出现 8 次、`"html_counterpart_verdict": "exists",` 出现 8 次；
   而绝对行号一改文件就失效（Task 47 的 M12 就是写死 `line=155` 而那行早已是别的内容）。
   `scope` 取该 entry 唯一的 `entry_id` 行，`offset` 由
   `tmp_t48_anchors.py`（一次性诊断，已清理）实算得出。

用法（仓库根；本仓库 PATH 上的 `python` 指向坏掉的 venv，必须用 `.\\.venv\\Scripts\\python.exe`）::

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task48_f_cycle_migration_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task48_f_cycle_migration_guards.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task48_f_cycle_migration_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task48-f-cycle-migration/mutation_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_f_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_f_cycle_deletion_plan.json"
PLAN_SYNC = "backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py"
NOTICE_TS = "audit-platform/frontend/src/components/workpaper/sync/workpaperEntrySyncNotice.ts"
NOTICE_VUE = "audit-platform/frontend/src/components/workpaper/sync/GtEntrySyncCapabilityNotice.vue"
HOST_F1 = "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue"
HOST_F2M = "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue"
HOST_F2S = "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue"
HOST_F3 = "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue"
HOST_F5 = "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue"

T48 = "test_task48_f_cycle_migration.py"
FE_SPEC = "workpaperEntrySyncNotice.spec.ts"

_SELF = f"{T48}::TestGuardSelfChecks"
_ADJ = f"{T48}::TestAdjudicationLegality"
_HTML = f"{T48}::TestHtmlCounterpartIsSourceBacked"
_P21 = f"{T48}::TestProperty21ContractFieldsNotClaimedPassingForFCycle"
_P28 = f"{T48}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T48}::TestProperty69EvidenceAndCounters"
_P70 = f"{T48}::TestProperty70NoCrossEntryReuse"
_AC14 = f"{T48}::TestAc14HonestModeVisibility"
_WORD = f"{T48}::TestWordLaneBoundaryAndUnifiedCommit"
_PARA = f"{T48}::TestParadigmCompliance"
_SRC = f"{T48}::TestSourceCodeStructure"

# ── 相对定位用的唯一 scope 锚（每个 entry 的 entry_id 行）───────────────────
S_F1 = '      "entry_id": "xlsx/gt-f1-prepayment",'
S_F2M = '      "entry_id": "xlsx/gt-f2-inventory-main",'
S_F2SPE = '      "entry_id": "xlsx/gt-f2-inventory-special",'
S_F2VAL = '      "entry_id": "xlsx/gt-f2-inventory-valuation",'
S_F2ST = '      "entry_id": "xlsx/gt-f2-stocktake-bundle",'
S_F3 = '      "entry_id": "xlsx/gt-f3-notes-payable",'
S_F4 = '      "entry_id": "xlsx/gt-f4-accounts-payable",'
S_F5 = '      "entry_id": "xlsx/gt-f5-cost-of-sales",'
# deletion plan 内同形态（另一份文件，offset 不同）
P_F1 = '      "entry_id": "xlsx/gt-f1-prepayment",'
P_F3 = '      "entry_id": "xlsx/gt-f3-notes-payable",'


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════
def _entry_field(entry_id: str, *path):
    """slice/plan 里某 entry 的嵌套字段必须**恰好**等于期望值（path 末位是期望值）。"""
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("independent_entries") or payload.get("entries") or []
        for entry in rows:
            if entry.get("entry_id") != entry_id:
                continue
            node = entry
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return False
                node = node[key]
            return node == expected
        return False

    return check


def _has_entry_id(entry_id: str):
    """entry 集合里必须出现该 id（用于「entry_id 被改名」这类变异）。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("independent_entries") or payload.get("entries") or []
        return entry_id in {e.get("entry_id") for e in rows}

    return check


def _top_path_is(expected, *keys: str):
    def check(data: bytes) -> bool:
        node = json.loads(data.decode("utf-8"))
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected

    return check


def _template_field(name: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _template_key_absent(name: str, key: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return key not in record
        return False

    return check


def _bp_field(bp_id: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for bp in payload["blocking_preconditions"]:
            if bp.get("id") == bp_id:
                return bp.get(key) == expected
        return False

    return check


def _mechanism_field(mech_id: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for mech in payload["composite_transport_keys"]["mechanisms"]:
            if mech.get("id") == mech_id:
                return mech.get(key) == expected
        return False

    return check


def _dynamic_row_kind_is(table_key: str, expected: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for table in payload["dynamic_row_identity"]["tables"]:
            if table.get("table_key") == table_key:
                return table["row_identity"].get("kind") == expected
        return False

    return check


def _plan_composable_field(path_suffix: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["entries"]:
            for comp in entry.get("legacy_composables_to_delete", []):
                if comp["file"].endswith(path_suffix):
                    return comp.get(key) == expected
        return False

    return check


def _word_lane_writer_field(sheet_code: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["independent_entries"]:
            lane = entry.get("partially_wired_word_lane")
            if not lane:
                continue
            for writer in lane["wired_writers"]:
                if writer.get("sheet_code") == sheet_code:
                    return writer.get(key) == expected
        return False

    return check


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① AC 12.8 / 12.1 / 1.3 裁决合法性
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=S_F1, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "bidirectional",',
        want=f"{_ADJ}::test_bidirectional_requires_all_five_identity_fields",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_ADJ}::test_single_or_pending_entries_carry_no_identity",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="把终态未定改成 bidirectional 而五个身份字段仍为 null 仍绿 ⇒ AC 12.1 的"
            "「缺 approved contract/bundle 不得进入 bidirectional 验收」整条失守",
        scope_check=_entry_field("xlsx/gt-f1-prepayment", "capability", "bidirectional"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=S_F2M, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="有 HTML 对端（verdict=exists）却裁 single_onlyoffice 仍绿 ⇒ AC 12.8 的唯一合法"
            "判据失守，这正是 Task 46 首轮把 7 条 D entry 全裁错的形态",
        scope_check=_entry_field(
            "xlsx/gt-f2-inventory-main", "capability", "single_onlyoffice"
        ),
        tags=("adjudication", "data", "regression"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=S_F3, offset=27,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="AP-3：把「还没查」写成 unresolved 仍绿 ⇒ step 3 的二值结论可以被含糊值顶替，"
            "而据此裁 single 就又回到循环论证",
        scope_check=_entry_field(
            "xlsx/gt-f3-notes-payable", "html_counterpart_verdict", "unresolved"
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=S_F2VAL, offset=113,
        anchor='        "criterion_source": "backend/data/workpaper_sync_migration_paradigm.json#adjudication_criteria.verdicts"',
        new='        "not_bidirectional_because": "无 bidirectional adapter，无 per-entry contract"',
        want=f"{_ADJ}::test_adjudication_reason_is_not_circular",
        why="用重复键把裁决理由替换成循环论证原文（JSON 后键覆盖前键）仍绿 ⇒ AP-1 检测器"
            "只扫 reason 不扫另两个理由字段，换个字段写循环论证照样通过",
        scope_check=_entry_field(
            "xlsx/gt-f2-inventory-valuation",
            "adjudication",
            "not_bidirectional_because",
            "无 bidirectional adapter，无 per-entry contract",
        ),
        tags=("adjudication", "data", "ap1"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        anchor='        "BP-9"',
        new='        "BP-99"',
        want=f"{_ADJ}::test_capability_blockers_reference_real_preconditions",
        why="entry 引用不存在的阻断项仍绿 ⇒ capability_target_blocked_by 可以指向任何编号，"
            "「缺什么已逐条登记」这句话失去约束",
        scope_check=lambda data: "BP-99"
        in json.loads(data.decode("utf-8"))["independent_entries"][4][
            "capability_target_blocked_by"
        ],
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=S_F4, offset=111,
        anchor='      "ui_toolbar_gate": "v-if=\\"showHtmlToolbar\\"",',
        new='      "ui_toolbar_gate": "class=\\"f4-nonexistent-toolbar\\"",',
        want=f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",
        why="工具栏门控锚点被改成宿主里不存在的类名仍绿 ⇒ 区块判据没有真去定位区块，"
            "「通知挂在模式工具栏内」这条退化成恒真",
        scope_check=_entry_field(
            "xlsx/gt-f4-accounts-payable",
            "ui_toolbar_gate",
            'class="f4-nonexistent-toolbar"',
        ),
        tags=("ac14", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ② Property 28：模板 digest / structure hash / sheet!cell / 索引可达性
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        anchor='      "template_ref": "F/F1 预付账款.xlsx",',
        new='      "template_ref": "F/F1 预付账款-不存在.xlsx",',
        want=f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="template_ref 指向不存在的文件仍绿 ⇒ 「权威模板只认 backend/wp_templates 且必须"
            "在 _index.json 里」这条无人把守，后面每个 digest 都会对着一份不存在的模板算",
        scope_check=_entry_field(
            "xlsx/gt-f1-prepayment", "template_ref", "F/F1 预付账款-不存在.xlsx"
        ),
        tags=("template", "data"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        anchor='      "template_ref": "F/F4 应付账款.xlsx",',
        new='      "template_ref": null,',
        want=f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",
        wants=(f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",),
        why="🔴 Task 46 首轮实测过的 fail-open 形态：判据写成 `if tref:` 时 template_ref 为"
            "null 会整条跳过（置 null 后 36 例全绿）。本文件写的是「必须非空」，必须 RED",
        scope_check=_entry_field("xlsx/gt-f4-accounts-payable", "template_ref", None),
        tags=("template", "data", "failopen"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "f30055cbebc7daedec6d073e983e7ada5375c3edf50b49880c7aa571846510dd",',
        new='        "sha256": "f30055cbebc7daedec6d073e983e7ada5375c3edf50b49880c7aa571846510de",',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="模板 sha256 改一位仍绿 ⇒ Requirement 6.10 的 definition 漂移 fail closed 失守，"
            "「digest 现算复核」退化成读一遍自己写的值",
        scope_check=_template_field(
            "F1 预付账款.xlsx",
            "sha256",
            "f30055cbebc7daedec6d073e983e7ada5375c3edf50b49880c7aa571846510de",
        ),
        tags=("template", "data", "digest"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='        "size": 261608,',
        new='        "size": 261609,',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="size 改一字节仍绿 ⇒ 字节级冻结只冻了 sha256 而没冻 size，"
            "两者任一漂移都应 fail closed",
        scope_check=_template_field("F1 预付账款.xlsx", "size", 261609),
        tags=("template", "data", "digest"),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='        "normalized_structure_hash": "f1457eb9334a3b97229643079b9c1fe0d1c277622d872d8f9f5afa8342ffc0a1",',
        new='        "normalized_structure_hash": "0000000000000000000000000000000000000000000000000000000000000000",',
        want=f"{_P28}::test_normalized_structure_hash_recomputes",
        wants=(f"{_P28}::test_digests_are_real_digests",),
        why="把结构 hash 换成全零仍绿 ⇒ 结构漂移判据没有真调用生产实现现算，"
            "且 Requirement 2.3 的「全零 hash 不得代替真 digest」也没人管",
        scope_check=_template_field(
            "F1 预付账款.xlsx", "normalized_structure_hash", "0" * 64
        ),
        tags=("template", "data", "digest"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='        "belongs_to_entry": "xlsx/gt-f1-prepayment"',
        new='        "belongs_to_entry": "xlsx/gt-f1-prepayment-x"',
        want=f"{_P28}::test_template_owner_mapping_is_consistent",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="模板归属到不存在的 entry 仍绿 ⇒ SR-8 失守，可以悄悄夹带跨循环模板"
            "或把模板挂到已删除的 entry 上",
        scope_check=_template_field(
            "F1 预付账款.xlsx", "belongs_to_entry", "xlsx/gt-f1-prepayment-x"
        ),
        tags=("template", "data"),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope='        "name": "F2存货.xlsx",',
        offset=3,
        anchor='        "in_runtime_index": false,',
        new='        "in_runtime_index": true,',
        want=f"{_P28}::test_in_runtime_index_flag_recomputes",
        why="把不可达合册的 in_runtime_index 手填成 true 仍绿 ⇒ 该标记没有从 _index.json 现算，"
            "BP-8 描述的「运行时不可达」可以被一行谎话抹掉",
        scope_check=_template_field("F2存货.xlsx", "in_runtime_index", True),
        tags=("template", "data", "bp8"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "afc762843ffee1c32087848d6401500b53d5f3fb59d32c1098acfff6f1b2ef0d",',
        new='        "sha256": "afc762843ffee1c32087848d6401500b53d5f3fb59d32c1098acfff6f1b2ef0e",',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        why="不可达合册 F2存货.xlsx 的 digest 改一位仍绿 ⇒ 「登记集合 == 磁盘实况」只比了"
            "文件名而没比内容，BP-8 登记的那份冗余模板可以被人悄悄换掉",
        scope_check=_template_field(
            "F2存货.xlsx",
            "sha256",
            "afc762843ffee1c32087848d6401500b53d5f3fb59d32c1098acfff6f1b2ef0e",
        ),
        tags=("template", "data", "bp8"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='          "identity_text": "项目 月份"',
        new='          "identity_text": "项目月份"',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="身份列表头少一个空格仍绿 ⇒ 第三边（权威 xlsx 真读）退化成模糊比对，"
            "而 F5-2 的表头恰恰是「项目 月份」（中间有空格）",
        scope_check=_entry_field(
            "xlsx/gt-f5-cost-of-sales",
            "html_counterpart",
            "primary_table",
            "identity_text",
            "项目月份",
        ),
        tags=("template", "data", "threeway"),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='          "identity_cell": "A6",',
        new='          "identity_cell": "A7",',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="身份单元格坐标改一行仍绿 ⇒ sheet!cell 没被真读（F2-3 的 A7 是「数量」不是「存货编码」）",
        scope_check=_entry_field(
            "xlsx/gt-f2-inventory-main",
            "html_counterpart",
            "primary_table",
            "identity_cell",
            "A7",
        ),
        tags=("template", "data", "threeway"),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='          "template_sheet": "明细表F3-2",',
        new='          "template_sheet": "审定表F3-1",',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="把 sheet 换成同册的另一张表仍绿 ⇒ 三边锁的第三边可以指向任意 sheet，"
            "契约会按错表的列结构生成",
        scope_check=_entry_field(
            "xlsx/gt-f3-notes-payable",
            "html_counterpart",
            "primary_table",
            "template_sheet",
            "审定表F3-1",
        ),
        tags=("template", "data", "threeway"),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        anchor='      "status": "REGISTERED_NOT_FIXED",',
        scope='      "id": "BP-5",',
        offset=9,
        new='      "status": "FIXED",',
        want=f"{_P28}::test_bp5_wrong_workbook_fallback_is_reproducible",
        why="BP-5 的 status 被改成 FIXED 而解析器没动仍绿 ⇒ 阻断项状态可以自说自话，"
            "「登记了」与「解决了」在报告里长得一样",
        scope_check=_bp_field("BP-5", "status", "FIXED"),
        tags=("bp", "data"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='        "backend/wp_templates/F/F2存货.xlsx",',
        new='        "backend/wp_templates/F/F2存货-不存在.xlsx",',
        want=f"{_P69}::test_blocking_preconditions_are_complete",
        why="阻断项的 source_ref 指向不存在的路径仍绿 ⇒ 无据可查的阻断项等于自由文本豁免",
        scope_check=lambda data: "backend/wp_templates/F/F2存货-不存在.xlsx"
        in [
            r
            for bp in json.loads(data.decode("utf-8"))["blocking_preconditions"]
            for r in bp["source_refs"]
        ],
        tags=("bp", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ③ HTML 对端三边锁与复合传输键
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=S_F3, offset=56,
        anchor='          "owner_constant": "STORAGE_KEY",',
        new='          "owner_constant": "ITEM_ID_ROWS",',
        want=f"{_HTML}::test_primary_table_is_declared_by_its_owner_module",
        why="owner_constant 写错常量名仍绿 ⇒ 第二边只查了「字面量出现过」，"
            "而没有校验它到底挂在哪个常量上（改名后契约的 json_pointer 会失配）",
        scope_check=_entry_field(
            "xlsx/gt-f3-notes-payable",
            "html_counterpart",
            "primary_table",
            "owner_constant",
            "ITEM_ID_ROWS",
        ),
        tags=("html", "data", "threeway"),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        anchor='          "owner_declaration_kind": "composed_from_sheet_code",',
        new='          "owner_declaration_kind": "module_constant",',
        want=f"{_HTML}::test_primary_table_is_declared_by_its_owner_module",
        wants=(f"{_HTML}::test_transport_key_kind_is_declared_and_matches_the_source",),
        why="把「由 sheetCode 拼出」误报成「模块常量」仍绿 ⇒ 三态判据互相顶替，"
            "契约会按单键而不是 (sheet_code, table_role) 两维生成，漏掉 10 张分类表",
        scope_check=_entry_field(
            "xlsx/gt-f2-inventory-main",
            "html_counterpart",
            "primary_table",
            "owner_declaration_kind",
            "module_constant",
        ),
        tags=("html", "data", "composite"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='        "transport_key_kind": "per_sheet_literal_injected_into_generic_composable",',
        new='        "transport_key_kind": "composite_sheet_code_plus_table_role",',
        want=f"{_HTML}::test_transport_key_kind_is_declared_and_matches_the_source",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="🔴 这正是本任务首轮踩的形态错：把监盘的「注入式」当成「拼接式」。改回去必须 RED —— "
            "否则 slice 可以声称一种源码里不存在的机制（拼接式判据要求 sheet_codes_in_family "
            "与 transport_key_composition_source，注入式给不出）",
        scope_check=_entry_field(
            "xlsx/gt-f2-stocktake-bundle",
            "html_counterpart",
            "transport_key_kind",
            "composite_sheet_code_plus_table_role",
        ),
        tags=("html", "data", "composite", "regression"),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        scope=S_F2M, offset=55,
        anchor='        "row_identity_key": "id",',
        new='        "row_identity_key": "rowId",',
        want=f"{_HTML}::test_row_identity_key_and_generator_are_source_backed",
        why="行身份键从 id 改成 rowId 仍绿 ⇒ 判据没回源码核对，"
            "照抄 D 循环「全 rowId」的结论会让 F2 的契约按不存在的字段取行身份",
        scope_check=_entry_field(
            "xlsx/gt-f2-inventory-main", "html_counterpart", "row_identity_key", "rowId"
        ),
        tags=("html", "data", "rowidentity"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        scope=S_F5, offset=45,
        anchor='        "row_identity_is_positional": true,',
        new='        "row_identity_is_positional": false,',
        want=f"{_HTML}::test_positional_row_identity_defects_are_real_and_exhaustive",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="把真实存在的位置化缺陷（F5 载入路径用数组下标 i 拼 id）改报成 false 仍绿 ⇒ "
            "漏报侧无人把守，BP-7 可以被悄悄抹掉",
        scope_check=_entry_field(
            "xlsx/gt-f5-cost-of-sales",
            "html_counterpart",
            "row_identity_is_positional",
            False,
        ),
        tags=("html", "data", "rowidentity"),
    ),
    Mutation(
        id="M25", side="be", path=SLICE, kind="replace",
        scope=S_F1, offset=42,
        anchor='        "row_identity_is_positional": false,',
        new='        "row_identity_is_positional": true,',
        want=f"{_HTML}::test_positional_row_identity_defects_are_real_and_exhaustive",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="把不存在的位置化缺陷虚报成 true 仍绿 ⇒ 虚报侧无人把守，"
            "可以拿一个不存在的缺陷去凑 BP 数量",
        scope_check=_entry_field(
            "xlsx/gt-f1-prepayment", "html_counterpart", "row_identity_is_positional", True
        ),
        tags=("html", "data", "rowidentity"),
    ),
    Mutation(
        id="M26", side="be", path=SLICE, kind="replace",
        anchor='        "html_persistence_composable": "audit-platform/frontend/src/components/workpaper/composables/useF1FormData.ts#L52(GET)/#L113(PUT)"',
        new='        "html_persistence_composable": "audit-platform/frontend/src/components/workpaper/composables/useF1Detail.ts"',
        want=f"{_HTML}::test_persistence_composable_really_calls_both_endpoints",
        why="把持久化 composable 换成一个不发 checklist-responses 请求的模块仍绿 ⇒ "
            "「业务内容落在 HTML 侧」这个结论退化成路径存在性判据",
        scope_check=_entry_field(
            "xlsx/gt-f1-prepayment",
            "html_counterpart",
            "html_persistence_composable",
            "audit-platform/frontend/src/components/workpaper/composables/useF1Detail.ts",
        ),
        tags=("html", "data"),
    ),
    Mutation(
        id="M27", side="be", path=SLICE, kind="replace",
        anchor='        "name": "template_literal_composed_from_sheet_code",',
        new='        "name": "template_literal_composed_from_wp_code",',
        want=f"{_HTML}::test_composite_transport_key_mechanisms_are_source_backed",
        why="机制名被改成没有对应源码探针的名字仍绿 ⇒ composite_transport_keys 变成"
            "「登记了但没人验」的死数据（G7 两级表头 0/38 的同型）",
        scope_check=_mechanism_field("CK-1", "name", "template_literal_composed_from_wp_code"),
        tags=("html", "data", "composite"),
    ),
    Mutation(
        id="M28", side="be", path=SLICE, kind="replace",
        anchor='          "audit-platform/frontend/src/components/workpaper/composables/useF2DetailSheet.ts",',
        new='          "audit-platform/frontend/src/components/workpaper/composables/useF1Detail.ts",',
        want=f"{_HTML}::test_composite_transport_key_mechanisms_are_source_backed",
        why="🔴 首轮此条判 GREEN，暴露的是守卫缺陷：判据原本写「sources 里至少一个通过探针」，"
            "于是把 CK-1 的一个 source 换成不含 `${sheetCode}-` 的 useF1Detail.ts 后，"
            "其余 4 个仍命中 ⇒ 登记表可以混进不体现该机制的模块。改成「每个 source 都必须"
            "通过探针」后必须 RED",
        scope_check=lambda data: "audit-platform/frontend/src/components/workpaper/composables/useF2DetailSheet.ts"
        not in json.loads(data.decode("utf-8"))["composite_transport_keys"]["mechanisms"][0][
            "sources"
        ],
        tags=("html", "data", "composite"),
    ),
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        anchor='          "kind": "generated_opaque_string_with_array_index_fallback",',
        new='          "kind": "array_index",',
        want=f"{_PARA}::test_dynamic_row_identity_section_satisfies_the_conditional_schema",
        why="dynamic_row_identity 的 kind 落进 forbidden_identity_kinds 仍绿 ⇒ "
            "范式 conditional_sections 的禁列判据没生效",
        scope_check=_dynamic_row_kind_is("F5-2-monthly-rows", "array_index"),
        tags=("paradigm", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ④ scope / 计数 / Property 21 分母声明
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M30", side="be", path=SLICE, kind="replace",
        anchor='    "independent_entry_count": 8,',
        new='    "independent_entry_count": 7,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="「自洽删除」形态：把 scope 计数改成 7 仍绿 ⇒ 「8」在文档里无推导，"
            "漏迁一条 entry 时守卫看不出来（判据必须从 manifest 按 selection_rule 现算）",
        scope_check=_top_path_is(7, "slice_scope", "independent_entry_count"),
        tags=("scope", "data"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        anchor='      "entry_id": "xlsx/gt-f5-cost-of-sales",',
        new='      "entry_id": "xlsx/gt-f5-cost-of-sales-x",',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        wants=(
            f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
            f"{_P70}::test_deletion_plan_matches_slice",
        ),
        why="「删一条 entry」的等价形态（entry 集合被篡改）仍绿 ⇒ slice 与 source manifest"
            "的集合等值判据失守",
        scope_check=_has_entry_id("xlsx/gt-f5-cost-of-sales-x"),
        tags=("scope", "data"),
    ),
    Mutation(
        id="M32", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 8,',
        new='      "unadjudicated": 0,',
        want=f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        why="把未裁决计数归零仍绿 ⇒ 「归零不是进度」这条失守，"
            "8 条终态未定的 entry 可以在报告里表现为零欠账",
        scope_check=_top_path_is(
            0, "honest_adjudication_summary", "slice_counters", "unadjudicated"
        ),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M33", side="be", path=SLICE, kind="replace",
        anchor='    "entries_with_composite_transport_key": 1,',
        new='    "entries_with_composite_transport_key": 3,',
        want=f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        why="复合键 entry 计数虚报成 3 仍绿 ⇒ 「复合传输键核验」的产出可以是随口一个数字",
        scope_check=_top_path_is(
            3, "honest_adjudication_summary", "entries_with_composite_transport_key"
        ),
        tags=("counters", "data", "composite"),
    ),
    Mutation(
        id="M34", side="be", path=SLICE, kind="replace",
        scope='    "property_21": {',
        offset=4,
        anchor='      "not_claimed_passing": true',
        new='      "not_claimed_passing": false',
        want=f"{_P21}::test_property_denominator_block_declares_what_is_not_claimed",
        why="🔴 把「Property 21 在 F 循环不宣称通过」改成宣称通过仍绿 ⇒ 空分母重言式的入口"
            "重新打开（Task 46 首轮就是这么写的：没有 contract 所以 Property 21 通过）",
        scope_check=_top_path_is(
            False, "property_denominators", "property_21", "not_claimed_passing"
        ),
        tags=("property", "data", "regression"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ deletion plan 与 slice 的一致性
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M35", side="be", path=PLAN, kind="replace",
        scope=P_F1, offset=3,
        anchor='      "capability_adjudication": null,',
        new='      "capability_adjudication": "single_onlyoffice",',
        want=f"{_P70}::test_deletion_plan_matches_slice",
        why="deletion plan 的裁决与 slice 脱钩仍绿 ⇒ 两份产物可以各说一套，"
            "Task 66/72 会照着旧裁决去删",
        scope_check=_entry_field(
            "xlsx/gt-f1-prepayment", "capability_adjudication", "single_onlyoffice"
        ),
        tags=("plan", "data"),
    ),
    Mutation(
        id="M36", side="be", path=PLAN, kind="replace",
        scope=P_F3, offset=6,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "none",',
        want=f"{_P70}::test_deletion_plan_matches_slice",
        why="plan 侧把 verdict 改成 none 仍绿 ⇒ 「有 HTML 对端」这个决定性事实在删除计划里"
            "可以被单侧翻掉",
        scope_check=_entry_field(
            "xlsx/gt-f3-notes-payable", "html_counterpart_verdict", "none"
        ),
        tags=("plan", "data"),
    ),
    Mutation(
        id="M37", side="be", path=PLAN, kind="replace",
        anchor='          "file": "audit-platform/frontend/src/components/workpaper/composables/useF4DualMode.ts",',
        new='          "file": "audit-platform/frontend/src/components/workpaper/composables/useF4DualMode-不存在.ts",',
        want=f"{_P70}::test_deletion_plan_composables_are_distinct_and_real",
        wants=(f"{_SRC}::test_deletion_plan_covers_every_host_composable",),
        why="清册里的 composable 路径写错仍绿 ⇒ Task 72 会照着一份与磁盘脱钩的清单执行删除",
        scope_check=lambda data: any(
            c["file"].endswith("useF4DualMode-不存在.ts")
            for e in json.loads(data.decode("utf-8"))["entries"]
            for c in e["legacy_composables_to_delete"]
        ),
        tags=("plan", "data"),
    ),
    Mutation(
        id="M38", side="be", path=PLAN, kind="replace",
        scope='      "entry_id": "xlsx/gt-f5-cost-of-sales",',
        offset=22,
        anchor='          "wraps_shared_base": false,',
        new='          "wraps_shared_base": true,',
        want=f"{_P70}::test_f_cycle_composables_really_do_not_wrap_the_shared_base",
        why="把「不包共享基座」误报成 true 仍绿 ⇒ shared_base_preserved 的结论"
            "（F 循环一条都不消费它）没有源码支撑，Task 72 可能连基座一起删",
        scope_check=_plan_composable_field("useF5CosOfDualMode.ts", "wraps_shared_base", True),
        tags=("plan", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ F2 Word lane 边界
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        scope='            "sheet_code": "F2-22",',
        offset=5,
        anchor='            "document_type": "docx",',
        new='            "document_type": "xlsx",',
        want=f"{_WORD}::test_word_lane_block_records_the_authority_model_premise_defect",
        why="把 Word lane 的 document_type 改成 xlsx 仍绿 ⇒ 「该 lane 与本 entry 的 xlsx 通道"
            "无共用」这个裁决前提可以被翻掉而无人发现（翻掉后 F2 监盘就该重算裁决影响）",
        scope_check=_word_lane_writer_field("F2-22", "document_type", "xlsx"),
        tags=("word", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ AC 1.4 的 UI 义务（范式 step 11）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M40", side="be", path=HOST_F1, kind="delete",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f1-prepayment" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        wants=(f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",),
        why="宿主的挂载点被删（import 还留着）仍绿 ⇒ 判据退化成 grep 符号名，"
            "「模型声明了而模板零引用」的结构性死代码照样通过（G7 两级表头 0/38 同型）",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M41", side="be", path=HOST_F2M, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f2-inventory-main" />',
        new='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f2-inventory-special" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="宿主传了别的 entry id 仍绿 ⇒ 通知与 entry 的绑定没被校验，"
            "将来某个 entry 真接上双向后它这条警告不会消失",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M42", side="be", path=HOST_F3, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f3-notes-payable" />',
        new='        <!-- <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f3-notes-payable" /> -->',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="把挂载点整行注释掉仍绿 ⇒ 判据没先 stripComments，注释可以充当证据"
            "（平台已登记的假绿形态）",
        tags=("ac14", "frontend", "stripcomments"),
    ),
    Mutation(
        id="M43", side="be", path=HOST_F5, kind="insert",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f5-cost-of-sales" />',
        new='        <el-tag size="small" type="success">可双向回写</el-tag>',
        want=f"{_AC14}::test_hosts_do_not_claim_bidirectional_writeback",
        why="宿主直接打出「可双向回写」仍绿 ⇒ AC 1.4 前半句无人把守",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M44", side="be", path=HOST_F2S, kind="replace",
        anchor='      <div class="toolbar">',
        new='      <div class="toolbar-x">',
        want=f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",
        why="监盘宿主的工具栏类名被改而 slice 的 ui_toolbar_gate 没跟上仍绿 ⇒ "
            "「通知挂在模式工具栏内」这条判据不会因为宿主结构漂移而打红",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M45", side="be", path=NOTICE_TS, kind="replace",
        anchor="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = []",
        new="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = ['xlsx/gt-f1-prepayment']",
        want=f"{_AC14}::test_registered_entry_ids_agree_with_the_slice",
        why="前端把没有 adapter 的 entry 登记成已注册仍绿 ⇒ 界面会以「已双向」呈现，"
            "正是 AC 1.4 前半句禁止的事",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M46", side="be", path=NOTICE_VUE, kind="replace",
        anchor='      <span class="entry-sync-notice__summary">{{ notice.summary }}</span>',
        new='      <span class="entry-sync-notice__summary">详情</span>',
        want=f"{_AC14}::test_notice_component_renders_summary_and_binds_entry_id",
        why="常显摘要从模板里消失（原因只剩 hover 才出现的 tooltip）仍绿 ⇒ AC 1.4 的"
            "「显示可操作原因」退化成默认看不见（EP tooltip 内容是 teleport）",
        tags=("ac14", "frontend"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ 判据自检本身
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M47", side="fe", path=NOTICE_TS, kind="replace",
        anchor="  if (registeredEntryIds.includes(entryId)) return null",
        new="  return null",
        want="D 循环 7 个 entry 全部拿到非空通知",
        wants=("挂载后真渲染标签、原因与 entry 绑定",),
        why="通知函数恒返回 null（等于关掉整条 AC 1.4 提示）仍绿 ⇒ 前端判据没有正向分母。"
            "F 循环复用的是同一个真源模块，所以由它的既有 spec 承载正向分母",
        tags=("ac14", "frontend", "fe"),
    ),
    Mutation(
        id="M48", side="be", path=PLAN_SYNC, kind="replace",
        anchor='        lane_id="f2_stocktake_plan",',
        new='        lane_id="custom_cells",',
        want=f"{_WORD}::test_both_writers_go_through_the_unified_commit",
        why="🔴 补的是本脚本原先的**覆盖缺口**：`test_both_writers_go_through_the_unified_commit` "
            "里 authority model 那条判据从来没有配套变异。原判据是子串匹配 "
            "`\"AuthorityModel.opaque_single_onlyoffice\" in code`，Task 65 把 "
            "`commit_bytes` 的 `authority_model` 参数删掉、改由 `lane_id` 经 lane 登记表"
            "单向决定之后，那句子串只会在注释里命中 ⇒ 判据已迁到新载体（调用点 lane 字面量 "
            "→ 登记表 → authority model → slice 的 `authority_model_used`）。这条变异把 F2-22 "
            "的 lane 换成 `custom_cells`（登记的 authority model 是 "
            "`custom_authoritative_ooxml`，且它登记的 writer 是 custom 端点而不是本模块）⇒ "
            "四向锁里的两环同时不成立，守卫必须打红。没有这条，「载体迁移」就无法与「判据被"
            "悄悄放宽」区分开",
        tags=("word",),
    ),
]

# 占位条目在声明期就该被拿掉 —— 留着会让 --list 报错
MUTATIONS = [m for m in MUTATIONS if "skip" not in m.tags]

GUARD_FILES = {
    T48: "Task 48 新建（AC 12.8 裁决合法性、HTML 对端三边锁 + 复合传输键四机制、"
         "模板 digest / structure hash / sheet!cell 现算、BP-5/BP-8 复现锁、"
         "evidence/计数/阻断项、F2 Word lane 边界、AC 1.4 的 UI 义务、slice_schema 必填字段）",
    FE_SPEC: "Task 46 收口新建、Task 48 复用（AC 1.4 前端真源两侧分母 + 组件 DOM 判据）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 48 F 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task48_f_cycle_migration.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            frontend_filters=[
                "src/components/workpaper/sync/__tests__/workpaperEntrySyncNotice.spec.ts",
            ],
            frontend_dir=REPO / "audit-platform" / "frontend",
            vitest_json=REPO / "backend" / "scripts" / "diagnose" / "_wip_task48_fe.json",
            baseline_backend_passed=82,
            baseline_frontend_passed=9,
        )
    )
