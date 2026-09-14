# -*- coding: utf-8 -*-
"""Task 46 守卫变异检验 —— D 循环 Excel 独立 entry 迁移（收口重写后）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 46

═══ 为什么有这份脚本 ═══

Task 46 首轮**没有**变异脚本（`file_search "task46"` 只命中测试文件本身），36 例守卫
从未做过变异检验 —— 而它恰好有四处 fail-open 和一处硬编码豁免。同 spec 的 Task 20 有
`mutate_task20_writer_gate_guards.py`、Tasks 40~44 各有自己的脚本。

用户要求「照 `mutate_task47_e_cycle_migration_guards.py` 的风格」：**该文件不存在**
（`backend/scripts/diagnose/` 里 task 系列只到 mutate_task44_…，另有与本 spec 无关的
`mutate_e_cycle_guards.py`）。故本脚本以同 spec 最近的 `mutate_task40_simple_checklist_
pilot_guards.py` 为风格基准。

覆盖面分母 = 本次收口重写的后端守卫 + 新建的前端 AC 1.4 判据。

用法（仓库根，注意本仓库 PATH 上的 `python` 指向坏掉的 venv）::

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task46_d_cycle_migration_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task46_d_cycle_migration_guards.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task46_d_cycle_migration_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task46-d-cycle-migration/mutation_report.json

🔴 数据文件（slice / deletion plan / 契约 JSON）的变异一律带 `scope_check`：锚点可能命中
别处同形态行，只看「新增失败集合」会把「改到了别的字段」误报成 GREEN。

🔴 7 条 entry 的多数字段逐字相同（`"capability": null,` 出现 7 次），这类锚点必须用
`scope`（唯一的 entry_id 行）+ `offset` 相对定位，不能用绝对行号 —— slice 是生成物，
行号一改就失效。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_d_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_d_cycle_deletion_plan.json"
CONTRACT = "backend/data/workpaper_sync_contracts/d2.receivable_detail.json"
CHECKLIST_ROUTER = "backend/app/routers/checklist_responses.py"
INSTRUMENTATION = "backend/app/services/workpaper_sync/excel_instrumentation.py"
NOTICE_TS = "audit-platform/frontend/src/components/workpaper/sync/workpaperEntrySyncNotice.ts"
NOTICE_VUE = "audit-platform/frontend/src/components/workpaper/sync/GtEntrySyncCapabilityNotice.vue"
HOST_D3 = "audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue"
HOST_D5 = "audit-platform/frontend/src/components/workpaper/GtD5ReceivablesFinancing.vue"
HOST_D6 = "audit-platform/frontend/src/components/workpaper/GtD6ContractAssets.vue"
HOST_D7 = "audit-platform/frontend/src/components/workpaper/GtD7ContractLiabilities.vue"

T46 = "test_task46_d_cycle_migration.py"
FE_SPEC = "workpaperEntrySyncNotice.spec.ts"

_ADJ = f"{T46}::TestAdjudicationLegality"
_HTML = f"{T46}::TestHtmlCounterpartIsSourceBacked"
_P2021 = f"{T46}::TestProperty20And21ContractAndAdapter"
_P28 = f"{T46}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T46}::TestProperty69EvidencePerEntry"
_P70 = f"{T46}::TestProperty70NoCrossEntryReuse"
_AC14 = f"{T46}::TestAc14HonestModeVisibility"
_PARA = f"{T46}::TestParadigmCompliance"
_MANI = f"{T46}::TestManifestAlignment"

# ── 相对定位用的唯一 scope 锚（每个 entry 的 entry_id 行）───────────────────
S_D1 = '      "entry_id": "xlsx/gt-d1-notes-receivable",'
S_D2 = '      "entry_id": "xlsx/gt-d2-accounts-receivable",'
S_D3 = '      "entry_id": "xlsx/gt-d3-prepaid-accounts",'
S_D7 = '      "entry_id": "xlsx/gt-d7-contract-liabilities",'
P_D1 = '      "entry_id": "xlsx/gt-d1-notes-receivable",'  # deletion plan 内同形态


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
# ═══════════════════════════════════════════════════════════════════════════
def _slice_entry_field(entry_id: str, *path: str):
    """slice 里某 entry 的嵌套字段必须**恰好**等于期望值。"""
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["independent_entries"]:
            if entry["entry_id"] != entry_id:
                continue
            node = entry
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return False
                node = node[key]
            return node == expected
        return False

    return check


def _slice_entry_key_absent(entry_id: str, key: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["independent_entries"]:
            if entry["entry_id"] == entry_id:
                return key not in entry
        return False

    return check


def _slice_has_entry_id(entry_id: str):
    """slice 的 entry 集合里必须出现该 id（用于「entry_id 被改名」这类变异）。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        return entry_id in {e["entry_id"] for e in payload["independent_entries"]}

    return check


def _slice_top_absent(key: str):
    def check(data: bytes) -> bool:
        return key not in json.loads(data.decode("utf-8"))

    return check


def _slice_counter_is(key: str, expected: int):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        return payload["honest_adjudication_summary"]["slice_counters"][key] == expected

    return check


def _slice_scope_count_is(expected: int):
    def check(data: bytes) -> bool:
        return json.loads(data.decode("utf-8"))["slice_scope"][
            "independent_entry_count"
        ] == expected

    return check


def _slice_template_field(name: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _slice_bp_field(bp_index: int, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        blocking = payload["blocking_preconditions"]
        if bp_index >= len(blocking):
            return False
        return blocking[bp_index].get(key) == expected

    return check


def _plan_entry_field(entry_id: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["entries"]:
            if entry["entry_id"] == entry_id:
                return entry.get(key) == expected
        return False

    return check


def _contract_path_is(expected, *keys: str):
    def check(data: bytes) -> bool:
        node = json.loads(data.decode("utf-8"))
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected

    return check


def _contract_field_key(column_key: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for sheet in payload["sheets"]:
            for table in sheet["tables"]:
                for field in table["fields"]:
                    if field.get("column_key") == column_key:
                        return field.get(key) == expected
        return False

    return check


def _contract_formula_mask_first_is(expected: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        masks = payload["sheets"][0]["tables"][0]["formula_mask"]
        return bool(masks) and masks[0] == expected

    return check


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① 用户首轮已做过的 5 条（4 条原本 RED 必须保持 RED，template_ref→null 原本
    #    GREEN 必须变 RED）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=5,
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
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "capability", "bidirectional"
        ),
        tags=("adjudication", "data", "regression"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        anchor='      "template_ref": "D/D1 应收票据.xlsx",',
        new='      "template_ref": "D/D1 应收票据-不存在.xlsx",',
        want=f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",
        wants=(f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",),
        why="template_ref 指向不存在的文件仍绿 ⇒ 「权威模板只认 backend/wp_templates」这条"
            "无人把守，后面每个 digest 都会对着一份不存在的模板算",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "template_ref", "D/D1 应收票据-不存在.xlsx"
        ),
        tags=("template", "data", "regression"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        anchor='      "mount_count": 2,',
        scope=S_D1, offset=23,
        new='      "mount_count": 9,',
        want=f"{_MANI}::test_source_backed_profile_fields_match_the_manifest",
        why="source-backed 的 mount_count 被手改仍绿 ⇒ slice 可以脱离生成器事实自说自话",
        scope_check=_slice_entry_field("xlsx/gt-d1-notes-receivable", "mount_count", 9),
        tags=("manifest", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        anchor='    "independent_entry_count": 7,',
        new='    "independent_entry_count": 6,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="「自洽删除」形态：把 scope 计数改成 6 仍绿 ⇒ 「7」在文档里无推导，"
            "漏迁一条 entry 时守卫看不出来（判据必须从 manifest 按 selection_rule 现算）",
        scope_check=_slice_scope_count_is(6),
        tags=("scope", "data", "regression"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        anchor='      "entry_id": "xlsx/gt-d7-contract-liabilities",',
        new='      "entry_id": "xlsx/gt-d7-contract-liabilities-x",',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        wants=(
            f"{_MANI}::test_slice_entry_ids_in_full_manifest",
            f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        ),
        why="「删一条 entry」的等价形态（entry 集合被篡改）仍绿 ⇒ slice 与 source manifest"
            "的集合等值判据失守",
        # 🔴 首轮这里写的是 `_slice_entry_key_absent("xlsx/gt-d7-contract-liabilities", ...)`，
        #    实测 ANCHOR-MISS：改名后按原 id 找不到 entry，回调直接 return False。
        #    自证要断言**改后的 id 真在集合里**（脚本缺陷，不是守卫缺陷）。
        scope_check=_slice_has_entry_id("xlsx/gt-d7-contract-liabilities-x"),
        tags=("scope", "data", "regression"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        anchor='      "template_ref": "D/D5 应收款项融资.xlsx",',
        new='      "template_ref": null,',
        want=f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",
        why="🔴 收口前这一条是 **GREEN**：首轮判据写的是 `if tref:` —— template_ref 为 null 时"
            "整条跳过（实测置 null 后 36 例全绿）。修完必须 RED",
        scope_check=_slice_entry_field(
            "xlsx/gt-d5-receivables-financing", "template_ref", None
        ),
        tags=("template", "data", "failopen"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ② AC 12.8 裁决判据（本次收口的核心）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=S_D3, offset=28,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="AP-3：把「还没查」写成 unresolved 仍绿 ⇒ step 3 的二值结论可以被含糊值顶替，"
            "而据此裁 single 就又回到循环论证",
        scope_check=_slice_entry_field(
            "xlsx/gt-d3-prepaid-accounts", "html_counterpart_verdict", "unresolved"
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        scope=S_D2, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_P2021}::test_contract_presence_forbids_single_onlyoffice",
        wants=(
            f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="🔴 这正是首轮的缺陷本体：D2 有 per-entry contract（contract 里逐字记着 HTML 对端）"
            "却被裁 single_onlyoffice。首轮守卫用 `if name.startswith(\"d2\"): continue` 硬编码"
            "豁免把它放过去了 —— 换成真判据后必须 RED",
        scope_check=_slice_entry_field(
            "xlsx/gt-d2-accounts-receivable", "capability", "single_onlyoffice"
        ),
        tags=("adjudication", "data", "exemption"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=86,
        anchor='        "criterion_source": "backend/data/workpaper_sync_migration_paradigm.json#adjudication_criteria.verdicts"',
        new='        "reason": "无 bidirectional adapter，无 per-entry contract"',
        want=f"{_ADJ}::test_adjudication_reason_is_not_circular",
        why="用重复键把裁决理由替换成循环论证原文（JSON 后出现的键胜出）仍绿 ⇒ AP-1 判据无效，"
            "首轮那句「None of the D-cycle entries have real bidirectional adapters…」可以复活",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable",
            "adjudication",
            "reason",
            "无 bidirectional adapter，无 per-entry contract",
        ),
        tags=("adjudication", "data", "ap1"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=6,
        anchor='      "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",',
        new='      "capability_verdict_stage_x": "pipeline_entry_pending_definition_delivery",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_slice_satisfies_the_paradigm_slice_schema",),
        why="capability 为 null 却不解释仍绿 ⇒ 「未裁决」可以伪装成「已裁决」，"
            "AC 1.8 的未裁决计数失去意义",
        scope_check=_slice_entry_key_absent(
            "xlsx/gt-d1-notes-receivable", "capability_verdict_stage"
        ),
        tags=("adjudication", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ③ HTML 对端三边锁（slice ↔ 前端源码 ↔ 权威 xlsx）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='          "identity_text": "对方单位名称"',
        new='          "identity_text": "客户名称"',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="第三边（权威 xlsx 真读）：身份列表头被改成别张表的文案仍绿 ⇒ "
            "「HTML 对端有模板依据」退化成自由文本",
        scope_check=_slice_entry_field(
            "xlsx/gt-d3-prepaid-accounts",
            "html_counterpart", "primary_table", "identity_text", "客户名称",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='          "identity_cell": "A5",',
        new='          "identity_cell": "A6",',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="身份单元格被挪到空格（D4-4 的 A6 是空行）仍绿 ⇒ 单元格坐标没被真读校验",
        scope_check=_slice_entry_field(
            "xlsx/gt-d4-operating-revenue",
            "html_counterpart", "primary_table", "identity_cell", "A6",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=52,
        anchor='          "owner_constant": "STORAGE_KEY",',
        new='          "owner_constant": "ITEM_ID_ROWS",',
        want=f"{_HTML}::test_primary_table_is_declared_by_its_owner_module",
        why="第二边（前端源码）：owner 常量名与真实声明不符仍绿 ⇒ 「item_id 由这个模块声明」"
            "没有被磁盘证实，改名/删除都不会打红",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable",
            "html_counterpart", "primary_table", "owner_constant", "ITEM_ID_ROWS",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='          "owner_declaration_kind": "inline_literal",',
        new='          "owner_declaration_kind": "module_constant",',
        want=f"{_HTML}::test_primary_table_is_declared_by_its_owner_module",
        why="D2 的 item_id 是内联字面量（无模块常量）。把形态标成 module_constant 仍绿 ⇒ "
            "两种声明形态的判据分支有一侧恒真",
        scope_check=_slice_entry_field(
            "xlsx/gt-d2-accounts-receivable",
            "html_counterpart", "primary_table", "owner_declaration_kind", "module_constant",
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='        "backend/app/routers/wp_render_strategies/_d1_notes_receivable.py",',
        new='        "backend/app/routers/wp_render_strategies/_d1_不存在.py",',
        want=f"{_HTML}::test_source_refs_point_at_real_paths",
        why="source_ref 指向不存在的文件仍绿 ⇒ 「结论带 source_refs」变成贴标签",
        scope_check=lambda data: "_d1_不存在.py" in data.decode("utf-8"),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=37,
        anchor='        "row_identity_key": "rowId",',
        new='        "row_identity_key": "index",',
        want=f"{_HTML}::test_row_identity_key_is_not_positional",
        why="行身份键改成下标形态仍绿 ⇒ stable row key 这条约束在 D 循环上整条不生效",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "html_counterpart", "row_identity_key", "index"
        ),
        tags=("counterpart", "data"),
    ),
    Mutation(
        id="M17", side="be", path=CHECKLIST_ROUTER, kind="replace",
        anchor='    prefix="/api/workpapers/{wp_id}/checklist-responses",',
        new='    prefix="/api/workpapers/{wp_id}/checklist-responses-v2",',
        want=f"{_HTML}::test_html_store_endpoints_exist_in_the_router",
        why="slice 声称的持久化端点在后端改了前缀仍绿 ⇒ 「HTML 对端存在」的端点侧证据"
            "与生产路由脱钩（fail-open 掩盖接线错误的形态）",
        tags=("counterpart", "backend"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ④ Property 28：真 digest 漂移（替代首轮的空分母）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "e6e8dcf28ba6e7f6fdf9867c3ac43b2f1a72e1a1b6f2aa477f58dfca39097577",',
        new='        "sha256": "e6e8dcf28ba6e7f6fdf9867c3ac43b2f1a72e1a1b6f2aa477f58dfca39097578",',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="模板 sha256 改一位仍绿 ⇒ 首轮的 `assert tpath.exists()` 只查存在不查内容，"
            "模板被换掉看不出来（Task 47 的 E slice 会红，Task 46 首轮不会）",
        scope_check=_slice_template_field(
            "D1 应收票据.xlsx",
            "sha256",
            "e6e8dcf28ba6e7f6fdf9867c3ac43b2f1a72e1a1b6f2aa477f58dfca39097578",
        ),
        tags=("template", "data", "failopen"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='        "size": 138008,',
        new='        "size": 138009,',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="模板 size 与实况不符仍绿 ⇒ size 这一维是死数据（Task 47 把 size+sha256 双冻结）",
        scope_check=_slice_template_field("D1 应收票据.xlsx", "size", 138009),
        tags=("template", "data", "failopen"),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        anchor='        "belongs_to_entry": "xlsx/gt-d1-notes-receivable",',
        new='        "belongs_to_entry": "xlsx/gt-d1-不存在",',
        want=f"{_P28}::test_template_owner_mapping_is_consistent",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="SR-8：模板挂到不存在的 entry 上仍绿 ⇒ 可以悄悄夹带跨循环模板",
        scope_check=_slice_template_field(
            "D1 应收票据.xlsx", "belongs_to_entry", "xlsx/gt-d1-不存在"
        ),
        tags=("template", "data"),
    ),
    Mutation(
        id="M21", side="be", path=CONTRACT, kind="replace",
        anchor='    "template_sha256": "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"',
        new='    "template_sha256": "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afb"',
        want=f"{_P28}::test_d2_contract_template_digests_recompute_from_the_template_bytes",
        wants=(f"{_P28}::test_d2_contract_identity_digests_are_real_digests",),
        why="🔴 首轮 Property 28 的整个论证是「没有 definition bundle → 无可漂移 identity → 通过」"
            "（空分母重言式）。D2 契约的 template_sha256 是**真分母**：改一位必须红",
        scope_check=_contract_path_is(
            "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afb",
            "template", "template_sha256",
        ),
        tags=("digest", "data", "tautology"),
    ),
    Mutation(
        id="M22", side="be", path=CONTRACT, kind="replace",
        anchor='    "normalized_structure_hash": "ff7a91a514db64ca030103f8cb10759fc4e62c77cf6d4cbe3c61bb7d69ebdc9e",',
        new='    "normalized_structure_hash": "ff7a91a514db64ca030103f8cb10759fc4e62c77cf6d4cbe3c61bb7d69ebdc9f",',
        want=f"{_P28}::test_d2_contract_template_digests_recompute_from_the_template_bytes",
        why="结构 hash 改一位仍绿 ⇒ 「可见业务结构漂移 fail closed」在 D 循环上没有落点",
        scope_check=_contract_path_is(
            "ff7a91a514db64ca030103f8cb10759fc4e62c77cf6d4cbe3c61bb7d69ebdc9f",
            "template", "normalized_structure_hash",
        ),
        tags=("digest", "data", "tautology"),
    ),
    Mutation(
        id="M23", side="be", path=INSTRUMENTATION, kind="replace",
        anchor='    joined = "\\n".join(f"{name}={aspects[name]}" for name in sorted(aspects))',
        new='    joined = "constant"',
        want=f"{_P28}::test_d2_contract_template_digests_recompute_from_the_template_bytes",
        why="把结构 hash 的输入换成常量（任何 workbook 都得同一个 hash）仍绿 ⇒ 我这条判据是"
            "自证式同义反复，只在比两个都错的值",
        tags=("digest", "backend", "tautology"),
    ),
    Mutation(
        id="M24", side="be", path=CONTRACT, kind="replace",
        anchor='            "Q13:Q25",',
        new='            "H13:H25",',
        want=f"{_P28}::test_d2_formula_mask_columns_are_really_formulas",
        why="把 formula_mask 指到模板里**不是公式**的 H 列仍绿 ⇒ 受保护格分类没有对着权威模板"
            "真读（H 列在契约里正是被判 editable 的那一列）",
        scope_check=_contract_formula_mask_first_is("H13:H25"),
        tags=("digest", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ Property 20/21：契约真分母 + 反例判据
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M25", side="be", path=CONTRACT, kind="replace",
        anchor='              "source_ref": "源xlsx!明细表D2-2!A13",',
        new='              "source_ref": "",',
        want=f"{_P2021}::test_d2_contract_fields_are_complete_and_source_backed",
        why="契约字段的 source_ref 被清空仍绿 ⇒ 「逐字段有来源」这条只是形状检查",
        scope_check=_contract_field_key("seq", "source_ref", ""),
        tags=("contract", "data"),
    ),
    Mutation(
        id="M26", side="be", path=CONTRACT, kind="replace",
        anchor='              "column_key": "seq",',
        new='              "column_key": "col_a",',
        want=f"{_P2021}::test_d2_contract_has_no_generated_column_placeholder",
        why="Property 20：`col_[a-z]+` 无语义列占位混进生产契约仍绿 ⇒ 首轮「没有 contract 所以"
            "Property 20 通过」的空分母论证一旦有了契约就彻底无守",
        scope_check=_contract_field_key("col_a", "mode", "editable"),
        tags=("contract", "data", "tautology"),
    ),
    Mutation(
        id="M27", side="be", path=CONTRACT, kind="replace",
        anchor='    "entry_id": "xlsx/gt-d2-accounts-receivable",',
        new='    "entry_id": "xlsx/gt-zz-somewhere-else",',
        want=f"{_P2021}::test_contract_presence_forbids_single_onlyoffice",
        wants=(
            f"{_P2021}::test_d2_contract_records_the_html_counterpart",
            f"{_P2021}::test_entries_without_contract_have_no_contract_file",
        ),
        why="契约的归属 entry 被改走仍绿 ⇒ 「contract 存在 ⇒ 不得裁 single_onlyoffice」这条"
            "真判据可以被改 entry_id 绕过（正是硬编码豁免换掉的那条）",
        scope_check=_contract_path_is(
            "xlsx/gt-zz-somewhere-else", "review", "entry_id"
        ),
        tags=("contract", "data", "exemption"),
    ),
    Mutation(
        id="M28", side="be", path=CONTRACT, kind="replace",
        anchor='      "item_id": "D2-detail-rows",',
        new='      "item_id": "D2-detail-rows-v2",',
        want=f"{_P2021}::test_d2_contract_records_the_html_counterpart",
        why="契约记的 HTML store item_id 与 slice 不一致仍绿 ⇒ 两侧双向锁失效，"
            "「D2 有 HTML 对端」这个反例的证据可以被单侧改掉",
        scope_check=_contract_path_is(
            "D2-detail-rows-v2", "review", "html_store", "item_id"
        ),
        tags=("contract", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ Property 69：evidence / 计数 / 阻断项
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=93,
        anchor='        "verification_state": "UNVERIFIABLE",',
        new='        "verification_state": "VERIFIED",',
        want=f"{_P69}::test_no_entry_claims_verified_without_a_test_run",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="没有 sync_test_run_id / scenario digest 就声称 VERIFIED 仍绿 ⇒ AC 12.13 的"
            "「bidirectional 未验收=0」可以靠改字符串达成",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "evidence", "verification_state", "VERIFIED"
        ),
        tags=("evidence", "data"),
    ),
    Mutation(
        id="M30", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=94,
        anchor='        "unverifiable_reasons": [',
        new='        "unverifiable_reasons_x": [',
        want=f"{_P69}::test_evidence_state_and_reasons",
        why="SR-7：标 UNVERIFIABLE 却不给原因仍绿 ⇒ 等于自由文本豁免；"
            "首轮 7 条 entry 的 evidence 整个字段缺失（连 UNVERIFIABLE 都没标）就是这个后果",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "evidence", "verification_state", "UNVERIFIABLE"
        ),
        tags=("evidence", "data", "failopen"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 7,',
        new='      "unadjudicated": 0,',
        want=f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        why="把未裁决计数抹成 0 仍绿 ⇒ 首轮那个「四类计数全为 0」的假绿可以原样复活",
        scope_check=_slice_counter_is("unadjudicated", 0),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M32", side="be", path=SLICE, kind="replace",
        anchor='      "id": "BP-5",',
        new='      "id": "BP-1",',
        want=f"{_P69}::test_blocking_preconditions_are_complete",
        wants=(f"{_P69}::test_capability_blockers_reference_real_preconditions",),
        why="阻断项 id 重复仍绿 ⇒ entry 上引用的 BP-5 实际不存在，「缺什么由谁兑现」的登记断链",
        scope_check=_slice_bp_field(4, "id", "BP-1"),
        tags=("blocking", "data"),
    ),
    Mutation(
        id="M33", side="be", path=SLICE, kind="replace",
        anchor='        "backend/app/services/workpaper_sync/excel_entry_gate.py",',
        new='        "backend/app/services/workpaper_sync/不存在.py",',
        want=f"{_P69}::test_blocking_preconditions_are_complete",
        why="阻断项的 source_ref 指向不存在的路径仍绿 ⇒ 无据可查的阻断项 = 自由文本豁免",
        scope_check=lambda data: "workpaper_sync/不存在.py" in data.decode("utf-8"),
        tags=("blocking", "data"),
    ),
    Mutation(
        id="M34", side="be", path=SLICE, kind="replace",
        anchor='  "cross_entry_isolation": {',
        new='  "cross_entry_isolation_x": {',
        want=f"{_P70}::test_cross_entry_isolation_block_present",
        wants=(f"{_PARA}::test_slice_satisfies_the_paradigm_slice_schema",),
        why="Property 70 的隔离声明整块消失仍绿 ⇒ 跨 entry 复用 contract/evidence 无人把守",
        scope_check=_slice_top_absent("cross_entry_isolation"),
        tags=("isolation", "data"),
    ),
    Mutation(
        id="M35", side="be", path=SLICE, kind="replace",
        anchor='      "per_entry_contract": {',
        new='      "per_entry_contract_x": {',
        want=f"{_P70}::test_only_d2_carries_a_contract",
        wants=(f"{_P2021}::test_entries_without_contract_have_no_contract_file",),
        why="D2 的契约登记被摘掉仍绿 ⇒ 契约目录 ↔ slice 登记的双向等值失效，"
            "未登记的生产契约可以溜进目录",
        scope_check=_slice_entry_key_absent(
            "xlsx/gt-d2-accounts-receivable", "per_entry_contract"
        ),
        tags=("isolation", "data"),
    ),
    Mutation(
        id="M36", side="be", path=SLICE, kind="replace",
        anchor='  "paradigm_schema_conflict": {',
        new='  "paradigm_schema_conflict_x": {',
        want=f"{_PARA}::test_paradigm_conflict_is_registered",
        why="范式内部冲突的登记被摘掉仍绿 ⇒ 「按哪一侧执行」这个决定可以不留痕，"
            "下一轮又会有人按 slice_schema 的 applies_to_tasks 认为 D slice 不用改",
        scope_check=_slice_top_absent("paradigm_schema_conflict"),
        tags=("paradigm", "data"),
    ),
    Mutation(
        id="M37", side="be", path=SLICE, kind="replace",
        scope=S_D1, offset=72,
        anchor='        "capability": "single_onlyoffice",',
        new='        "capability": null,',
        want=f"{_MANI}::test_manifest_capability_divergence_is_registered",
        why="manifest 镜像被改成与 slice 一致（分歧被抹平）仍绿 ⇒ BP-6 那条真实分歧从账面消失，"
            "而 overlay 的组件级默认值又会被当成裁决真源（首轮 `assert 相等` 的原罪）",
        scope_check=_slice_entry_field(
            "xlsx/gt-d1-notes-receivable", "manifest_mirror", "capability", None
        ),
        tags=("manifest", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ deletion plan 与 slice 的一致性
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M38", side="be", path=PLAN, kind="replace",
        scope=P_D1, offset=3,
        anchor='      "capability_adjudication": null,',
        new='      "capability_adjudication": "single_onlyoffice",',
        want=f"{_P70}::test_deletion_plan_adjudication_matches_slice",
        why="deletion plan 的裁决与 slice 脱钩仍绿 ⇒ 两份产物可以各说一套，"
            "Task 66/72 会照着旧裁决去删",
        scope_check=_plan_entry_field(
            "xlsx/gt-d1-notes-receivable", "capability_adjudication", "single_onlyoffice"
        ),
        tags=("plan", "data"),
    ),
    Mutation(
        id="M39", side="be", path=PLAN, kind="replace",
        scope=P_D1, offset=24,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "none",',
        want=f"{_P70}::test_deletion_plan_adjudication_matches_slice",
        why="plan 侧把 verdict 改成 none 仍绿 ⇒ 「有 HTML 对端」这个决定性事实在删除计划里"
            "可以被单侧翻掉",
        scope_check=_plan_entry_field(
            "xlsx/gt-d1-notes-receivable", "html_counterpart_verdict", "none"
        ),
        tags=("plan", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ AC 1.4 的 UI 义务（step 11）—— 只声明不渲染 = 结构性死代码
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M40", side="be", path=NOTICE_VUE, kind="replace",
        anchor='      <span class="entry-sync-notice__summary">{{ notice.summary }}</span>',
        new='      <span class="entry-sync-notice__summary">详情</span>',
        want=f"{_AC14}::test_notice_component_renders_summary_and_binds_entry_id",
        why="常显摘要从模板里消失（原因只剩 hover 才出现的 tooltip）仍绿 ⇒ AC 1.4 的"
            "「显示可操作原因」退化成默认看不见（EP tooltip 内容是 teleport）",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M41", side="be", path=HOST_D5, kind="delete",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d5-receivables-financing" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        wants=(f"{_AC14}::test_notice_mount_sits_inside_the_mode_toolbar",),
        why="宿主的挂载点被删（import 还留着）仍绿 ⇒ 判据退化成 grep 符号名，"
            "「模型声明了而模板零引用」的结构性死代码照样通过（G7 两级表头 0/38 同型）",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M42", side="be", path=HOST_D6, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d6-contract-assets" />',
        new='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d7-contract-liabilities" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="宿主传了别的 entry id 仍绿 ⇒ 通知与 entry 的绑定没被校验，"
            "将来某个 entry 真接上双向后它这条警告不会消失",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M43", side="be", path=HOST_D7, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d7-contract-liabilities" />',
        new='        <!-- <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d7-contract-liabilities" /> -->',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="把挂载点整行注释掉仍绿 ⇒ 判据没先 stripComments，注释可以充当证据"
            "（平台已登记的假绿形态）",
        tags=("ac14", "frontend", "stripcomments"),
    ),
    Mutation(
        id="M44", side="be", path=NOTICE_TS, kind="replace",
        anchor="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = []",
        new="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = ['xlsx/gt-d1-notes-receivable']",
        want=f"{_AC14}::test_registered_entry_ids_agree_with_the_slice",
        why="前端把没有 adapter 的 entry 登记成已注册仍绿 ⇒ 界面会以「已双向」呈现，"
            "正是 AC 1.4 前半句禁止的事",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M45", side="be", path=HOST_D3, kind="insert",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d3-prepaid-accounts" />',
        new='        <el-tag size="small" type="success">可双向回写</el-tag>',
        want=f"{_AC14}::test_hosts_do_not_claim_bidirectional_writeback",
        why="宿主直接打出「可双向回写」仍绿 ⇒ AC 1.4 前半句无人把守",
        tags=("ac14", "frontend"),
    ),
    Mutation(
        id="M46", side="fe", path=NOTICE_TS, kind="replace",
        anchor="  if (registeredEntryIds.includes(entryId)) return null",
        new="  return null",
        want="D 循环 7 个 entry 全部拿到非空通知",
        wants=("挂载后真渲染标签、原因与 entry 绑定",),
        why="通知函数恒返回 null（等于关掉整条 AC 1.4 提示）仍绿 ⇒ 前端判据没有正向分母",
        tags=("ac14", "frontend", "fe"),
    ),
    Mutation(
        id="M47", side="fe", path=NOTICE_TS, kind="replace",
        anchor="  '结构化视图与在线编辑各自独立保存，互不同步'",
        new="  '同步成功'",
        want="不得出现笼统成功态文案",
        wants=("常显摘要一行说清「各自独立、互不同步」",),
        why="把摘要换成笼统成功态文案仍绿 ⇒ AC 11.3 同族的「不得统一显示同步成功」在这里失守",
        tags=("ac14", "frontend", "fe"),
    ),
]

GUARD_FILES = {
    T46: "Task 46 收口重写（AC 12.8 裁决合法性、HTML 对端三边锁、真 digest 漂移、"
         "evidence/计数/阻断项、AC 1.4 的 UI 义务、slice_schema 必填字段）",
    FE_SPEC: "Task 46 收口新建（AC 1.4 前端真源两侧分母 + 组件 DOM 判据）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 46 D 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task46_d_cycle_migration.py",
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
            vitest_json=REPO / "backend" / "scripts" / "diagnose" / "_wip_task46_fe.json",
            baseline_backend_passed=72,
            baseline_frontend_passed=9,
        )
    )
