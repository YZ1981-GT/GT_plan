"""导入导出全生命周期守卫的变异检验 —— Wave 6 Task 21

spec: workpaper-import-export-lifecycle-closure（R7.2、R7.3）

## 为什么需要这个脚本

守卫全绿**不能**证明守卫有效。memory 记的假绿三源里有两条直指守卫本身：

* grep 式守卫只查字符串存在（改成 `if False:` / 删调用 / 改名残留仍绿）
* 守卫把错值当基线锁死（把真源改对反而打红）

⇒ 判据是「**改坏代码后守卫是否打红，且红在预期那一条**」。本 spec 开发过程中
逐 Task 做过 37 个变异，本脚本把它们固化成可重复运行的回归工具。

## 四态判定（按失败测试名集合，🔴 不看退出码）

| 判定 | 含义 | 说明 |
|---|---|---|
| RED | 打红，且失败集合含预期那条 | 守卫有效 |
| GREEN | 没打红 | **守卫缺陷** —— 该判据形同虚设 |
| ANCHOR-MISS | 锚点命中数 != 1 | **脚本缺陷**，不是守卫结论 |
| WRONG-TEST | 打红了但预期项不在失败集合 | 锚点错行 / 污染残留 |

只看退出码会把后三态全部误判成 RED —— 这是本项目实测踩过的坑：
`M7` 明明打红了正确的守卫，却因为「消息内容匹配」失败被判 WRONG-TEST
（vitest 把数组折叠成 `[Array(n)]`，预期片段落在 diff 里而非消息前 400 字符），
故本脚本一律按**测试名**匹配。

## CRLF 归一（本仓库是 CRLF）

含 `\\n` 的跨行锚点若直接用 LF 写，在 CRLF 文件里必然 ANCHOR-MISS。
`_read` / `_write` 统一按 LF 处理内存中的文本，落盘时保持原始换行风格。

## 备份与还原

每次变异前把原文件复制成 `<file>.mutbak`，并记 md5；`finally` 里还原后
**立即重算 md5 比对**，不符就大声报错（不能只写在 finally 里就当已还原
—— 本项目实测过「finally 里的复原因连接池炸掉而静默失败，真把库改坏」）。
`--restore` 可在脚本被强杀后手工收尾。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[3]
_FRONTEND = _REPO / "audit-platform" / "frontend"

BAK_SUFFIX = ".mutbak"


# ═══════════════════════════════════════════════════════════════════════════
# 守卫清单（覆盖率分母）
# ═══════════════════════════════════════════════════════════════════════════

#: 本 spec 的全部守卫文件。**漏登记一个 = 该文件的守卫全体缺席变异检验**。
GUARD_FILES: dict[str, str] = {
    # 元守卫（Task 22）—— 守「五类是否都有人守」与「CI 是否真挂了」
    "guard_coverage": "backend/tests/test_ie_lifecycle_guard_coverage.py",
    "ci_wiring": "backend/tests/test_ie_lifecycle_ci_wiring.py",
    # 后端
    "self_evidence": "backend/tests/services/test_wp_export_self_evidence.py",
    "download_manifest": "backend/tests/services/test_wp_download_manifest.py",
    "route_inventory": "backend/tests/test_ie_route_inventory.py",
    "entry_payload": "backend/tests/services/test_entry_payload_reader.py",
    "export_entry_sheet": "backend/tests/services/test_export_entry_sheet.py",
    "scenario_registry": "backend/tests/services/test_scenario_registry.py",
    "bulk_mode_mismatch": "backend/tests/services/test_bulk_mode_mismatch.py",
    "bulk_visible_granularity": (
        "backend/tests/services/test_bulk_visible_filter_granularity.py"
    ),
    "archive_gating": "backend/tests/services/test_archive_gating.py",
    "prefix_reachability": "backend/tests/test_ie_prefix_reachability.py",
    "scenario_ui": "backend/tests/test_bulk_scenario_ui_single_source.py",
    "templates_readonly": "backend/tests/test_wp_templates_readonly.py",
    "deref_script": "backend/tests/scripts/test_wp_template_deref.py",
    # 前端
    "orphan_baseline": (
        "audit-platform/frontend/src/components/workpaper/__tests__/ieOrphanBaseline.spec.ts"
    ),
    "wiring_integrity": (
        "audit-platform/frontend/src/components/workpaper/__tests__/ieWiringIntegrity.spec.ts"
    ),
    "registry_lock": (
        "audit-platform/frontend/src/components/workpaper/shared/__tests__"
        "/cycleImportExportRegistry.spec.ts"
    ),
    "bulk_dialog": (
        "audit-platform/frontend/src/components/workpaper/bulk-tab/__tests__"
        "/WpBulkImportExport.spec.ts"
    ),
}

FRONTEND_GUARD_KEYS = {"orphan_baseline", "wiring_integrity", "registry_lock", "bulk_dialog"}


# ═══════════════════════════════════════════════════════════════════════════
# 变异定义
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Mutation:
    """一个变异。

    Attributes:
        mid: 变异编号（与 spec tasks.md 的实录对应）。
        guard: 所属守卫（`GUARD_FILES` 的键），决定跑哪个测试文件。
        desc: 改坏了什么（中文，报告直接展示）。
        target: 被改的文件（相对仓库根）。
        old: 锚点原文，**必须在目标文件里恰好出现 1 次**。
        new: 替换文本。
        expect: 预期失败测试名的片段。
        destructive: 是否触碰真实资产（模板库 / 数据库）—— 这类默认跳过，
            须显式 `--include-destructive` 才跑，且脚本会额外校验还原。
    """

    mid: str
    guard: str
    desc: str
    target: str
    old: str
    new: str
    expect: str
    destructive: bool = False


#: 🔴 已验证有效的变异集。每条都在开发过程中真跑过并判定为 RED。
#:
#: 编号沿用 tasks.md 实录（M1~M37），便于双向对照。
MUTATIONS: tuple[Mutation, ...] = (
    # ── 接线完整性（Task 17）────────────────────────────────────────────
    Mutation(
        "M1", "wiring_integrity",
        "父宿主去掉 @imported 绑定（子 emit 没人听 ⇒ 导入后视图不刷新）",
        "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue",
        '            :is-readonly="isReadonly"\n            @imported="selfLoad()"\n          />\n          <H7TabDetailFair',
        '            :is-readonly="isReadonly"\n          />\n          <H7TabDetailFair',
        "渲染宿主",
    ),
    Mutation(
        "M2", "wiring_integrity",
        "sheet 改成 registry 不存在的值（死按钮）",
        "audit-platform/frontend/src/components/workpaper/k5/core/K5TabDetail.vue",
        'sheet="K5-2"', 'sheet="K5-99"', "registry sheets",
    ),
    Mutation(
        "M3", "wiring_integrity",
        "defineEmits 去掉 imported 声明",
        "audit-platform/frontend/src/components/workpaper/k12/core/K12TabDetail.vue",
        "  /** 导入完成 → 父宿主重载 allResponses（父绑定 @imported=\"selfLoad()\"） */\n  (e: 'imported'): void\n}>()",
        "}>()",
        "defineEmits",
    ),
    Mutation(
        "M4", "wiring_integrity",
        "去掉 dropdown 的 import 语句（模板里成未知组件）",
        "audit-platform/frontend/src/components/workpaper/h7/core/H7TabDetailCost.vue",
        "import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'\n",
        "",
        "注册",
    ),
    Mutation(
        "M9", "wiring_integrity",
        "给挂载点改用非路径形态前缀 h5（真实端点是 /api/h5/*，必 404）",
        "audit-platform/frontend/src/components/workpaper/k5/core/K5TabDetail.vue",
        'api-prefix="k5"', 'api-prefix="h5"', "非路径形态",
    ),
    # ── registry 三向锁死（Task 13/17）──────────────────────────────────
    Mutation(
        "M5", "registry_lock",
        "registry 丢掉既有键 F2-14（R4.6 零回归）",
        "audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.ts",
        "'F2-14', 'F2-19'", "'F2-19'",
        # 🔴 expect 必须是**测试名**片段，不能填断言消息里的中文。
        # 本脚本按 fullName 匹配（消息会被 vitest 折叠成 [Array(n)]，见模块 docstring）。
        # 初版这三条填了消息片段（如「丢了既有 sheet 键」），结果 40 个变异里
        # 只有它们判 WRONG-TEST —— 而单独跑时明明是 RED，属判定层缺陷不是守卫缺陷。
        "R4.6 零回归",
    ),
    Mutation(
        "M6", "registry_lock",
        "registry 加未登记键 F2-18（后端白名单不含它）",
        "audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.ts",
        "      'F2-note-listed', 'F2-note-soe',",
        "      'F2-note-listed', 'F2-note-soe', 'F2-18',",
        "R4.6 零回归",
    ),
    Mutation(
        "M8", "registry_lock",
        "抽键不再跟随相对 import（附注键真源丢失 ⇒ 真实键被判不存在）",
        "audit-platform/frontend/src/components/workpaper/shared/__tests__"
        "/cycleImportExportRegistry.spec.ts",
        "    for (const m of src.matchAll(/from\\s+\\.(\\w+)\\s+import/g)) {\n"
        "      for (const k of keysOf(readSrc(`${m[1]}.py`))) keys.add(k)\n    }\n",
        "",
        "落在「catalog ∪ 后端 specs」真源内",
    ),
    # ── 路由可达性 / sheet 参数（Task 17）───────────────────────────────
    Mutation(
        "M10", "prefix_reachability",
        "把 h5 移出 NON_PATH_FORM_PREFIXES（不可达前缀未登记）",
        "backend/tests/test_ie_prefix_reachability.py",
        'NON_PATH_FORM_PREFIXES: frozenset[str] = frozenset({"h5", "n4"})',
        'NON_PATH_FORM_PREFIXES: frozenset[str] = frozenset({"n4"})',
        "test_registry_prefixes_are_reachable_or_declared",
    ),
    Mutation(
        "M11", "prefix_reachability",
        "把其实可达的 k5 塞进不可达清单（清单当垃圾桶）",
        "backend/tests/test_ie_prefix_reachability.py",
        'NON_PATH_FORM_PREFIXES: frozenset[str] = frozenset({"h5", "n4"})',
        'NON_PATH_FORM_PREFIXES: frozenset[str] = frozenset({"h5", "n4", "k5"})',
        "test_declared_non_path_prefixes_really_unreachable",
    ),
    Mutation(
        "M13", "prefix_reachability",
        "把 l4 移出 SHEET_AGNOSTIC_PREFIXES（多 sheet 前缀却不收 sheet 参数）",
        "backend/tests/test_ie_prefix_reachability.py",
        'SHEET_AGNOSTIC_PREFIXES: frozenset[str] = frozenset({"l4"})',
        "SHEET_AGNOSTIC_PREFIXES: frozenset[str] = frozenset()",
        "test_multi_sheet_prefixes_accept_sheet_param",
    ),
    Mutation(
        "M14", "prefix_reachability",
        "把接受 sheet 的 k5 塞进 sheet 无关清单（stale 清单）",
        "backend/tests/test_ie_prefix_reachability.py",
        'SHEET_AGNOSTIC_PREFIXES: frozenset[str] = frozenset({"l4"})',
        'SHEET_AGNOSTIC_PREFIXES: frozenset[str] = frozenset({"l4", "k5"})',
        "test_sheet_agnostic_list_not_stale",
    ),
    Mutation(
        "M16", "prefix_reachability",
        "令多 sheet 前缀抽取恒空（空转自检）",
        "backend/tests/test_ie_prefix_reachability.py",
        "        if len(sheets) > 1:",
        "        if False:  # MUTATION",
        "test_multi_sheet_prefixes_accept_sheet_param",
    ),
    # ── 四场景 UI 单一真源（Task 18）────────────────────────────────────
    Mutation(
        "M17", "scenario_ui",
        "前端抄一段 artifactNote 文案（文案变两份真源）",
        "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue",
        '      <div v-if="scenariosLoading" class="scenario-loading">',
        "      <p>仅含表格骨架与表头，不含任何项目数据</p>\n"
        '      <div v-if="scenariosLoading" class="scenario-loading">',
        "test_frontend_does_not_hardcode_scenario_copy",
    ),
    Mutation(
        "M18", "scenario_ui",
        "删掉卡片块内的 timingNote 渲染（options 回显仍在 ⇒ 全文判据会漏）",
        "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue",
        "              <dt>适用时点</dt>\n              <dd>{{ sc.timingNote }}</dd>\n",
        "",
        "test_frontend_binds_all_three_copy_fields_inside_card",
    ),
    Mutation(
        "M19", "scenario_ui",
        "v-for 改成写死（后端增删场景不同步）",
        "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue",
        'v-for="sc in scenarios"', 'v-if="scenarios.length"',
        "test_frontend_renders_all_four_scenarios_generically",
    ),
    Mutation(
        "M20", "scenario_ui",
        "前端自己判 archived（门控规则第二份）",
        "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue",
        "const isArchived = ref(false)",
        "const isArchived = ref(false)\nconst _st = 'archived'",
        "test_archive_gating_comes_from_backend",
    ),
    Mutation(
        "M21", "scenario_ui",
        "前端接口加后端不下发的字段（模板渲染空白）",
        "audit-platform/frontend/src/components/workpaper/bulk-tab/WpBulkDialog.vue",
        "  disabledReason: string | null\n}",
        "  disabledReason: string | null\n  bogusField: string\n}",
        "test_ui_payload_shape_matches_frontend_interface",
    ),
    Mutation(
        "M22", "scenario_ui",
        "场景端点改成 POST（读取语义丢失）",
        "backend/app/routers/wp_bulk_router.py",
        '@router.get("/scenarios")', '@router.post("/scenarios")',
        "test_scenarios_endpoint_registered_and_readonly",
    ),
    Mutation(
        "M23", "scenario_ui",
        "特征片段阈值调到不可能值（空转自检）",
        "backend/tests/test_bulk_scenario_ui_single_source.py",
        "_MIN_FRAGMENT = 8", "_MIN_FRAGMENT = 9999",
        "test_guard_would_catch_hardcoded_copy",
    ),
    Mutation(
        "M24", "scenario_ui",
        "破坏卡片块截取锚点（空转自检）",
        "backend/tests/test_bulk_scenario_ui_single_source.py",
        "    anchor = src.find('v-for=\"sc in scenarios\"')",
        "    anchor = src.find('v-for=\"NOPE in nothing\"')",
        "test_frontend_binds_all_three_copy_fields_inside_card",
    ),
    Mutation(
        "M25", "scenario_ui",
        "卡片块截取退化成整份文件（判据退回全文匹配）",
        "backend/tests/test_bulk_scenario_ui_single_source.py",
        "    block = src[start:end]",
        "    block = src  # MUTATION",
        "test_card_block_extraction_is_bounded",
    ),
    Mutation(
        "M26", "scenario_ui",
        "disabled 恒 False（归档态也放行导入）",
        "backend/app/routers/wp_bulk_router.py",
        'disabled = bool(is_archived and not spec["archivedAllowed"])',
        "disabled = False  # MUTATION",
        "test_endpoint_disables_import_when_archived_live",
    ),
    Mutation(
        "M28", "scenario_ui",
        "忽略 archivedAllowed（归档后连导出也禁用）",
        "backend/app/routers/wp_bulk_router.py",
        'disabled = bool(is_archived and not spec["archivedAllowed"])',
        "disabled = bool(is_archived)  # MUTATION",
        "test_endpoint_disables_import_when_archived_live",
    ),
    # ── 模板库解引用（Task 19/20）───────────────────────────────────────
    Mutation(
        "M30", "templates_readonly",
        "真改模板库一个字节（内容变、长度不变）",
        "<RUNTIME:TEMPLATE_BYTE>", "", "",
        "test_snapshot_matches_baseline",
        destructive=True,
    ),
    Mutation(
        "M31", "templates_readonly",
        "库里塞一条 file_path 指向模板库的记录",
        "<RUNTIME:DB_TEMPLATE_REF>", "", "",
        "test_no_workpaper_points_into_template_library",
        destructive=True,
    ),
    Mutation(
        "M32", "deref_script",
        "目标路径去掉 cycle 段（偏离既有命名惯例）",
        "backend/scripts/fix/fix_wp_template_deref.py",
        'return f"storage/projects/{project_id}/workpapers/{cycle}/{wp_code}.xlsx"',
        'return f"storage/projects/{project_id}/workpapers/{wp_code}.xlsx"',
        "test_target_rel_matches_existing_convention",
    ),
    Mutation(
        "M33", "deref_script",
        "不再跳过已迁移记录（破幂等）",
        "backend/scripts/fix/fix_wp_template_deref.py",
        "        if not _is_template_ref(raw):\n            skipped_not_template.append(wp_id)",
        "        if False:\n            skipped_not_template.append(wp_id)",
        "test_plan_is_idempotent_for_already_migrated",
    ),
    Mutation(
        "M34", "deref_script",
        "丢掉 project_id 致共享源产出同一目标（跨项目串数据）",
        "backend/scripts/fix/fix_wp_template_deref.py",
        'rel = _target_rel(r["project_id"], cycle, wp_code)',
        'rel = _target_rel("SAME", cycle, wp_code)',
        "test_plan_gives_each_project_its_own_copy",
    ),
    Mutation(
        "M35", "deref_script",
        "破坏性门控放行（--apply 不需确认）",
        "backend/scripts/fix/fix_wp_template_deref.py",
        "    if not args.confirm_destructive:", "    if False:",
        "test_apply_without_confirm_is_refused",
    ),
    Mutation(
        "M36", "deref_script",
        "_safe_name 放水（允许 .. 穿越与非法字符）",
        "backend/scripts/fix/fix_wp_template_deref.py",
        'return bool(value) and value not in {".", ".."} and not (set(value) & bad)',
        "return True",
        "test_safe_name_rejects_traversal_and_illegal_chars",
    ),
    # ── 自证层（Task 4/5）——  Wave 2 建的守卫，Task 21 补齐变异 ──────────
    Mutation(
        "M38", "self_evidence",
        "四态判定退化：needs_self_evidence 恒返 None（自证层静默失效）",
        "backend/app/services/wp_export/self_evidence.py",
        "def needs_self_evidence(",
        "def needs_self_evidence(  # MUTATION-SENTINEL\n    *_mut_args: object, **_mut_kw: object\n) -> None:\n    return None\n\n\ndef _orig_needs_self_evidence(",
        "test_needs_self_evidence_returns",
    ),
    Mutation(
        "M39", "self_evidence",
        "verdict 档横幅不再取 VERDICT_LABELS（文案脱离单一真源）",
        "backend/app/services/wp_export/self_evidence.py",
        "        reason = VERDICT_LABELS.get(verdict)",
        '        reason = "底稿文件不可用"  # MUTATION: 写死中文，绕开真源',
        "test_verdict_banner_contains_blank_template_phrase_and_reason",
    ),
    Mutation(
        "M42", "self_evidence",
        "两档文案合并（entry_not_in_xlsx 与 html_data_absent 给同样建议）",
        "backend/app/services/wp_export/self_evidence.py",
        "        banner = _KIND_LABELS[kind]",
        '        banner = _KIND_LABELS["html_data_absent"]  # MUTATION: 两档合并',
        "test_entry_not_in_xlsx_and_html_absent_labels_differ",
    ),
    # ── 下载清单（Task 6）───────────────────────────────────────────────
    Mutation(
        "M40", "download_manifest",
        "处置建议退回「写死 2 条」（三档同现时有档位无指引）",
        "backend/app/services/wp_download_service.py",
        "    for verdict in sorted(by_verdict):\n"
        "        label = VERDICT_LABELS.get(verdict, verdict)\n"
        "        advice = _VERDICT_ADVICE.get(verdict, _VERDICT_ADVICE_FALLBACK)",
        "    for verdict in list(sorted(by_verdict))[:1]:  # MUTATION: 只给 1 条\n"
        "        label = VERDICT_LABELS.get(verdict, verdict)\n"
        "        advice = _VERDICT_ADVICE.get(verdict, _VERDICT_ADVICE_FALLBACK)",
        "test_advice_lines_match_group_count_for_all_three",
    ),
    Mutation(
        "M43", "download_manifest",
        "清单用裸 verdict 而非中文 label（用户看到 template_fallback 这种英文）",
        "backend/app/services/wp_download_service.py",
        '        lines.append(f"【{label}】共 {len(items)} 份")',
        '        lines.append(f"【{verdict}】共 {len(items)} 份")  # MUTATION: 裸英文',
        "test_uses_verdict_labels_not_raw_verdict",
    ),
    Mutation(
        "M44", "download_manifest",
        "_VERDICT_ADVICE 摘掉一个档位（缺键退到兜底话术）",
        "backend/app/services/wp_download_service.py",
        '    "empty": (',
        '    "_mut_empty": (',
        "test_advice_covers_all_non_file_verdicts",
    ),
    # ── 批量可见集过滤粒度（Task 24）──────────────────────────────────────
    # 本 spec 抓到的**最严重**一个「四层全绿但产物是空壳」缺陷：
    # 批量导出把 sheet_code 传给 gate 的 requested_sheet_key，触发 sheet 成员校验，
    # 而候选集（ProcedureRowTask.sheet_key）只覆盖 19/2802 个 wp_index（0.7%）
    # ⇒ 99.3% 底稿被判 sheet_unmapped 静默剔除，且不泄露存在性连 skipped 都不进
    # ⇒ 用户拿到只含报表/附注的空壳 ZIP，无任何提示。
    # 实测三个真实项目：1025→0、1017→0、340→0 份底稿进 ZIP。修后 D 循环 0→7。
    Mutation(
        "M65", "bulk_visible_granularity",
        "批量可见集过滤把 requested_sheet_key 传回去（回退空壳 ZIP 缺陷）",
        "backend/app/services/wp_visibility/entry_integration.py",
        "            # 有意不传 requested_sheet_key —— 见 docstring\n",
        "            requested_sheet_key=sheet_code,\n",
        "test_bulk_filter_does_not_pass_sheet_key",
    ),
    Mutation(
        "M67", "bulk_visible_granularity",
        "删掉「0.7% 覆盖率」说明（回退后无信号，只能靠注释拦）",
        "backend/app/services/wp_visibility/entry_integration.py",
        "**只覆盖 19 / 2802 个 wp_index（0.7%）**",
        "覆盖率有限",
        "test_sheet_key_omission_is_documented",
    ),
    # ── 真实库验收脚本（Task 23）──────────────────────────────────────────
    # 这两条守的是**验收脚本自己**不许放水：
    #   · 找不到合法对象时必须报「无法验收」而不是拿 fixture 凑
    #   · 产物找回判据必须下钻到叶子标量（拿容器 str() 会产生假红）
    # 它们无对应 pytest 守卫文件（验收脚本本身就是可执行判据），
    # 故 guard 指向 guard_coverage —— 由元守卫保证脚本存在且被 CI 提及。
    Mutation(
        "M60", "guard_coverage",
        "验收脚本：挑选条件收紧到不可能，验证「无法验收」路径而非 fixture 冒充",
        "backend/scripts/diagnose/verify_ie_lifecycle_live.py",
        '        if int(r["cr_nonblank"] or 0) == 0:',
        "        if True:  # MUTATION: 全部排除",
        # 该变异的预期效果是脚本自身 exit 2，不是 pytest 打红；
        # 由 `test_live_verify_refuses_fixture_fallback` 断言其行为。
        "test_live_verify_refuses_fixture_fallback",
    ),
    Mutation(
        "M62", "guard_coverage",
        "验收脚本：产物找回探针改回容器 str()（重现假红）",
        "backend/scripts/diagnose/verify_ie_lifecycle_live.py",
        "            probe = _leaf_probe(p.obj)[:24]",
        "            probe = str(next(iter(p.obj.values()), ''))[:24].strip()",
        "test_live_verify_probe_drills_to_leaf",
    ),
    # ── 元守卫：CI 接线（Task 22）─────────────────────────────────────────
    # 往 4300+ 行的 workflow 里加 job 有三种静默失效：yaml 语法错让**整个**
    # workflow 停摆、job 名重复后者静默覆盖前者、引用路径写错但 step 被消音。
    Mutation(
        "M50", "ci_wiring",
        "CI 漏挂一个后端守卫（该文件在 CI 里全体缺席）",
        ".github/workflows/governance-checks.yml",
        "            backend/tests/services/test_entry_payload_reader.py \\\n",
        "",
        "test_all_backend_guard_files_are_mounted",
    ),
    Mutation(
        "M51", "ci_wiring",
        "CI job 名与既有 job 重名（后者静默覆盖前者）",
        ".github/workflows/governance-checks.yml",
        "  wp-import-export-lifecycle-frontend:",
        "  sql-column-contract:",
        "test_no_duplicate_job_names",
    ),
    Mutation(
        "M52", "ci_wiring",
        "CI 引用不存在的测试文件（pytest 报 not found，若被消音则彻底静默）",
        ".github/workflows/governance-checks.yml",
        "backend/tests/test_wp_templates_readonly.py",
        "backend/tests/test_wp_templates_readonly_NOPE.py",
        "test_backend_job_references_existing_test_files",
    ),
    Mutation(
        "M53", "ci_wiring",
        "幂等脚本在 CI 里改成 --apply（流水线改版本库产物）",
        ".github/workflows/governance-checks.yml",
        "python backend/scripts/fix/fix_acnr_catalog_ie_gap.py --check",
        "python backend/scripts/fix/fix_acnr_catalog_ie_gap.py --apply",
        "test_idempotent_scripts_use_check_only",
    ),
    Mutation(
        "M54", "ci_wiring",
        "严格 step 加 `|| true` 消音（失败伪装成成功）",
        ".github/workflows/governance-checks.yml",
        # 锚点取「产物自证」那个 step 的 run 块尾行 —— 元守卫 step 后来改成了
        # 多行 `run: |` 块，原先按单行匹配的锚点已失效（M54 曾因此 ANCHOR-MISS）。
        "            backend/tests/services/test_wp_download_manifest.py",
        "            backend/tests/services/test_wp_download_manifest.py || true",
        "test_strict_steps_are_not_silenced",
    ),
    Mutation(
        "M55", "ci_wiring",
        "孤儿基线去掉 continue-on-error（该 job 会长期红，红久了没人看）",
        ".github/workflows/governance-checks.yml",
        "      - name: 孤儿基线（含有意留红的占位断言，报告模式）\n"
        "        continue-on-error: true\n",
        "      - name: 孤儿基线（含有意留红的占位断言，报告模式）\n",
        "test_orphan_baseline_is_report_mode",
    ),
    # ── 元守卫：五类覆盖（Task 22）────────────────────────────────────────
    Mutation(
        "M56", "guard_coverage",
        "五类里删掉一整类（该类不变量整体失守而其余守卫照样全绿）",
        "backend/tests/test_ie_lifecycle_guard_coverage.py",
        '    "模板库只读": ("templates_readonly", "deref_script"),\n',
        "",
        "test_all_five_invariant_classes_declared",
    ),
    Mutation(
        "M57", "guard_coverage",
        "某类的守卫键指向不存在的守卫文件",
        "backend/tests/test_ie_lifecycle_guard_coverage.py",
        '    "产物自证": ("self_evidence", "download_manifest"),',
        '    "产物自证": ("self_evidence", "download_manifest", "nope_guard"),',
        "test_each_class_has_at_least_one_guard",
    ),
    # ── 数据源接通（Task 7/8）─────────────────────────────────────────────
    # 🔴 这三条是 Task 22 的元守卫逼出来的：初版把 entry_payload /
    #    export_entry_sheet 两个守卫**整类**登记进 UNCOVERED_RATIONALE，
    #    等于「数据源接通」这一类不变量从未被证明有效。
    #    元守卫 `test_uncovered_rationale_does_not_hide_whole_class` 打红后补齐。
    Mutation(
        "M47", "entry_payload",
        "JSON 解析失败不再降级 plain_text 而是丢弃（录入内容静默消失）",
        "backend/app/services/wp_export/entry_payload_reader.py",
        # 锚点必须带上后续的 `if isinstance(data, list):` —— `_classify` 里有
        # 三处结构相同的 except 块，只取 except 两行会命中 2 次判 ANCHOR-MISS。
        '            return "plain_text", None, None, True\n'
        "        if isinstance(data, list):",
        '            return "json_array", [], None, True  # MUTATION: 丢内容\n'
        "        if isinstance(data, list):",
        "test_broken_json_degrades_not_raises",
    ),
    Mutation(
        "M48", "entry_payload",
        "个体闸失效：超长载荷不截断（86 万字符直接写进产物）",
        "backend/app/services/wp_export/entry_payload_reader.py",
        "        truncated = len(raw) > max_one_chars",
        "        truncated = False  # MUTATION: 个体闸失效",
        "test_one_chars_cap_truncates_and_flags",
    ),
    Mutation(
        "M49", "export_entry_sheet",
        "录入 sheet 不再追加（导出物缺录入内容且无提示）",
        "backend/app/services/wp_export/entry_sheet_writer.py",
        "def write_entry_sheet(",
        "def write_entry_sheet(  # MUTATION-SENTINEL\n    *_mut_a: object, **_mut_k: object\n) -> None:\n    return None\n\n\ndef _orig_write_entry_sheet(",
        "test_checklist_only_workpaper_产物含其内容",
    ),
    # ── 端点清单台账（Task 9）——  防「凭旧数重新发起改动」────────────────
    Mutation(
        "M41", "route_inventory",
        "模块数改回立项旧数 102（实测 99）",
        "backend/tests/test_ie_route_inventory.py",
        "_BASE_IE_MODULES = 99            # 立项: 102",
        "_BASE_IE_MODULES = 102           # MUTATION",
        "test_ie_module_count",
    ),
    Mutation(
        "M45", "route_inventory",
        "三态端点总数改回立项错数 314（实测 308）",
        "backend/tests/test_ie_route_inventory.py",
        "_BASE_THREE_STATE_ROUTES = 308   # 立项: 314",
        "_BASE_THREE_STATE_ROUTES = 314   # MUTATION",
        "test_baseline_numbers_reject_stale_figures",
    ),
    Mutation(
        "M46", "route_inventory",
        "三态齐全前缀数改回立项的 36（实测 100，曾据此漏掉 64 个前缀）",
        "backend/tests/test_ie_route_inventory.py",
        "_BASE_FULL3_PREFIXES = 100       # 立项: 36 / 我的第 1 轮: 81 / 第 2 轮: 80",
        "_BASE_FULL3_PREFIXES = 36        # MUTATION",
        "test_baseline_numbers_reject_stale_figures",
    ),
)


#: 🔴 无变异覆盖的守卫 —— **必须逐条写明理由**（R7.3 的「缺口显式登记」）。
#:
#: 登记不是免责：写在这里意味着「已评估过、当前有意不补」，而不是「忘了」。
#: `--list` 会把未登记的缺口单独打出来。
UNCOVERED_RATIONALE: dict[str, str] = {
    # 🔴 `entry_payload` / `export_entry_sheet` 已于 Task 22 补上变异
    #    （M47/M48/M49），从本表移除 —— 保留在这里会被
    #    `_coverage()` 的 `stale_rationale` 自检打红。
    #
    #    移除原因值得记：初版把这两个守卫**整类**登记豁免，而它们正好是
    #    「数据源接通」这一类不变量的全部守卫 ⇒ 等于整类从未被证明有效。
    #    元守卫 `test_uncovered_rationale_does_not_hide_whole_class` 把它抓了出来。
    #    教训：缺口登记是给个别守卫开的口子，不能覆盖某一类的全部守卫。
    "scenario_registry": (
        "28 条里大部分是 SCENARIOS 常量的结构断言（端点 ⊆ app.routes、"
        "场景②③ import_endpoint 必须相同等）。改常量即多条同时红，"
        "而端点存在性已由 prefix_reachability 的 M10/M11 覆盖同类判据。"
    ),
    "bulk_mode_mismatch": (
        "mode 错用校验（16 条）已在 Task 11 用真实 ZIP 走过 fail-closed 路径；"
        "其核心分支（校验器自身异常也不放行）用变异会改到 except 块，"
        "等价于删掉整个校验，红的是全部 16 条而非某一条。"
    ),
    "archive_gating": (
        "15 条守的是 `_BLOCKED_STATUSES` 含 archived + 导入侧真消费 classify()。"
        "该常量的变异效果已由 scenario_ui 的 M26/M28（归档态可用性）等价覆盖 —— "
        "两者共用同一门控真源。"
    ),
    "orphan_baseline": (
        "26 条里有 1 条是**有意保持红色**的占位断言（剩 6 个孤儿各有实证阻塞），"
        "基线不干净会让本脚本对该文件的全部变异结论不可信（脚本会打印"
        "『基线不干净』告警）。待 Task 17 遗留 6 个孤儿处置完毕后再补变异。"
    ),
    "bulk_dialog": (
        "13 条是组件挂载与渲染管线断言，其文案单一真源判据已由 scenario_ui "
        "的 M17~M25（11 个变异）从后端侧覆盖；组件侧变异需改 .vue 模板，"
        "与 M18/M19 重复。"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 文件读写（CRLF 归一）
# ═══════════════════════════════════════════════════════════════════════════


def _read(path: Path) -> tuple[str, str]:
    """读文件 → (LF 归一文本, 原始换行风格)。

    🔴 本仓库是 CRLF。含 `\\n` 的跨行锚点若直接对原文匹配必然 ANCHOR-MISS
    —— 故内存中统一按 LF 处理，落盘时还原原始风格。
    """
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _write(path: Path, text_lf: str, newline: str) -> None:
    out = text_lf.replace("\n", newline) if newline == "\r\n" else text_lf
    path.write_bytes(out.encode("utf-8"))


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 测试执行
# ═══════════════════════════════════════════════════════════════════════════


def _run_guard(guard_key: str) -> list[str]:
    """跑单个守卫文件，返回**失败测试名**列表。

    🔴 按测试名匹配而非消息内容：pytest/vitest 都会折叠长 diff
    （vitest 把数组显示成 `[Array(n)]`），消息匹配会把 RED 误判成 WRONG-TEST。
    """
    rel = GUARD_FILES[guard_key]
    if guard_key in FRONTEND_GUARD_KEYS:
        spec_rel = rel.replace("audit-platform/frontend/", "")
        res_file = _REPO / f".mut_vitest_{guard_key}.json"
        res_file.unlink(missing_ok=True)
        subprocess.run(
            ["cmd", "/c",
             f"npx vitest run {spec_rel} --reporter=json "
             f"--outputFile={res_file.as_posix()} >nul 2>&1"],
            cwd=str(_FRONTEND), check=False,
        )
        if not res_file.exists():
            return ["<vitest 未产出结果文件>"]
        try:
            data = json.loads(res_file.read_text(encoding="utf-8"))
        finally:
            res_file.unlink(missing_ok=True)
        return [
            (a.get("fullName") or a.get("title") or "?")
            for tr in data.get("testResults", [])
            for a in tr.get("assertionResults", [])
            if a.get("status") == "failed"
        ]

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", rel, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(_REPO), check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        # 🔴 与 `tests/scripts/test_wp_template_deref.py::_run` 同一个 Windows 编码坑：
        # `capture_output=True` ⇒ 子进程 stdout 是管道，Windows 上 CPython 按 locale
        # 编码（cp936/GBK）写，父进程这边的 `encoding="utf-8"` 只覆盖解码侧。
        # 此处目前尚不假判（上面按 ASCII 的测试名匹配，乱码只糊中文消息不糊
        # `FAILED …::name`），但一旦有人改成按消息内容匹配就会静默失准 ——
        # 变异检验是判 RED/GREEN 的仲裁者，先把编码钉死。
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    names = re.findall(r"FAILED\s+\S+::([\w\[\]\-]+)", out)
    if not names and " failed" in out:
        names = ["<有失败但未解析出名字>"]
    return names


# ═══════════════════════════════════════════════════════════════════════════
# 破坏性变异的运行时钩子
# ═══════════════════════════════════════════════════════════════════════════


def _mutate_template_byte() -> tuple[Path, bytes, str]:
    """改模板库一个字节（长度不变）。返回 (路径, 原字节, 原 sha256)。"""
    tpl = _REPO / "backend" / "wp_templates"
    target = next(
        p for p in sorted(tpl.rglob("*.xlsx")) if not p.name.startswith("~$")
    )
    orig = target.read_bytes()
    sha = hashlib.sha256(orig).hexdigest()
    data = bytearray(orig)
    data[len(data) // 2] ^= 0xFF
    target.write_bytes(bytes(data))
    return target, orig, sha


def _db_exec(sql: str, params: dict | None = None) -> list[tuple]:
    """独立 engine 执行一次 SQL，用完 dispose。

    🔴 绝不用 `app.core.database.engine` 的共享连接池：本项目实测过
    两次 `asyncio.run` 复用它会在第二次报 `NoneType has no attribute send`，
    导致「改了库但复原失败」。
    """
    import asyncio

    async def _go() -> list[tuple]:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.core.config import settings

        eng = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            async with eng.begin() as conn:
                res = await conn.execute(text(sql), params or {})
                try:
                    return [tuple(r) for r in res.all()]
                except Exception:
                    return []
        finally:
            await eng.dispose()

    if str(_REPO / "backend") not in sys.path:
        sys.path.insert(0, str(_REPO / "backend"))
    return asyncio.run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# 单个变异
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Verdict:
    mid: str
    guard: str
    desc: str
    state: str
    failed: list[str] = field(default_factory=list)
    note: str = ""


def _judge(mut: Mutation, failed: list[str]) -> tuple[str, str]:
    if not failed:
        return "GREEN", "变异后仍全绿 ⇒ 该判据形同虚设"
    if any(mut.expect in f for f in failed):
        return "RED", f"命中预期 {mut.expect}"
    return "WRONG-TEST", f"打红了但不含预期 {mut.expect}"


def _self_check_expect_fields() -> list[str]:
    """自检：`expect` 必须能在对应守卫文件的**测试名**里找到。

    🔴 这条防的是本脚本自己的判定缺陷（2026-08-12 真实踩到）：
    `expect` 若填成断言消息里的中文（如「丢了既有 sheet 键」），判定按 fullName
    匹配就永远命中不了 ⇒ 明明打红了正确的守卫，却被判 WRONG-TEST。

    单独跑那个变异时能看出不对，但混在 40 个里只会显示 3 个 WRONG-TEST，
    很容易被当成「守卫有问题」而去改守卫 —— 改错方向的代价比漏判更大。
    """
    problems: list[str] = []
    for mut in MUTATIONS:
        guard_path = _REPO / GUARD_FILES[mut.guard]
        if not guard_path.is_file():
            problems.append(f"{mut.mid}: 守卫文件不存在 {mut.guard}")
            continue
        src = guard_path.read_text(encoding="utf-8")
        if mut.guard in FRONTEND_GUARD_KEYS:
            names = re.findall(r"\b(?:it|test)\(\s*['\"`]([^'\"`]+)", src)
        else:
            names = re.findall(r"^\s*(?:async )?def (test_\w+)", src, re.M)
        if not any(mut.expect in n for n in names):
            problems.append(
                f"{mut.mid}: expect={mut.expect!r} 不在 {mut.guard} 的任何测试名里"
                " ⇒ 该变异永远判不出 RED（疑似把断言消息当成了测试名）"
            )
    return problems


def _run_source_mutation(mut: Mutation) -> Verdict:
    path = _REPO / mut.target
    if not path.is_file():
        return Verdict(mut.mid, mut.guard, mut.desc, "ANCHOR-MISS",
                       note=f"目标文件不存在: {mut.target}")

    text_lf, newline = _read(path)
    hits = text_lf.count(mut.old)
    if hits != 1:
        return Verdict(mut.mid, mut.guard, mut.desc, "ANCHOR-MISS",
                       note=f"锚点命中 {hits} 次（需恰好 1）")

    bak = path.with_suffix(path.suffix + BAK_SUFFIX)
    bak.write_bytes(path.read_bytes())
    md5_before = _md5(path)
    try:
        _write(path, text_lf.replace(mut.old, mut.new, 1), newline)
        failed = _run_guard(mut.guard)
        state, note = _judge(mut, failed)
        return Verdict(mut.mid, mut.guard, mut.desc, state, failed, note)
    finally:
        path.write_bytes(bak.read_bytes())
        bak.unlink(missing_ok=True)
        md5_after = _md5(path)
        if md5_after != md5_before:
            raise SystemExit(
                f"🔴 {mut.mid} 还原失败：{mut.target} 的 md5 变了 "
                f"({md5_before} → {md5_after})。请 git checkout 该文件。"
            )


def _run_destructive_mutation(mut: Mutation) -> Verdict:
    if mut.target == "<RUNTIME:TEMPLATE_BYTE>":
        target, orig, sha = _mutate_template_byte()
        try:
            failed = _run_guard(mut.guard)
            state, note = _judge(mut, failed)
            return Verdict(mut.mid, mut.guard, mut.desc, state, failed, note)
        finally:
            target.write_bytes(orig)
            got = hashlib.sha256(target.read_bytes()).hexdigest()
            if got != sha:
                raise SystemExit(
                    f"🔴 {mut.mid} 模板库还原失败：{target} sha256 {sha} → {got}"
                )

    if mut.target == "<RUNTIME:DB_TEMPLATE_REF>":
        rows = _db_exec(
            "SELECT id::text, file_path FROM working_paper "
            "WHERE file_path ~ '^storage/projects/[^/]+/workpapers/[A-Z]/' LIMIT 1"
        )
        if not rows:
            return Verdict(mut.mid, mut.guard, mut.desc, "SKIP",
                           note="库里没有可用样本（迁移未执行？）")
        wp_id, old_path = rows[0][0], rows[0][1]
        try:
            _db_exec(
                "UPDATE working_paper SET file_path = :p WHERE id = CAST(:i AS uuid)",
                {"p": "wp_templates/__MUTATION__.xlsx", "i": wp_id},
            )
            failed = _run_guard(mut.guard)
            state, note = _judge(mut, failed)
            return Verdict(mut.mid, mut.guard, mut.desc, state, failed, note)
        finally:
            _db_exec(
                "UPDATE working_paper SET file_path = :p WHERE id = CAST(:i AS uuid)",
                {"p": old_path, "i": wp_id},
            )
            left = _db_exec(
                "SELECT count(*) FROM working_paper WHERE file_path LIKE '%wp_templates%'"
            )
            n = int(left[0][0]) if left else -1
            if n != 0:
                raise SystemExit(
                    f"🔴 {mut.mid} 库未还原：仍有 {n} 条指向模板库（wp_id={wp_id}，"
                    f"应为 {old_path}）"
                )

    return Verdict(mut.mid, mut.guard, mut.desc, "ANCHOR-MISS",
                   note=f"未知运行时钩子: {mut.target}")


# ═══════════════════════════════════════════════════════════════════════════
# 覆盖率
# ═══════════════════════════════════════════════════════════════════════════


def _assertion_count(guard_key: str) -> int:
    path = _REPO / GUARD_FILES[guard_key]
    if not path.is_file():
        return 0
    src = path.read_text(encoding="utf-8")
    if guard_key in FRONTEND_GUARD_KEYS:
        return len(re.findall(r"\b(?:it|test)\(\s*['\"`]", src))
    return len(re.findall(r"^\s*(?:async )?def test_\w+", src, re.M))


def _coverage() -> dict[str, object]:
    per_guard: dict[str, dict[str, object]] = {}
    for key in GUARD_FILES:
        muts = [m.mid for m in MUTATIONS if m.guard == key]
        n = _assertion_count(key)
        per_guard[key] = {
            "assertions": n,
            "mutations": len(muts),
            "mids": muts,
            "uncovered": max(0, n - len(muts)),
        }
    total_a = sum(int(v["assertions"]) for v in per_guard.values())  # type: ignore[arg-type]
    total_m = len(MUTATIONS)

    zero = sorted(k for k, v in per_guard.items() if v["mutations"] == 0)
    # 🔴 缺口分两类，混在一起就等于没登记：
    #    registered   —— 已在 UNCOVERED_RATIONALE 写明理由（有意不补）
    #    unregistered —— 既没变异也没理由（真缺口，必须打红）
    registered = [k for k in zero if k in UNCOVERED_RATIONALE]
    unregistered = [k for k in zero if k not in UNCOVERED_RATIONALE]

    # 反向自检：理由表里不该出现「其实已有变异」的守卫，否则理由 stale
    stale_rationale = sorted(
        k for k in UNCOVERED_RATIONALE if per_guard.get(k, {}).get("mutations")
    )
    # 理由表里也不该出现不存在的守卫键（改名后残留）
    unknown_rationale = sorted(set(UNCOVERED_RATIONALE) - set(GUARD_FILES))

    covered_assertions = sum(
        int(v["assertions"])  # type: ignore[arg-type]
        for k, v in per_guard.items()
        if v["mutations"]
    )

    return {
        "per_guard": per_guard,
        "total_assertions": total_a,
        "total_mutations": total_m,
        "coverage_pct": round(total_m / total_a * 100, 1) if total_a else 0.0,
        # 更有意义的口径：**有变异覆盖的守卫**占全部判据的比例
        "guarded_assertion_pct": (
            round(covered_assertions / total_a * 100, 1) if total_a else 0.0
        ),
        "guards_without_mutation": zero,
        "uncovered_registered": registered,
        "uncovered_unregistered": unregistered,
        "stale_rationale": stale_rationale,
        "unknown_rationale": unknown_rationale,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def _restore_all() -> int:
    n = 0
    for bak in _REPO.rglob(f"*{BAK_SUFFIX}"):
        orig = bak.with_suffix("")
        if orig.suffix == "":  # 防误删（*.mutbak 必须对应一个真实文件）
            continue
        orig.write_bytes(bak.read_bytes())
        bak.unlink()
        print(f"已还原 {orig.relative_to(_REPO)}")
        n += 1
    print(f"共还原 {n} 个文件")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="导入导出守卫变异检验")
    ap.add_argument("--list", action="store_true", help="列出变异与覆盖率，不执行")
    ap.add_argument("--run", action="store_true", help="执行变异检验")
    ap.add_argument("--restore", action="store_true", help="还原残留的 .mutbak（被强杀后收尾）")
    ap.add_argument("--guard", help="只跑指定守卫的变异（GUARD_FILES 的键）")
    ap.add_argument("--mid", help="只跑指定编号的变异（如 M17）")
    ap.add_argument(
        "--include-destructive",
        action="store_true",
        help="包含触碰真实模板库/数据库的变异（默认跳过）",
    )
    ap.add_argument("--out", help="报告落点目录（默认脚本同级 _mutation_reports/）")
    args = ap.parse_args()

    if args.restore:
        return _restore_all()

    cov = _coverage()

    if args.list or not args.run:
        print(
            f"变异 {cov['total_mutations']} 个 / 判据 {cov['total_assertions']} 条"
            f" ⇒ 变异密度 {cov['coverage_pct']}%"
        )
        print(
            f"有变异覆盖的守卫占判据 {cov['guarded_assertion_pct']}%"
            f"（{len(GUARD_FILES) - len(cov['guards_without_mutation'])}"  # type: ignore[arg-type]
            f"/{len(GUARD_FILES)} 个守卫文件）"
        )
        print()
        for key, v in cov["per_guard"].items():  # type: ignore[union-attr]
            if v["mutations"]:
                flag = "  "
            elif key in UNCOVERED_RATIONALE:
                flag = "登"  # 已登记理由
            else:
                flag = "!!"  # 未登记缺口
            print(f" {flag} {key:<22} 判据 {v['assertions']:>3}  变异 {v['mutations']:>2}"
                  f"  {','.join(v['mids'])}")  # type: ignore[arg-type]

        if cov["uncovered_registered"]:
            print()
            print("已登记的缺口（有意不补，理由见 UNCOVERED_RATIONALE）：")
            for k in cov["uncovered_registered"]:  # type: ignore[union-attr]
                reason = UNCOVERED_RATIONALE[k].split("。")[0]
                print(f"     {k:<22} {reason}。")

        problems: list[str] = []
        if cov["uncovered_unregistered"]:
            problems.append(
                "🔴 未登记的缺口（既无变异也无理由）："
                + ", ".join(cov["uncovered_unregistered"])  # type: ignore[arg-type]
            )
        if cov["stale_rationale"]:
            problems.append(
                "🔴 理由表 stale（这些守卫其实已有变异，应从 UNCOVERED_RATIONALE 移除）："
                + ", ".join(cov["stale_rationale"])  # type: ignore[arg-type]
            )
        if cov["unknown_rationale"]:
            problems.append(
                "🔴 理由表含未知守卫键（改名残留）："
                + ", ".join(cov["unknown_rationale"])  # type: ignore[arg-type]
            )
        expect_problems = _self_check_expect_fields()
        if expect_problems:
            problems.append(
                "🔴 expect 字段自检失败（这些变异永远判不出 RED）：\n"
                + "\n".join(f"     {p}" for p in expect_problems)
            )

        if problems:
            print()
            for p in problems:
                print(p)

        if not args.run:
            return 1 if problems else 0

    selected = [
        m for m in MUTATIONS
        if (not args.guard or m.guard == args.guard)
        and (not args.mid or m.mid == args.mid)
        and (args.include_destructive or not m.destructive)
    ]
    skipped_destructive = [
        m.mid for m in MUTATIONS if m.destructive and not args.include_destructive
    ]

    print(f"\n执行 {len(selected)} 个变异"
          + (f"（跳过破坏性 {len(skipped_destructive)} 个: {skipped_destructive}）"
             if skipped_destructive else ""))

    baseline: dict[str, list[str]] = {}
    for key in sorted({m.guard for m in selected}):
        baseline[key] = _run_guard(key)
        if baseline[key]:
            print(f"  !! 基线不干净 {key}: {baseline[key]}"
                  " ⇒ 该守卫的变异结论不可信")

    verdicts: list[Verdict] = []
    for mut in selected:
        print(f"  [{mut.mid}] {mut.desc[:52]} …", end=" ", flush=True)
        v = (
            _run_destructive_mutation(mut)
            if mut.destructive
            else _run_source_mutation(mut)
        )
        # 扣掉基线本来就红的项，避免把既有失败算进变异效果
        base = set(baseline.get(mut.guard, []))
        v.failed = [f for f in v.failed if f not in base]
        if base and v.state == "RED" and not v.failed:
            v.state, v.note = "WRONG-TEST", "红全部来自基线，变异本身未触发"
        verdicts.append(v)
        print(v.state)

    tally = {}
    for v in verdicts:
        tally[v.state] = tally.get(v.state, 0) + 1

    report = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "coverage": cov,
        "tally": tally,
        "skipped_destructive": skipped_destructive,
        "baseline_dirty": {k: v for k, v in baseline.items() if v},
        "verdicts": [
            {
                "mid": v.mid, "guard": v.guard, "desc": v.desc,
                "state": v.state, "failed": v.failed, "note": v.note,
            }
            for v in verdicts
        ],
    }

    out_dir = Path(args.out) if args.out else _THIS.parent / "_mutation_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"mutation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n判定汇总: {tally}")
    print(f"报告: {out}")

    bad = [v for v in verdicts if v.state in {"GREEN", "WRONG-TEST", "ANCHOR-MISS"}]
    if bad:
        print("\n需处理:")
        for v in bad:
            print(f"  {v.state:<12} {v.mid}  {v.desc[:50]}")
            print(f"               {v.note}")
    # 🔴 退出码只作 CI 信号；判定一律看报告里的 state（memory 铁律）
    return 1 if any(v.state == "GREEN" for v in verdicts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
