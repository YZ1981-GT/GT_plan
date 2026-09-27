"""逐 entry 契约的**交付登记表** —— 从 `adapters/registry.py` 抽出的伴生模块。

═══ 为什么抽出来 ═══

这张表是**纯数据台账**：每交付一份逐 entry 契约就追加一条，条目里带长篇 `reason`
（记录该 entry 的形态差异、踩过的坑、与前序 entry 不同之处），单条 40~60 行。

它在 `registry.py` 里长到了 **1172 行 / 占该文件 47%**，并且**按设计还会继续长**
（H 循环剩 5 条、I~S 各循环未开始）。行数门禁 `check_file_size.py` 因此在两次连续
提交里各拦了一次；继续上调 whitelist 基线等于「预留膨胀空间」，正是白名单注释
第 7 行明令禁止的做法。

⇒ 抽成伴生模块：`registry.py` 保留全部**行为**（matcher / registration / report），
台账数据独立成文件。`registry.py` **re-export** 本符号，所有既有 import 路径
（`from ...adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS`、
`RG.DELIVERED_PER_ENTRY_CONTRACTS`）**一字不用改**。

🔴 追加新条目请改**本文件**，不要改回 `registry.py`。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

__all__ = ["DELIVERED_PER_ENTRY_CONTRACTS"]


# ═══════════════════════════════════════════════════════════════════════════
# per-entry 生产契约交付登记（Task 40 追加；只加不动）
# ═══════════════════════════════════════════════════════════════════════════
#
# Task 13 交付时 `backend/data/workpaper_sync_contracts/` 里没有任何生产契约，它的
# `test_contract_directory_holds_no_production_contract_yet` 把这个事实写成**绝对空清册**。
# Tasks 40~57 / 62~64 逐 entry 发布契约后那条清册必然过期，但**不能**把判据删掉 ——
# 删掉之后「谁能往契约目录里放生产契约」就无人把守了。
#
# 做法与 :data:`DELIVERED_ENGINE_ADAPTERS` / `merge.RETIRED_DEFERRALS` 同款：把「已发布」
# 做成一张登记表，边界判据改为与 `contracts.available_contract_ids()` **双向等值**：
#
# * 出现未登记的生产契约 ⇒ 打红（有人绕过 pilot 门放了个契约）；
# * 登记了却没有对应文件 ⇒ 打红（登记表与事实脱钩）；
# * 登记的 `entry_id` 不在 source-backed manifest 里 ⇒ 打红（契约指向已消失的入口）。

#: **已发布**的 per-entry 生产契约。每条写明由哪个任务发布、对应哪个 manifest entry、
#: 权威模板载体，以及"为什么这次发布没有跳过 finalize 顺序"。
DELIVERED_PER_ENTRY_CONTRACTS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "contract_id": "b60.hour_budget",
        "provider_module": "app.services.workpaper_sync.pilot_simple_checklist",
        "delivered_by_task": "40",
        "pilot_class": "simple_checklist",
        "entry_id": "xlsx/b60/gt-b60-bundle",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "B/B60-1 审计项目工时预算与控制表.xlsx",
        "adapter_registered": False,
        "reason": (
            "Task 40 冻结 simple_checklist pilot 的唯一合格 entry（174 个候选里唯一"
            "independent 且 wp_code 与 wp_templates/_index.json 精确相等、零回退的那个），"
            "逐 sheet 读权威模板后人工审核并发布 approved authority model / per-entry "
            "contract / non-null bundle。`adapter_registered=False` 是**顺序**而不是遗漏："
            "任务正文要求「经 Task 36 finalize Task 17 candidate 为 published "
            "representation 后，方可注册 adapter / 接宿主 / 启用 capability」。"
            "Task 75 已交付该 finalize 缺的公共观测器（`published_identity_observer`）并把 "
            "`resolve_published_frozen_definitions()` 改成真实现；今天仍未注册的原因换成了"
            "**供给**：`working_paper_sync_definition_bundle` / "
            "`working_paper_content_representation` / `working_paper_sync_entry_state` 三表"
            "实测 0 行。其中 approved bundle 与 candidate 受控 attach 是 Task 76 的交付；"
            "**published representation 不是** —— 它的生产者是 "
            "`ContentMutationService.commit(...)`（首版 content version）与 Task 36 / Task 77 "
            "的 finalize gate（同 content version 的新代际）。"
            "（Task 77 更正：首版此处把 representation 一并归给 Task 76，属误记。）"
            "`register_from_manifest()` 对本 entry 给出的显式原因即"
            "「还没有 current published representation」。"
            "契约孤儿由 `RegistryReport.contract_files_without_adapter` 持续可见。"
        ),
    },
    # ── Task 41 追加（只加不动；本条起至 tuple 结束是 Task 41 的字节区间）────────
    {
        "contract_id": "d2.receivable_detail",
        "provider_module": "app.services.workpaper_sync.pilot_d2_large_json",
        "delivered_by_task": "41",
        "pilot_class": "d2_large_json",
        "entry_id": "xlsx/gt-d2-accounts-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 41 冻结 d2_large_json pilot 的唯一候选 entry（`assess_pilot_classes()` 实测 "
            "1 个候选、bidirectional 0 个），逐 sheet 读权威模板的 11 张 sheet 后只声明受管 "
            "sheet `明细表D2-2`，按 stable field + row UUID 把真实 906,239 字节的 HTML store "
            "载荷（`checklist_responses.item_id='D2-detail-rows'`，1260 行 × 39 列）拆成 "
            "49,140 个字段，禁止把整 JSON 当一个字段（AC 6.9 / 6.12）。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`d2.receivable_detail` —— 该 entry 的 manifest 已由 reviewed overlay 裁决为 "
            "`bidirectional`（`adapter_id` 同步写回），approved bundle / current published "
            "representation / entry_state 三件供给齐备，观测器真读出 frozen identity 后走完 "
            "`build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation），"
            "不是本登记表自己宣称的。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE（`RegistryReport.contract_files_without_adapter` "
            "对本 entry 已不再登记为孤儿）。"
        ),
    },
    # ── Task 42 追加（只加不动；本条起至 tuple 结束是 Task 42 的字节区间）────────
    {
        "contract_id": "h1.disposal_check",
        "provider_module": "app.services.workpaper_sync.pilot_h1_grouped_dynamic",
        "delivered_by_task": "42",
        "pilot_class": "h1_grouped_dynamic",
        "entry_id": "xlsx/gt-h1-fixed-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H1 固定资产.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 42 冻结 h1_grouped_dynamic pilot 的唯一候选 entry（`assess_pilot_classes()` "
            "实测 1 个候选、bidirectional 0 个），逐 sheet 读权威模板的 26 张 sheet 后只声明"
            "受管 sheet `减少检查表H1-8` —— 它是契约 schema 域内（`header_rows` 1..3）分组"
            "最深的一张：三级表头 10/11/12 行（4 个横向组 + 3 个中层 + 6 个真叶子）、"
            "动态行 13..27、L/O 两列逐行公式、A28 合计 footer、B/E 两条数据验证。"
            "25 个字段各带 source_ref / header_source_ref / mid_source_ref / "
            "group_source_ref；骨架行数由 `skeleton_row_count(seed) = max(seed,1)` 决定，"
            "不写死模板自带的 15 行。X 列是模板占位列（表头 `……`）故按 Requirement 6.1 "
            "不声明；UUID 列取 AB 而非 AA（AA11 有可见注解）。"
            "工作簿里分组更深的 `明细表H1-2`（四级表头）**表达不了**，登记为 "
            "`pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`h1.disposal_check` —— 该 entry 的 manifest 已由 reviewed overlay 裁决为 "
            "`bidirectional`（`adapter_id` 同步写回），approved bundle / current published "
            "representation / entry_state 三件供给齐备，观测器真读出 frozen identity 后走完 "
            "`build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation）。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE。"
        ),
    },
    # ── Task 43 追加（只加不动；本条起至 tuple 结束是 Task 43 的字节区间）────────
    {
        "contract_id": "g7.soe_subsidiary_disclosure",
        "provider_module": "app.services.workpaper_sync.pilot_g7_two_level_dynamic",
        "delivered_by_task": "43",
        "pilot_class": "g7_two_level_dynamic",
        "entry_id": "xlsx/gt-g7-long-term-equity-main",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G7 长期股权投资.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 43 冻结 g7_two_level_dynamic pilot 的 entry。`assess_pilot_classes()` 实测 "
            "**3 个**候选（gt-g7-equity-method / gt-g7-equity-subsidiary / "
            "gt-g7-long-term-equity-main）、bidirectional 0 个；收敛到一个的决定性事实是 "
            "**matcher 域独占**：前两个共用 `wp_code_patterns == [\"G7E\"]`，以它为 "
            "`EntryMatcher.wp_codes` 的 adapter 会触发 RG-3 `MatcherOverlapError` / "
            "`AmbiguousAdapterError`，而 `G7L` 只属本 entry。"
            "逐 sheet 读权威模板的 22 张 sheet 后只声明受管 sheet `附注披露信息（国企）`，"
            "并在其上声明两张表：① 静态块 `minority_financials`（源「2、主要财务信息」，"
            "两级表头 62/63 行 —— 行 62 的 5 个**空白**横向合并就是源模板自己的动态列占位，"
            "行 63 的 10 个叶子只有 2 个不同 label 各重复 5 次；10 metric × 10 动态列 = 100 "
            "个字段，`C64:L73` 逐格实测全空 ⇒ 全部 editable）；② 动态行表 "
            "`former_subsidiary_basic`（源「（1）原子公司的基本情况」，5 行骨架、A 列字面量 "
            "1..5 ⇒ auto_source、B..G 逐格跨 sheet 公式 ⇒ formula + formula_mask B79:G83、"
            "footer 取 A85 真实文本）。"
            "本 pilot 是四类里**唯一**真有 `{slot}_{seq}` 动态列的那个：键由 Task 36 的 "
            "`dynamic_column_stable_keys(slot=table_key, count=…)` 生成（签名里拿不到 label），"
            "列数由 `dynamic_column_keys_for_entities()` 从实体列表推出、不写死；"
            "键→列的实测绑定由 `dynamic_column_binding_for()` 产出。"
            "上市侧同构的 5 张动态列矩阵因数据格在源模板里全是公式 ⇒ 零 editable 字段、"
            "merge 家族两条 required scenario 结构性不可满足，故未选用，登记为 "
            "`pilot_g7_two_level_dynamic.UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN`。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`g7.soe_subsidiary_disclosure` —— 该 entry 的 manifest 已由 reviewed overlay "
            "裁决为 `bidirectional`（`adapter_id` 同步写回），approved bundle / current "
            "published representation / entry_state 三件供给齐备，观测器真读出 frozen "
            "identity（含 observed_dynamic_columns 由工作簿物理列跨度 + merge 铺开的 label "
            "现读）后走完 `build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation）。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE。"
        ),
    },
    # ── G5-1 追加（Phase 5 首个 canary，harness 无关的独立 entry 双向路径）─────────
    {
        "contract_id": "d1.notes_receivable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d1_notes_receivable",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_notes_receivable",
        "entry_id": "xlsx/gt-d1-notes-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D1 应收票据.xlsx",
        "adapter_registered": True,
        "reason": (
            "G5-1 Phase 5 首个 canary。**不是第五个 pilot**：四个 pilot 是 "
            "`pilot_harness.PilotClass` 封闭枚举的代表，`xlsx/gt-d1-notes-receivable` 的 "
            "entry_id 不含 d2/h1/g7 会被归进 catch-all `simple_checklist`（B60 已占），故本 "
            "provider 的选型守卫 `assert_entry_selectable` 直接在真 manifest + 真 finder 上核"
            "四条事实（entry 存在 / independent=True / profile==D2/B60 同型 "
            "`xlsx.editable.shared.single.room_service_wired.v1` / wp_code==['D1N']）+ 零回退"
            "（D1N find/any 均 None、父码 D1 落权威模板），**不**调 `assess_pilot_classes()`。"
            "逐 sheet 读权威模板 `D/D1 应收票据.xlsx`（21 张 sheet）后只声明受管 sheet "
            "`原值明细表（按客户）D1-3`：单级表头行 10（15 列 A..O）、数据区 11..20、"
            "G/J/L/O 四列逐行公式 `=D+E+F` / `=D+H-I` / `=J+K` / `=L+M+N`（openpyxl 逐格实测）、"
            "A21 合计 footer。HTML store = `checklist_responses.item_id='D1-cust-rows'`"
            "（前端 useD1DetailCustomer.ts 的 CustomerRow 整行数组 serializeRows()），按 "
            "stable field + rowId 拆成 15 字段/行，禁止把整 JSON 当一个字段。"
            "`adapter_registered=False` 是**顺序**：Task 4 把 overlay 裁决为 bidirectional 并"
            "重生 manifest（当前 capability=single_onlyoffice）、发布链产出 approved bundle + "
            "current published representation 之后方可注册；未就绪时 `attach_adapters` 返回空"
            "元组且一次库都不读，契约孤儿由 `RegistryReport.contract_files_without_adapter` "
            "持续可见。"
        ),
    },
    # ── G5-1 追加（Phase 5 第二个 canary：D7 合同负债，两级表头 + 账龄组）─────────
    {
        "contract_id": "d7.contract_liabilities_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d7_contract_liabilities",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_contract_liabilities",
        "entry_id": "xlsx/gt-d7-contract-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D7 合同负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第二个 canary（同 D1 的 harness 无关独立 entry 路径，非第五 pilot）。"
            "选型守卫 assert_entry_selectable 直接核四条 manifest 事实（entry 存在 / "
            "independent=True / profile==D2/B60 同型 / wp_code==['D7C']）+ 零回退（D7C find/any "
            "均 None、父码 D7 落权威模板），不调 assess_pilot_classes()。逐 sheet 读权威模板 "
            "D/D7 合同负债.xlsx 后只声明受管 sheet 明细表D7-2：两级表头行 8 / 行 9（账龄子标题），"
            "27 列 A-AA，数据区 10-22，I/P/R/U 四列逐行公式 =F+G+H / =F-N+O（贷方科目）/ =P+Q / "
            "=R+S+T，A23 合计 footer；19 标量 + 两个账龄组各 4 段（THREE_YEAR），字段键与前端 "
            "useD7Detail.DetailRow 锁死。HTML store = checklist_responses.item_id='D7-2-rows'，"
            "账龄 nested keyed。wp_code 裁决=['D7']（**不是 D7C 幻影码 / D7-2 名义码**）：查真库"
            "确认 store 载荷落 wp_code=D7（project 0ec33ac9 / wp 6f23dcce / 669B）。"
            "`adapter_registered=False` 是顺序：overlay 裁决 bidirectional + 重生 manifest + 发布链"
            "产出 approved bundle + current published representation 之后方可注册。"
        ),
    },
    # ── G5-1 追加（Phase 5 第三个 canary：D3 预收账款，两级表头 + 账龄组）─────────
    {
        "contract_id": "d3.prepaid_receipts_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d3_prepaid_receipts",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_prepaid_receipts",
        "entry_id": "xlsx/gt-d3-prepaid-accounts",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D3 预收账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第三个 canary（同 D1/D7 的 harness 无关独立 entry 路径）。选型守卫 "
            "assert_entry_selectable 核四条 manifest 事实（entry 存在 / independent=True / "
            "profile==room_service_wired.v1 / wp_code==['D3P']）+ 零回退（D3P find/any 均 None、"
            "父码 D3 落净化后权威模板）。逐 sheet 读净化后权威模板 D/D3 预收账款.xlsx（外链净化后 "
            "sha256 699a9be0）后只声明受管 sheet 预收账款明细表D3-2：两级表头行 10 / 行 11（账龄"
            "子标题），27 列 A-AA，数据区 12-23，H/O/Q/T 四列逐行公式 =E+F+G / =E+N-M（贷方科目）/ "
            "=O+P / =Q+R+S，A24「合计」footer（纯两字无空格，非 D7 的三空格）；19 标量 + 两个账龄组"
            "各 4 段（THREE_YEAR），字段键与前端 useD3Detail.DetailRow 锁死。HTML store = "
            "checklist_responses.item_id='D3-det-rows'，账龄 nested keyed。wp_code 裁决=['D3']"
            "（**不是 D3P 幻影码 / D3-2 名义码**）：D3-det-rows 全库 0 行（同 H1 空表单），但 sibling "
            "D3-vc-current-rows 载荷落 wp_code=D3（1 行 3601B）已证 D3 store 落点=D3，且 D3 wp 未删除"
            "有 file_path。`adapter_registered=False`：**与真实库对齐**——真库 "
            "`register_from_manifest()` 当前只注册 {d2,d4,g7,h1}（有真实供给的 entry），"
            "D3-det-rows / D3-vc 全库 0 行、无 current published representation ⇒ 未注册成功。"
            "原登记乐观标 True 与现实脱钩（Property 49 实测捕获）；发布链真正产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 追加（Phase 5 第四个 canary：D6 合同资产，两级表头 + 账龄组，账龄 FLAT 键）─────
    {
        "contract_id": "d6.contract_assets_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d6_contract_assets",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_contract_assets",
        "entry_id": "xlsx/gt-d6-contract-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D6 合同资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第四个 canary（同 D1/D3/D7 的 harness 无关独立 entry 路径）。选型守卫核四条"
            "manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D6C']）+ 零回退（D6C find/any 均 None、父码 D6 落净化后权威模板）。逐 sheet 读"
            "净化后权威模板 D/D6 合同资产.xlsx（外链净化后 sha256 88125e42）后只声明受管 sheet "
            "明细表D6-2：两级表头行 12 / 行 13（账龄子标题），32 列 A-AF（受管 A-AD），数据区 14-25，"
            "J/Q/T 三列逐行公式 =G+H+I / =G+O-P（借方科目）/ =Q+R+S，A26「合   计」footer（3 半角空格，"
            "同 D7）；22 标量 + 两个账龄组各 4 段（K-N 期初 / U-X 期末，**FLAT 键 agePrior*/ageEnd***，"
            "非 D3/D7 的 nested），字段键与前端 useD6Detail.DetailRow 锁死。HTML store = "
            "checklist_responses.item_id='D6-2-rows'。wp_code 裁决=['D6']（**不是 D6C 幻影码 / D6-2 "
            "名义码**）：D6-2-rows 全库 0 行（同 H1/D3 空表单），D6 wp 未删除有 file_path。"
            "`adapter_registered=False`：**与真实库对齐**——真库 `register_from_manifest()` 当前只注册 "
            "{d2,d4,g7,h1}，D6-2-rows 0 行、无 current published representation ⇒ 未注册成功。"
            "原乐观标 True 与现实脱钩（Property 49 捕获）；发布链产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 追加（Phase 5 第五个 canary：D5 应收款项融资，两级表头无账龄 FVOCI）─────
    {
        "contract_id": "d5.receivables_financing_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d5_receivables_financing",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_receivables_financing",
        "entry_id": "xlsx/gt-d5-receivables-financing",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D5 应收款项融资.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第五个 canary（同 D1/D3/D6/D7 的 harness 无关独立 entry 路径）。选型守卫核"
            "四条 manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D5R']）+ 零回退（D5R find/any 均 None、父码 D5 落净化后权威模板）。逐 sheet 读"
            "净化后权威模板 D/D5 应收款项融资.xlsx（外链净化后 sha256 92c5f7f2）后只声明受管 sheet "
            "应收款项融资明细表D5-2：两级表头行 10（组标题 期初数 C:G / 本期变动 H:I / 期末数 J:P）/ "
            "行 11（子标题），17 列 A-Q，数据区 12-16，F/J/L/O 四列逐行公式 =C+E+D / =C+H-I / =J+K / "
            "=J+N+M，A17「合计」footer（纯两字，同 D3）；**FVOCI 无账龄组**（最简 canary，group 下"
            "每个子列是不同语义字段），字段键与前端 useD5Detail.DetailRow 锁死（postRealized/eclStage "
            "store-only 不入）。HTML store = checklist_responses.item_id='D5-2-rows'。wp_code 裁决=['D5']"
            "（**不是 D5R 幻影码 / D5-2 名义码**）：D5-2-rows 全库 0 行（同 H1/D3/D6 空表单），D5 wp 未删除"
            "有 file_path。`adapter_registered=False`：**与真实库对齐**——真库 `register_from_manifest()` "
            "当前只注册 {d2,d4,g7,h1}，D5-2-rows 0 行、无 current published representation ⇒ 未注册成功。"
            "原乐观标 True 与现实脱钩（Property 49 捕获）；发布链产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 D4 营业收入（位置数组；契约含 D4-2/D4-3/D4-5 sibling sheets）─────
    {
        "contract_id": "d4.revenue_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d4_revenue_detail",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_revenue_detail",
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D4 收入底稿.xlsx",
        "adapter_registered": True,
        "reason": (
            "G5-1 Phase 5 第六个 canary（第五种行形态：位置数组）。选型守卫 assert_entry_selectable "
            "核四条 manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D4O']）+ 零回退（D4O find/any 均 None、父码 D4 落净化后权威模板）+ "
            "mapping_digest 哨兵。权威模板 D/D4 收入底稿.xlsx（sha256 b8fb92d4…）；受管 sheets="
            "d42-managed / d43-managed / d45-managed（D4-5 政策检查：分组紧凑表 + 经营模式 B11–B16；"
            "宿主 D4TabPolicyCheck 独立，不进 isD4DetailSheet）。HTML store 含 D4-2-rows / D4-3-rows / "
            "D4-5-policy-groups + D4-5-biz-*。wp_code 裁决=['D4']（真载荷落点）。"
            "D4-9 重要客户结构分析作为 sibling sheet（d49-managed，同 entry / 同 adapter）"
            "并入本 entry —— 与 D4-1/2/3/5/15/16/21~29/35 同架构（overlay 规则：D4 子表 mount "
            "归父 entry，不独立计数）。"
        ),
    },
    # ── E1 货币资金 canary（spec: e1-sync-coverage-and-first-canary · Task 10）─────
    {
        "contract_id": "e1.monetary_fund_detail",
        "provider_module": "app.services.workpaper_sync.phase5_e1_monetary_fund",
        "delivered_by_task": "E1-canary",
        "pilot_class": "phase5_monetary_fund",
        "entry_id": "xlsx/gt-e1-monetary-fund",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx",
        "adapter_registered": False,
        "reason": (
            "E1 canary（spec e1-sync-coverage-and-first-canary）。选型守卫 assert_entry_selectable "
            "核四条 manifest 事实（entry 存在 / independent=True / "
            "profile==xlsx.editable.shared.single.room_service_wired.v1 / wp_code==['E1']）。"
            "权威模板 E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx "
            "（sha256 8317e2ba…）；受管 sheets= e12-managed(canary) / e14-managed / "
            "e16-managed / e17-managed / e18-managed / e19-managed / e110-managed / "
            "e111-managed(static_region)。HTML store 含 E1-cash-detail-rows / "
            "E1-digital-rows / E1-reconciliation-rows / E1-cash-count-{rmb|fx|cert}-rows / "
            "E1-account-list-rows + static E1-account-commit。行身份键统一为 `id`"
            "（不是 D 类的 rowId）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7 卡在同一平台级缺口"
            "（umbrella BP-61-1：published representation 三表近空，186 个 planned "
            "entry 一个都注册不上），供给就绪后真栈注册。"
        ),
    },
    # ── F1 预付账款 canary（spec: f1-sync-coverage-and-first-canary · Task 9）─────
    {
        "contract_id": "f1.prepayment_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f1_prepayment",
        "delivered_by_task": "F1-canary",
        "pilot_class": "phase5_prepayment",
        "entry_id": "xlsx/gt-f1-prepayment",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F1 预付账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "F1 canary（spec f1-sync-coverage-and-first-canary）。选型守卫 "
            "assert_entry_selectable 核四条 manifest 事实（entry 存在 / "
            "independent=True / profile==room_service_wired.v1 / "
            "wp_code==['F1P']）+ 零回退（F1P find/any 均 None、父码 F1 落权威模板）。"
            "权威模板 F/F1 预付账款.xlsx（sha256 f30055cb…）；canary 受管 sheet = "
            "关联方及交易检查表F1-6（单级表头 / 3 行 / F/H 两列公式 / UUID N 列）。"
            "HTML store = checklist_responses.item_id='F1-rp-rows'（前端 "
            "useF1RelatedParty.ts 的 RelatedPartyRow 行数组）。"
            "wp_code 裁决=['F1']（store 载荷 F1-det-rows 46,295 B 落在 "
            "wp_code=F1 上；F1P 是 CamelCase 幻影码 finder 零命中）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1 卡在同一平台级缺口"
            "（umbrella BP-61-1），供给就绪后真栈注册。"
        ),
    },
    # ── F2 main（spec: f2-sync-coverage-four-entry-lanes · Task 7）──────
    {
        "contract_id": "f2.inventory_main",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_main",
        "delivered_by_task": "F2-main-canary",
        "pilot_class": "phase5_f2_inventory_main",
        "entry_id": "xlsx/gt-f2-inventory-main",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 main lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "三个 F2I entry 共用幻影码，matcher 域靠 sheet_keys 互斥解 RG-3（F2-H1）。"
            "canary 受管 sheet = 四、自制半成品明细表F2-6（F2-H4）。"
            "权威模板 F/F2-1至F2-14（sha256 9e57efd2…）；"
            "HTML store = checklist_responses.item_id='F2-6-rows'。"
            "wp_code 裁决=['F2']（35 键全在父码 F2）。"
            "`adapter_registered=False`：与 D/E/F1 卡在同一平台级缺口"
            "（umbrella BP-61-1），供给就绪后真栈注册。"
        ),
    },
    # ── F2 stocktake（spec: f2-sync-coverage-four-entry-lanes · Task 14）──────
    {
        "contract_id": "f2.stocktake_bundle",
        "provider_module": "app.services.workpaper_sync.phase5_f2_stocktake_bundle",
        "delivered_by_task": "F2-stocktake-canary",
        "pilot_class": "phase5_f2_stocktake_bundle",
        "entry_id": "xlsx/gt-f2-stocktake-bundle",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 stocktake lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2S 独占幻影码，无 RG-3 冲突。canary = F2-25 双区。"
            "权威模板 F/F2-21至F2-26（sha256 bdfdcf8a…）。"
            "wp_code 裁决=['F2']。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F2 valuation（spec: f2-sync-coverage-four-entry-lanes · Task 18）──────
    {
        "contract_id": "f2.inventory_valuation",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_valuation",
        "delivered_by_task": "F2-valuation-canary",
        "pilot_class": "phase5_f2_inventory_valuation",
        "entry_id": "xlsx/gt-f2-inventory-valuation",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 valuation lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2I + sheet_keys 解 RG-3。canary = F2-48 dict 子数组。"
            "F2-47 卡 FC-10（百分数换算），灰度关待 Task 20。"
            "权威模板 F/F2-47至F2-49（sha256 bab0abc0…）。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F2 special（spec: f2-sync-coverage-four-entry-lanes · Task 22）──────
    {
        "contract_id": "f2.inventory_special",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_special",
        "delivered_by_task": "F2-special-canary",
        "pilot_class": "phase5_f2_inventory_special",
        "entry_id": "xlsx/gt-f2-inventory-special",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F2-55至F2-58 合同履约成本.xlsx",
        "adapter_registered": False,
        "reason": (
            "F2 special lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2I + sheet_keys 解 RG-3。canary = F2-57 dict 子数组。"
            "权威模板 F/F2-55至F2-58（sha256 b9ea2481…）。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F3 canary（spec: f3-sync-coverage-and-first-canary · Task 9）─────────
    {
        "contract_id": "f3.notes_payable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f3_notes_payable",
        "delivered_by_task": "F3-canary",
        "pilot_class": "phase5_notes_payable",
        "entry_id": "xlsx/gt-f3-notes-payable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F3 应付票据.xlsx",
        "adapter_registered": False,
        "reason": (
            "F3 canary（spec f3-sync-coverage-and-first-canary）。选型守卫 "
            "assert_entry_selectable 照 D3 同签名（resolution 必填 / 无关闭开关）并对**真 "
            "manifest 真调**（wp_code_patterns==['F3N'] 幻影码）+ 零回退（F3N 在 wp_index 与 "
            "wp_templates/_index.json 均 0 命中，父码 F3 落权威模板）。"
            "权威模板 F/F3 应付票据.xlsx（sha256 06de707b…，79,616 B，12 sheets）；"
            "canary 受管 sheet = 逾期票据检查F3-5（两级表头 R5/R6 / 数据 R7-21 / "
            "footer R22「合计」纯两字 / UUID 列 P / **数据区零公式** —— 10 个公式全在页眉与 footer）。"
            "HTML store = checklist_responses.item_id='F3-5-rows'（真库 675 B / 2 行全带 rowId，"
            "F3 唯一有载荷的键；🔴 实测是 2 行**空白行**，有意义数值的 roundtrip 仍需 seed）。"
            "🔴 契约装配走框架层 spec_to_contract_sheet_payload（不手写 table payload）—— "
            "F1 的手写版缺 anchor/header_rows/row_identity.json_pointer 等必填字段，parse_contract 直接抛。"
            "I 列（票面利率）命中 FC-10（模板 0.00% × 前端存百分数）⇒ 暂不进 field_specs，"
            "待 value_type=percent_points 换算落地（merge.py 现无任何 percent 换算）。"
            "wp_code 裁决=['F3']（wp_index 4 行）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1/F2 卡在同一平台级缺口"
            "（umbrella BP-61-1：slice 实测 published_representation=null），供给就绪后真栈注册。"
        ),
    },
    # ── F4 canary（spec: f4-sync-coverage-and-first-canary · Task 8）─────────
    {
        "contract_id": "f4.accounts_payable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f4_accounts_payable",
        "delivered_by_task": "F4-canary",
        "pilot_class": "phase5_accounts_payable",
        "entry_id": "xlsx/gt-f4-accounts-payable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F4 应付账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "F4 canary（spec f4-sync-coverage-and-first-canary）。"
            "🔴 **全 F 循环唯一「幻影码撞真码」**：manifest 的 wp_code_patterns==['F4A'] 与 "
            "wp_code_overrides.json 的程序表路由码 F4A 字面相同（裁决 F4-H2：两侧都不改）。"
            "四条隔离事实实测：wp_templates/_index.json 无 F4A（F 循环只有 F0~F5 六个真码）· "
            "wp_index 无 F4A（真码 F4 有 5 行）· provisioner 用裁决真码 ['F4'] · "
            "assert_no_implicit_template_fallback('F4A') 通过 ⇒ 幻影码只存在于路由表一处，"
            "误当业务码用时得到空集而不是命中程序表。"
            "权威模板 F/F4 应付账款.xlsx（sha256 e20e6272…，108,329 B，15 sheets）；"
            "canary 受管 sheet = 关联方及交易检查表F4-6（单级表头 R6 / 数据 R7-11 / "
            "footer R12「合计」/ UUID 列 M / formula_columns=('F',)）。"
            "🔴 公式 F=C+E-D（**负债类**：期初+贷方−借方）与 F1-6 的 F=C+D-E（资产类）互为镜像 —— "
            "同型不等于同式，逐格实测所得（FC-4）。"
            "HTML store = checklist_responses.item_id='F4-6-rows'；真库 F4-2-rows 3,485 B / "
            "4 行全带 rowId + F4-7-estimated-inbound-rows 1,211 B / 2 行（同一底稿）。"
            "FC-10 **不命中**（F4-6 逐格实测零百分比格式格）—— 四个 F spec 里唯一无该阻塞的。"
            "顺带发现并登记的模板缺陷：B8:B11 的数据验证 formula1=$N$7:$N$14 而 N 列全空"
            "（悬空引用，仅 B7 的 DV 指向真实枚举源 $B$18:$B$25）—— 不改模板字节。"
            "`adapter_registered=False`：同 BP-61-1。"
        ),
    },
    # ── F5 canary（spec: f5-sync-coverage-and-first-canary · Task 9）─────────
    {
        "contract_id": "f5.cost_of_sales_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f5_cost_of_sales",
        "delivered_by_task": "F5-canary",
        "pilot_class": "phase5_cost_of_sales",
        "entry_id": "xlsx/gt-f5-cost-of-sales",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F5 营业成本.xlsx",
        "adapter_registered": False,
        "reason": (
            "F5 canary（spec f5-sync-coverage-and-first-canary）。选型守卫对真 manifest 真调"
            "（wp_code_patterns==['F5C']）+ 零回退（F5C 在 wp_index 与 _index.json 均 0 命中）。"
            "权威模板 F/F5 营业成本.xlsx（sha256 417e5ae7…，187,721 B，11 sheets）；"
            "canary 受管 sheet = 重大调整核查表F5-8（两级表头 R12/R13 / 数据 R14-29 / "
            "**无 footer 合计** ⇒ 锚行 R30 + footer_carries_total_formula=False，"
            "🔴 marker 逐字是「三、审计说明：」**带全角冒号**（spec Task 8 漏了冒号，"
            "assert_footer_anchor_stable 逐字匹配会失败）/ UUID 列 I —— "
            "🔴 **超出模板 max_column(H)** ⇒ instrumentation 需扩列）。"
            "🔴 行身份是 **`id`** 不是 rowId（F5-2/3/5/8 四张皆如此，与 D 类惯例相反）。"
            "G 列不单独声明 —— 被 F 列的 F{r}:G{r} 逐行合并吞掉（表头区 F12:G13 跨两行两列）。"
            "🔴 **真库完全无载荷**（全部 F5-% 键 0 行，F 循环唯一）⇒ wp_code 裁决条目的 "
            "max_payload_bytes 如实记 0（不伪造），验收前必须先 seed（裁决 F5-H7 / Property 8），"
            "否则空表往返会被判 store_mirrored 假绿。"
            "BP-7 三处下标派生行身份（useF5MonthlyDetail:133 / useF5OtherCost:146 / "
            "useF5Comparison:128）是 slice 明令的双向硬前置，已由 f5RowIdentity.ts 单点收敛并立即回写。"
            "HTML-only 登记：F5-1 主营区（七列全是引 F5-2 的公式、零 editable ⇒ 受管会与 F5-2 双源，"
            "裁决 F5-H3）· F5-4（FC-6 hub）· F5-6（244 公式三块，后置另立 spec）。"
            "`adapter_registered=False`：同 BP-61-1。"
        ),
    },
    # ── G2 canary（spec: g-cycle-sync-foundation-and-first-canary · Task 14）──
    {
        "contract_id": "g2.interest_receivable_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g2_interest_receivable"
        ),
        "delivered_by_task": "G2-canary",
        "pilot_class": "phase5_interest_receivable",
        "entry_id": "xlsx/gt-g2-interest-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G2 应收利息.xlsx",
        "adapter_registered": False,
        "reason": (
            "G 循环**首条** entry（spec g-cycle-sync-foundation-and-first-canary，"
            "canary 裁决 GF-H1）。G 循环起点是 E1 级：17 条 entry 零 provider / 零契约 / "
            "零 published representation，本条是第一个。"
            "assert_entry_selectable 照 D3 同签名（resolution 必填 / 无关闭开关）并对"
            "**真 manifest 真调**（wp_code_patterns==['G2I'] 幻影码）+ 零回退"
            "（G2I 在 wp_index 实测 0 命中，真码 G2 有 4 行活行）。"
            "权威模板 G/G2 应收利息.xlsx（sha256 c7563e85…，99,479 B，12 sheets）；"
            "canary 受管 sheet = 明细表G2-2（**单级**表头 R9 / 数据 R10-15 / "
            "footer R16「合计」/ 公式列 E·H·J 共 18 格：E=C+D · H=C+F-G · J=H+I / "
            "有效内容列 13 即 A-M、N·O·P 全空 ⇒ UUID 列 N / 0 个 definedName）。"
            "🔴 **范式裁决 GF-H3**：走 `phase5_*` 声明式范式，**不照** 同循环已迁移的 G7 "
            "（G7 是 `pilot_g7_two_level_dynamic` 的 `pilot_*` 范式，形态早于行表引擎）；"
            "唯一复用 G7 的是 `oo_crash_neutralization_fn`（范式无关的 per-file 缓解件）。"
            "🔴 **GC-2**：G2 册裸 IF **21 格**（审定表G2-1 19 + 应收利息坏账准备测算G2-7 2，"
            "受管表本身零命中）⇒ 仍按 per-file 保守策略挂中性化。"
            "（spec RG-4 表记的 40 是 `findall` 出现次数不是格数，权威口径见 evidence/task0。）"
            "🔴 **GC-5**：HTML store = checklist_responses.item_id='G2-2-detail-rows'，"
            "payload 落 **remark**（`conclusion` 是字面 null 占位 —— FD-1 的 null 占位"
            "子形态，**全 slice 仅 G2 一条**）。判 mode 必须先剔占位，否则会被误判 dual_write。"
            "真库实测 remark **475 B** / conclusion 0 B ⇒ 裁决 GF-H2：**不 seed**，"
            "但验收判据须断言 roundtrip 行数 > 0 且来自真库。"
            "🔴 契约装配走框架层 `spec_to_contract_sheet_payload`（同 F3~F5 的做法）—— "
            "本轮实测 F1 的手写版缺 anchor/header_rows/row_identity.json_pointer，"
            "`parse_contract` 直接抛、`assert_contract_file_matches_source` 从来过不了；"
            "G2 的生成器在写盘前先跑 parse_contract，形态错就不落盘。"
            "BP-10 的 G2 份额已收敛：`G2-2-detail-rows` 原有 **5 处**声明"
            "（g2CrossHelpers / useG2Detail / useG2DisclosureListed / useG2DisclosureSoe / "
            "useG2InterestCalc）⇒ 新建 `g2StorageContract.G2_ITEM_IDS` 单一真源 + 派生别名"
            "（范式照 BP-10 正面样本 g6CrossHelpers）。"
            "wp_code 裁决=['G2']（真库 G2-2-detail-rows 载荷落 wp_code=G2）。"
            "FC-9 红线：G2 已接显式发布门（科目 1132 余额口径，useG2Adjudication.publishToTb=3），"
            "本 provider 对 trial_balance 写次数为 0。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3：instrumentation candidate / "
            "人工审核契约 / approved bundle 三缺），供给就绪后真栈注册。"
        ),
    },
    # ── G9（spec: g-cycle-single-region-detail-lanes · Task 8 / C-5）──────────
    {
        "contract_id": "g9.other_noncurrent_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g9_other_noncurrent"
        ),
        "delivered_by_task": "G1R-Task8",
        "pilot_class": "phase5_other_noncurrent_financial",
        "entry_id": "xlsx/gt-g9-other-noncurrent-financial",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G9 其他非流动金融资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**首条**（lane 顺序由易到难 "
            "G9→G10→G8→G14→G11→G13→G12→G3→G1）。范式照 G2 的 `phase5_*`，不照 G7 的 "
            "`pilot_*`；唯一复用 G7 的是 `oo_crash_neutralization_fn`。"
            "权威模板 G/G9 其他非流动金融资产.xlsx（sha256 264322c0…，88,636 B，10 sheets）；"
            "受管 sheet = 明细表G9-2（**两级**表头 R9 组 / R10 叶子 / 有效内容列 28 即 A-AB / "
            "0 个 definedName / 12 个公式列 E·H·I·J·L·P·Q·R·U·V·W·Y 共 156 格 / "
            "合计 R30 是**枚举相加** =SUM(C17,C24,C29) 非 SUM 区间）。"
            "🔴 **全库首个「一个 store 键 × 三个受管区」**：三区 R12-16 / R19-23 / R26-28 "
            "（区标题行 R11·R18·R25 与小计行 R17·R24·R29 均不受管）的行都存在**同一个** "
            "`G9-detail-rows` 数组里，区归属由行的 `section` 字段表达。既有多区范式 "
            "`phase5_d3_04_analysis` 是「一区一个 store_item_id」（要求前端拆键）—— 这里"
            "**不拆**：该键有真库载荷 605 B、被 8 个跨表消费方读取、且是 BP-10 登记键，"
            "拆键波及面远大于在引擎加一层可选过滤。改为引擎 `row_section_field='section'` + "
            "逐段 `row_section_value`（`iter_store_rows` 按它过滤、"
            "`merge_projection_into_store_rows` 给新增行补它，两处成对）。"
            "⇒ provider 的三个 store 门面按「遍历三段」组合：投影合并三段、回写顺序穿线、"
            "iter 串联三段；`html_store.item_ids` 仍只有 **1** 条（不是 3）。"
            "🔴 `template_id` 逐区不同（G92R1/R2/R3）而 `sheet_key` 共享（g902-managed）："
            "instrumentation 的 definedName 按 template_id 命名（实测抛「多 sheet "
            "instrumentation 的 template_id 必须唯一」），而契约层同 excel_name 两个 "
            "sheet_key 会产出重复 sheet 条目。先例 `phase5_d3_04_analysis`（D34DEBIT/D34CREDIT）。"
            "🔴 **前端根治在先**（用户拍板选项 C）：`useG9Detail.ts` 原 30 列里 15 列与权威模板"
            "不符 —— `ociChange`/`ociCumulative`/`impairmentLoss`/`impairmentProvision` 属 "
            "FVOCI 口径（G9 模板编制说明 A38-A43 五类全 **FVTPL**，CAS22 下不确认 OCI 与减值）、"
            "`fairValueLevel`/`valuationMethod` 属 G9-4/G9-5 两张表、另 6 列模板没有。已按模板"
            "列序 A..AB 重写为 28 字段「三分量 × 四阶段」模型（成本 + 累计公允价值变动 = 公允"
            "价值；未审→账项调整→审定→重分类报表）并带迁移函数与丢弃计数。"
            "🔴 顺带修掉 `g9FvCrossHelpers.pushG9FvToDetail`（G9-4 往 G9-2 回写那三列，"
            "层次与方向都错 —— G9-2 无公允价值层次列）。"
            "🔴 **GC-2**：G9 册裸 IF **42 格**（全在 审定表G9-1，受管表 明细表G9-2 零命中）"
            "⇒ 仍按 per-file 保守策略挂中性化（点同册任一 sheet 的在线编辑都会触发整册加载）。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G9-detail-rows'，"
            "payload 落 **remark**（真库实证 remark 605 B / conclusion 0 B）⇒ 不 seed，"
            "验收判据断言 roundtrip 行数 > 0 且来自真库。"
            "wp_code 裁决：manifest 幻影码 ['G9O']（matcher 域），真码 **G9**（载荷所在）。"
            "FC-9 红线：G9 已接显式发布门（useG9Adjudication.publishToTb），"
            "本 provider 对 trial_balance 写次数为 0；审定表 审定表G9-1 归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── G10（spec: g-cycle-single-region-detail-lanes · Task 9 / C-7）─────────
    {
        "contract_id": "g10.trading_liabilities_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g10_trading_liabilities"
        ),
        "delivered_by_task": "G1R-Task9",
        "pilot_class": "phase5_trading_financial_liabilities",
        "entry_id": "xlsx/gt-g10-trading-financial-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G10 交易性金融负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**第二条**。范式照 G2/G9 的 "
            "`phase5_*`；与首条 G9 的结构差别只在受管区数量 —— G10 是**单区** ⇒ 三个 store "
            "门面各自 ≤3 行薄转发框架层引擎，不需要 G9 那样的「遍历三段」伴生模块。"
            "权威模板 G/G10 交易性金融负债.xlsx（sha256 3afd5131…，99,458 B，12 sheets）；"
            "受管 sheet = 明细表G10-2（**两级**表头 R9 组 / R10 叶子 / 单区 R11-R20 / "
            "footer R21 逐列 =SUM(x11:x20) 且 **O21 例外**为 =M21+N21 / 6 个公式列 "
            "E·G·K·L·M·O 共 60 格 / 0 个 definedName）。"
            "🔴 **UUID 列取 T 不是 max_column+1**：`max_column=24` 含空列，有效内容列只有 "
            "**19**（A..S，T..X 全空）⇒ 判据 GC-3 的口径是「有效列右移一列」。"
            "🔴 **前端根治在先**（用户拍板选项 C）：`useG10Detail.ts` 原 35 列里 16 列与权威"
            "模板不符 —— OCI/减值四列属 FVOCI 口径（CAS22 下 FVTPL 不确认 OCI 与减值）、"
            "`fairValueLevel`/`valuationMethod` 属 G10-5/G10-6 两张表、`isDerivative` 属 "
            "G10-8、另自研 `currentDecrease`/`closingBalance` 两列与模板口径冲突。已按模板"
            "列序 A..S 重写为 19 字段模型。"
            "🔴 **负债侧三处会计口径差异（不是 G9 的镜像）**：① `F`/`G`（期初调整/审定）与 "
            "`N`/`O`（期末）在 R9 **无合并区** —— 负债侧调整与审定**都不拆分量**，资产侧 G9 "
            "是拆的（M/N 两列调整 → P/Q 两列审定）；② `L=D+I+J` **含利息 J** —— 交易性金融"
            "负债的利息计入财务费用**同时增加负债账面价值**，改造前前端算 D+I（漏 J）致审定数"
            "系统性偏小；③ 本期变动是**净额列**（表头逐字「增加\"+\"/减少\"—\"」）⇒ 模板没有"
            "「本期减少」列，改造前的自研 `currentDecrease` 与走审定线的 `closingBalance`"
            "（=期初审定+变动−减少）两个字段都与模板不符，已移除。`K=C+H` 走未审线（同 G9 的 P=C+M）。"
            "🔴 顺带停用两处方向错的回写：`pushG10FvToDetail`（公允价值层次应落 G10-5）与 "
            "`pushG10DerivativeCheckToDetail`（衍生工具核查应落 G10-8）—— 保签名恒返 0 不写 "
            "store，避免打断 4 个调用方；`sumG10DetailLevel3Closing` 与 "
            "`useG10L3Reconciliation` 的 Level3 名单改由 **G10-5** 定，"
            "`isG10DerivativeDetailRow` 只按 B 列项目名称判。"
            "🔴 **GC-2**：G10 册裸 IF **28 格**（全在 审定表G10-1，受管表 明细表G10-2 零命中）"
            "⇒ 仍按 per-file 保守策略挂中性化（点同册任一 sheet 的在线编辑都会触发整册加载）。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G10-detail-rows'，"
            "payload 落 **remark**（真库实证 remark **2 B 即空数组** / conclusion 0 B）⇒ "
            "与 G9 的 605 B 不同，本条**没有**真实行数据可对，roundtrip 判据一律用合成行。"
            "🔴 该键是 **BP-10 第二严重**的重复声明（6 处 `const … = 'G10-detail-rows'`，"
            "仅次于 G1-2-rows 的 8 处）—— 收敛到 per-cycle storage contract 是未清欠账，"
            "本条只在 provider 侧立单一口径（`all_store_item_ids()`）。"
            "wp_code 裁决：manifest 幻影码 ['G10T']（matcher 域），真码 **G10**（载荷所在，"
            "逐字见 workpaper_sync_entry_wp_code_adjudication.json 该节点，其 contract_id "
            "就是本 provider 的 ADAPTER_ID）。"
            "FC-9 红线：G10 已接显式发布门（useG10Adjudication.publishToTb），"
            "本 provider 对 trial_balance 写次数为 0；审定表 审定表G10-1 归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G9 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── G8（spec: g-cycle-single-region-detail-lanes · Task 9b / C-8）─────────
    {
        "contract_id": "g8.other_equity_detail",
        "provider_module": "app.services.workpaper_sync.phase5_g8_other_equity",
        "delivered_by_task": "G1R-Task9b",
        "pilot_class": "phase5_other_equity_instruments",
        "entry_id": "xlsx/gt-g8-other-equity-instruments",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G8 其他权益工具投资.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**第三条**（原 Task 9 是"
            "「G10 + G8」，已拆为 9 / 9b —— 行级 mask 与 G10 无共享代码，绑一条会让完成度"
            "无法诚实表达）。几何同 G10（两级表头 R9/R10 + 单区 R11-R20 + footer R21）⇒ "
            "薄转发，无伴生模块。权威模板 sha256 5c8d3de7…（450,079 B，11 sheets）。"
            "受管 sheet = 明细表G8-2（R9 横向合并区恰三个 C9:F9 期初余额 / I9:N9 本期变动 / "
            "O9:R9 期末余额，另九个跨两行单列 / 有效内容列 **23** 即 A-W 且 X 空 ⇒ uuid_col=X / "
            "0 个 definedName / R22「三、审计说明：」有个 N22==A22 的模板怪癖，在受管区外不碰）。"
            "🔴 **G8 是 FVOCI —— 与 G9/G10 反向**：受管表注释逐字「在初始确认时，企业可以将"
            "非交易性权益工具投资**指定为以公允价值计量且其变动计入其他综合收益**的金融资产。"
            "该指定一经作出，**不得撤销**」⇒ 模板的三个 OCI 列（F 期初累计 / L 本期转留存 / "
            "R 期末累计）是 CAS22 要求的。G9/G10 的前端根治删掉 OCI 四列，依据是「那两张表"
            "全 FVTPL」—— 照抄它们的移除清单会把准则要求的列删掉。同理 G6 也是 FVOCI。"
            "🔴 **前端真重建**（八条里唯一与 G9 同量级）：24 字段 → 23 字段，"
            "拆 3+3 分量（openingBalance→C/D/E · closingBalance→O/P/Q）· 补 2 列"
            "（K 处置时公允价值变动结转 / N 本期确认的股利收入）· 合并 1 组"
            "（increaseAmount+decreaseAmount → I 净额，模板 I 是净额单列）· "
            "改名对齐 2 列（ociOpeningCumulative→F openingOciCumulative · "
            "ociCumulativeChange→R closingOciCumulative，原两名无一对应模板语义）· "
            "删 8 列（五列公允价值测试族归 G8-4 / decreaseAmount 与 I 双源 / "
            "**ociCurrentChange 与模板 J 双源** —— FVOCI 下本期 OCI 就是本期公允价值变动，"
            "改造前还专门写了一条校验提醒两者应相等，那正是双源的证据 / remark 模板无）。"
            "🔴 **模板四处行级公式缺陷**（逐格实测 R11-R20）：M 在 R12-R20 漏加 L · "
            "P 在 R11+R13-R20 漏加 K · R 在 R13-R20 **整格无公式** · T 在 R12 **整格无公式**。"
            "会计判读：M 应含 L、P 应含 K、R(=F+J+L) 与 T(=Q+S) 都是恒等式每行都该有 ⇒ "
            "R11 与 R12 各对一半、R13-R20 两处都漏。与 G5「三段合计各漏加一个小计」同族。"
            "🔴 处置由框架层**两条硬约束**唯一确定：① contracts CS-13（mode=formula 的列必须"
            "落在 formula_mask 内）② excel_materialize 写受保护格时要求 `view.has_formula`，"
            "否则抛 ProtectedRegionWriteError。⇒ M/P 每行都有公式（口径不同）可判 formula 并进"
            "formula_columns；**R/T 只能判 editable** —— 这正是判据 P12 要求证明的「R13 的 R 列"
            "与 R12 的 T 列不被误标 formula」，其技术根据就是第②条。代价是这两列会双向同步、"
            "OO 侧改动被前端按恒等式重算覆盖，已如实登记（修模板要么改字节=禁止，要么走覆盖层"
            "=框架层尚无该机制 + 需会计专业复核，都不在本 lane 范围）。"
            "🔴 **裁决 G1R-H3 两处措辞已修正**：①「拆 r11/r12plus（或三 spec）」不可行 —— "
            "引擎只支持 row_section_field（按**字段值**过滤），而 G8 是连续 R11-R20 里逐行公式"
            "不同，前端数组没有也不该有区归属字段（行的物理位置不是业务属性，那是 BP-11 语义"
            "耦合行身份的同族问题）；②「并集取 formula」按字面会让 R/T 撞 "
            "ProtectedRegionWriteError，正确口径是「模板每行都有公式才可判 formula」。"
            "🔴 顺带停用 `g8CrossHelpers.pushG8FvToDetail`（G8-4 往 G8-2 回写层次/数量/单价/"
            "FV 合计/估值方法五列 —— 权威源就是 G8-4，且 G8-2 重构后没有这五列）；"
            "G8-4 → G8-5 的层次同步方向是对的，未动。与 G9 的 pushG9FvToDetail、G10 的 "
            "pushG10FvToDetail 同族错误，三条同批处置。"
            "🔴 **GC-2**：G8 册裸 IF **12 格**（全 G 循环最少，全在 审定表G8-1，受管表零命中）"
            "⇒ 仍按 per-file 保守策略挂中性化。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G8-detail-rows'，"
            "payload 落 **remark**（真库实证 remark 2 B 即空数组 / conclusion 0 B）⇒ 无真实行"
            "数据，roundtrip 判据一律用合成行。另有 G8-adj-tb-writeback（40 B）是 RG-10 模板化"
            "拼接键，按字面量 grep 零命中，不属本 sheet 受管面。"
            "wp_code 裁决：manifest 幻影码 ['G8O']（matcher 域），真码 **G8**（载荷所在）。"
            "FC-9 红线：G8 已接显式发布门（useG8Adjudication.publishToTb），"
            "本 provider 对 trial_balance 写次数为 0；审定表归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G9/G10 卡在同一平台级"
            "缺口（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── G14（spec: g-cycle-single-region-detail-lanes · Task 10 / C-9）────────
    {
        "contract_id": "g14.credit_impairment_detail",
        "provider_module": "app.services.workpaper_sync.phase5_g14_credit_impairment",
        "delivered_by_task": "G1R-Task10",
        "pilot_class": "phase5_credit_impairment_detail",
        "entry_id": "xlsx/gt-g14-credit-impairment-loss",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G14 信用减值损失.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**第四条**。几何同 G8/G10"
            "（两级表头 R9/R10 + 单区 + footer）⇒ 薄转发，无伴生模块。"
            "权威模板 sha256 5ca77090…（60,094 B，8 sheets）；受管 sheet = 明细表G14-2"
            "（R9 横向合并区恰两个 B9:D9 本期数 / F9:K9 对应科目-减值准备，另四个跨两行单列 "
            "A/E/L/M / 有效内容列 **13** 即 A-M **恰等于 max_column**（无空尾列，此处"
            "「有效列右移一列」与「max_column+1」两个口径重合，不构成 G10/G8 的反例）⇒ "
            "uuid_col=N / 0 个 definedName / R21「三、审计说明」与 R23「四、审计结论」在受管区外）。"
            "🔴 **固定 9 行** R11-R19（行集由模板 A 列写死），行身份是 **`rowKey`**"
            "（`stable_template_row_key`）—— 全 G 循环唯一一家不用生成式 id 的，GC-6 裁决它是"
            "**最稳**的一族（插行/改名都不漂移）；照抄 F 循环的 "
            "`row_identity_key in ('rowId','id')` 白名单会把它判违规。"
            "🔴 **前端行集原与模板不一致**（本轮实测才发现）：前端自研了第 10 行 "
            "`rowKey:'ca'`（合同资产减值损失），而模板固定行集**没有**该专行；行表引擎按"
            "**数组顺序**映射 R11-R19，10 行落进 9 行区会扩行、把 footer R20 挤下去。"
            "另 `rfin` 的 label 写的是「应收款项融资**减值**损失」，模板逐字是「**坏账**损失」。"
            "已按用户拍板的**选项 A** 对齐模板 9 行：label 逐字改正；合同资产的三处落点"
            "（1142 试算取数 / D6 的 ECL 事件 `gCycleSourceEcl.G14_SOURCE_TO_ROW_KEY` / 含"
            "「合同资产」的调整分录 rowKey 推断 `g14AdjStorage`）并入模板 R19「其他」行，"
            "`G14_ECL_CROSS_REF.other` 也随之指向 wp:D6-1 —— 口径不丢、链不断。"
            "国企披露的 `G14_SOE_BAD_DEBT_SOURCES` 同步删 'ca'（`other` 本就单独成行，"
            "留着会双算）。前端另立 `G14_TEMPLATE_ROW_LABELS` 与 provider 的 "
            "`TEMPLATE_ROW_LABELS_G1402` 双向锁，行集再漂移会直接打红。"
            "🔴 **模板缺陷 `K=G+H`**：`J=F+G-H-I` 要求「本期转回」H 填**正数**（转回减少"
            "准备），而同表 `K=G+H` 把转回当成**增加**损益 —— 两式对 H 的符号约定互相矛盾。"
            "判定 K 错的三条依据：① 会计口径「信用减值损失 = 计提 − 转回」② J 的形式与准则"
            "逐字一致 ③ 平台早已裁定转回填正数（前端 `migrateReversalToPositive` 专门把历史"
            "负数统一成正数）。处置同 G8：K 在模板每行都有公式 ⇒ 仍判 `mode=formula`，"
            "`formula_templates` **逐字记模板原式**（判据逐格比对模板，记成 =G-H 会必红）；"
            "前端按 `计提 − 转回` 算 ⇒ 有转回时 Excel 侧 K 比平台侧多 2×转回。如实登记为"
            "欠账（修模板要么改字节=禁止，要么走覆盖层=框架层尚无该机制 + 需会计专业复核）。"
            "模板自带的 `L=D=K` 核对列会在有转回时显示不平 —— 用户看得见，不是静默错。"
            "🔴 **`L` 是布尔校验列**（裁决 G1R-H4）：`=D{r}=K{r}` 求值 TRUE/FALSE ⇒ "
            "`value_type=boolean` + `mode=formula`（`PROTECTED_MODES` 使其不入 store，"
            "TRUE/FALSE 不会落库）。判据三条：extract 不抛 / 异常类型 "
            "type_normalization_failure / store 无 TRUE/FALSE 字面量。"
            "🔴 **前端另删 4 个自研派生字段**：`otherMovement`（模板 J 是 =F+G-H-I **不含**"
            "其他变动项 ⇒ 录入值会在 Excel 侧凭空消失）· `closingComputed`/"
            "`rollForwardVariance`/`rollForwardBalanced`（模板 J 本身就是推算式公式，"
            "「录入期末 vs 推算期末」是双源；期末的对账对象是**试算余额** tbClosing）。"
            "期末余额 J 随之由录入列改为只读公式格，「推算期末」按钮删除，「写入期末」按钮"
            "改为「按试算倒推期初」（原按钮写 J 会被 enrichRow 立刻重算覆盖 = 无效按钮）。"
            "🔴 **GC-2**：G14 册裸 IF **11 格**（全在 审定表G14-1，受管表零命中）⇒ 仍按 "
            "per-file 保守策略挂中性化。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G14-detail-rows'，"
            "payload 落 **remark**（真库实证 remark 2 B 即空数组 / conclusion 0 B）⇒ "
            "roundtrip 判据一律用合成行。另有独立键 `G14-detail-provision-tb`（试算取数缓存）"
            "与三个不受管的对账派生字段（tbClosing / tbClosingMatched / tbClosingVariance），"
            "都不属本 sheet 受管面。"
            "wp_code 裁决：manifest 幻影码 ['G14C']（matcher 域），真码 **G14**（载荷所在）。"
            "🔴 **TB 口径是本期发生额**：G14 是损益类（科目 **6702**），审定合计须与试算 6702 "
            "的本期发生额（借方计提 − 贷方转回）一致 —— 不是余额。"
            "FC-9 红线：G14 已接显式发布门（useG14Adjudication.publishToTb），本 provider 对 "
            "trial_balance 写次数为 0；审定表归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G8/G9/G10 卡在同一"
            "平台级缺口（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── H9 canary（spec: h-cycle-sync-foundation-and-first-canary · Task 20）──
    {
        "contract_id": "h9.lease_liability_detail",
        "provider_module": "app.services.workpaper_sync.phase5_h9_lease_liabilities",
        "delivered_by_task": "H9-canary",
        "pilot_class": "phase5_lease_liability_detail",
        "entry_id": "xlsx/gt-h9-lease-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H9 租赁负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**首条** entry（spec h-cycle-sync-foundation-and-first-canary，canary = H9）。"
            "H 循环起点同 E1/G：9 条独立 entry 零 provider / 零契约 / 零 representation。"
            "canary 选型硬依据：**真库唯一非空主表载荷** —— 现算 checklist_responses 的 remark，"
            "9 条主表键只有 3 条命中（H8-2-rows=[] 2B · H10-detail-rows=[] 2B · "
            "**H9-2-rows 819 B / 2 行真实数据**），其余 6 条无行；"
            "几何最简族（两级表头 R7/R8 · 数据 R9-13 仅 5 行 · footer R14 纯 SUM · "
            "22 有效列 · 54 公式 · 裸 IF 24 格全 H 次少）；无专属阻塞。"
            "受管 sheet = `租赁负债明细表H9-2`，公式列 E·I·J·K·L·N（🔴 **负债贷方**口径 "
            "E=B-C+D / L=I-J+K，抄成资产类会让审定期末反号）；UUID 列 W = 有效内容列 22 + 1。"
            "🔴 **平台级前置**：本 entry 所在循环有五条主受管表是**四级表头**"
            "（明细表H2-2 / H4-2 / H5-2 /（成本模式）H7-2 / H8-2）⇒ 本 spec 把 "
            "`contracts._parse_table` 的 header_rows 上界从 3 扩到 **4**"
            "（新增 `MIN_HEADER_ROWS` / `MAX_HEADER_ROWS`），结清 Task 42 登记的 "
            "`pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` 欠账。"
            "🔴 H1 的契约 / adapter / golden digest **一字未改**（HC-8）——"
            "h1.disposal_check.json 里那段欠账叙述是冻结的历史记录。"
            "🔴 **范式裁决**：走 `phase5_*`，**不照**同循环已注册的 H1（`pilot_h1_grouped_dynamic` "
            "的 `pilot_*` 范式早于行表引擎）；唯一复用 pilot 的是 `oo_crash_neutralization_fn`。"
            "七段公共流程收进 `phase5_h_cycle_common`（H 要接 9 条，抄 9 份就是 9 个漂移面）。"
            "🔴 **幻影码零回退口径在 H 必须改**：G2 的 assert_no_implicit_template_fallback 断言"
            "「幻影码不得命中任何模板」，但实测 9 个幻影码里 `H6A` / `H10A` **同时是真实程序表码**"
            "（固定资产清理实质性程序表H6A / 资产处置损益实质性程序表H10A）⇒ 照 G2 写这两条 provider "
            "会在注册路径上直接抛。正确不变量 = 「不得命中**别的 entry** 的册子」；"
            "本条的 `H9L` 是真幻影码（三条 finder 路径实测全空）。"
            "🔴 **HD-7 缺口**：H9 `publishToTb` 全链路 **0 处** ⇒ 契约 "
            "`review.tb_publish_gate=None` 是**声明**不是遗漏，本 canary **不覆盖发布链**；"
            "发布链首例归 h2-h6-h10-pilot-cross-reference-lanes。"
            "sync 路径对 trial_balance 写次数为 0。"
            "🔴 **HC-11**：`isRelatedParty` / `isConfirmed` / `isTerminated` 是**中文枚举**"
            "（值域 {是,否}，真库实测全为 '否'），**不得**声明为 boolean（回写会把 '否' 写成 "
            "false、前端下拉失配）；`terminatedFromH8` 是 H8 终止租赁流程回传的**跨 entry 派生标记**，"
            "OO 侧编辑必被覆盖 ⇒ 声明 derived。"
            "口径差异如实登记：模板 `U 期后付款` / `V 备注` 有列但 HTML 无字段（不进 field_specs，"
            "照 H1 对占位列 X 的处置）；`contractNo`/`assetDesc`/`ibrRate`/`leaseTerm`/"
            "`isTerminated`/`terminationDate`/`terminatedFromH8` 七个 HTML 有字段但模板无列"
            "（store-only，不映射格）；6 个公式列 json_key **不落库**（前端 load 时重算）。"
            "🔴 `locked` 标志在 H 循环**惰性**：实测 9 张 H 主受管表 sheet 级保护**全部未启用**"
            "（ws.protection.sheet=False / 无密码 / workbook 未锁结构）⇒ 单元格 locked=True "
            "只是 Excel 未设样式时的默认值。本表 locked = E·I·J·K·L·**M**·N 七列而 M（重分类）"
            "无公式且 HTML 侧可编辑 —— 这**不是模板缺陷**，是「locked 无判读价值」的实证。"
            "契约 mode 一律按「该格逐行有没有真公式」判，merge._protection 也只看契约 "
            "mode + formula_mask 不读模板 locked ⇒ 两边口径一致、无需覆盖层。"
            "🔴 HC-8：`H9-2-rows` 被 `useH8CrossSheet.ts` / `useH8DisposalCheck.ts` 跨 entry 消费 "
            "⇒ 键名冻结。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2 卡在同一平台级缺口"
            "（BP-1~BP-3：instrumentation candidate / 人工审核契约 / approved bundle 三缺），"
            "供给就绪后真栈注册。🔴 capability 从 single_onlyoffice → bidirectional 只能由 "
            "`register_from_manifest()` 在注册成功后驱动，**禁止手改 manifest 文件**（HC-1）。"
        ),
    },
    # ── H6 发布链首例（spec: h2-h6-h10-pilot-cross-reference-lanes）──
    {
        "contract_id": "h6.asset_disposal_clearing_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_h6_asset_disposal_clearing"
        ),
        "delivered_by_task": "H6-publish-chain-first",
        "pilot_class": "phase5_asset_disposal_clearing_detail",
        "entry_id": "xlsx/gt-h6-asset-disposal-clearing",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H6 固定资产清理.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**第二条** entry，也是**发布链首例**：H6 的审定数经 "
            "`H6TabAdjudication → useH6Adjudication.publishToTb` 走显式发布门"
            "（POST audit-determination/publish-to-tb，科目 1606，中文二次确认）；"
            "H8/H9 两条 `publishToTb` 全链路 0 处 ⇒ canary 覆盖不到发布链，由本条补上。"
            "🔴 但 sync 路径对 trial_balance 的写次数仍为 **0** —— 发布是用户显式动作，"
            "不是回写副作用；把 materialize/merge 接到 TB 上会绕过二次确认，"
            "违反 tb-writeback-explicit-publish-gate 铁律。"
            "🔴 **与 canary H9 的三处实质差异（照抄会静默出错）**："
            "① `H6A` **不是幻影码** —— 它同时是真实程序表码（册内 sheet "
            "`固定资产清理实质性程序表H6A`），解析到自己的册 ⇒ "
            "`phantom_code_resolves_to_own_workbook=True`；照 G2 的「幻影码不得命中任何模板」"
            "会让本 provider 注册时直接抛。"
            "② 审定期末公式是**资产口径** `L=I+J-K`（H9 是负债口径 `L=I-J+K`）—— "
            "直接复制 H9 的模板会让 H6 审定期末反号。"
            "③ payload 列是 `dual_write_remark_and_conclusion`（H9 是 `remark_only`）。"
            "🔴 **公式列部分落库**：E/I/L 的 json_key 落库、**J/K 不落库**"
            "（前端 load 时 `applyH62BalanceFormulas` 重算）⇒ 回写比对不得按 H9 的"
            "「公式列一律不落库」推演，否则把「store 里本来就没有」误报成「回写丢字段」。"
            "🔴 **HC-6 派生合计 6 键**（H6-2-subtotal-gain-loss / -net-book-value / "
            "-begin-unadjusted / -end-unadjusted / -begin-audited / -end-audited）"
            "与主表同批写出，不参与 roundtrip 比对。"
            "🔴 **HC-8 键名冻结**：`H6-2-rows` 被 h10RelatedH6Pull.ts / "
            "h1SoeClearingH6Pull.ts / h6DisclosureModel.ts 三处跨 entry 消费 ⇒ 本轮只补契约不改键名。"
            "🔴 **真库零载荷**：`H6-2-rows` 在 checklist_responses 无行 ⇒ roundtrip 真实证"
            "需造数据，这正是 canary 选 H9 而非 H6 的原因（如实登记，不粉饰）。"
            "模板 16 列**全部**有 store 字段 ⇒ `template_only_columns` 为空（与 H9 的 U/V 不同）；"
            "反向 20 个 HTML 字段模板无列（含 accDepreciation/tax/netGainLoss/h1Reference/"
            "h10Reference 五个兼容别名 + 派生列 endAdjustment）。"
            "`adapter_registered=False` 同 canary：BP-1~BP-3 属平台缺口，不手改 manifest。"
        ),
    },
    # ── H4 首个四级表头 + 三区块宽表（spec: h4-h8-sub-entry-lanes-…）──
    {
        "contract_id": "h4.engineering_materials_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_h4_engineering_materials"
        ),
        "delivered_by_task": "H4-four-level-header",
        "pilot_class": "phase5_engineering_materials_detail",
        "entry_id": "xlsx/gt-h4-engineering-materials",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H4 工程物资.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**第三条** entry，规模上是前两条的量级之外："
            "🔴 **四级表头**（R8/R9/R10/R11）—— 这是 `contracts.MAX_HEADER_ROWS` 从 3 扩到 4 "
            "之后的**首个真实消费者**（扩容见 commit 91933bd68，结清 Task 42 登记的 "
            "UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE 欠账）；schema 回退到 3 "
            "则本 entry 直接无法表达。H9/H6 都只是两级表头。"
            "🔴 **49 有效内容列 + 三区块**（原值 E..AH / 减值准备 AI..AS / 期末净值 AT..AU），"
            "对比 H9 的 22 列单区块与 H6 的 16 列单区块；max_column=67 是空列尾巴。"
            "🔴 **18 个 template-only 列**，主体是**调整/审定块的数量列与单价列** —— "
            "前端在那些位置只有金额标量。该映射**由代码定死不是命名推测**："
            "`useH4Detail.ts#L63` 注释『调整（金额口径 AJE，对齐 Excel 核实情况）』+ "
            "`#L140 auditedBegin = calcAuditedAmount(row.beginAmount, row.ajeBegin, 0)` "
            "以金额为基。若把 `ajeBegin` 映到数量列 Q，回写会把金额写进数量格，"
            "且单价公式 `=金额/数量` 立刻算出荒谬单价。"
            "**覆盖闭合自检：31 映射 + 18 template-only == 49 有效列**，无重复无交叠"
            "（落在契约 review.column_coverage_closure，判据可复算）。"
            "🔴 **`ajeImpair` 是 store-only**：前端把减值调整压成一个字段，模板却是 "
            "AM 期初调整 + AN 账项增加 + AO 账项减少三列且 AS 走 `=AP+AQ-AR`，"
            "一对三无法确定分摊 ⇒ 不映射任何格，两侧口径差异写进 html_store_note。"
            "🔴 **footer R28 之下还有不受管区域 R29-R34**（`A29='其中：'` + 5 行按类别 "
            "SUMPRODUCT 小计，行标签取 =底稿目录!A9..A13）—— H9/H6 的 footer 之下无内容；"
            "不显式登记（review.unmanaged_regions），merge 可能把它们当数据行覆盖，"
            "一次就把分类小计整块写坏。"
            "🔴 **2 条 `H4T` 子入口**（h4/impairment/H4TabImpairment.vue / H4TabRecoverable.vue）"
            "按 AC 1.6 **复用本 entry 的 adapter** —— 不新建 adapter、不给子入口单独登记契约。"
            "🔴 `H4-3-rows` 登记在 review.sibling_tables_not_managed：它是**另一张表**"
            "（调整分录汇总 H4-3），不是本表的合计副本，也不在本轮受管面 —— "
            "登记它是为了让后续批次不把它误当派生键跳过。"
            "载体族：write/read 皆 `formdata_composable`（H9/H6 都是 host_inline）。"
            "幻影码 `H4E` 是**真**幻影码（三条 finder 路径实测全空；程序表码是 `H4A` 不是 `H4E`），"
            "与 `H6A`/`H10A` 那两个同时是真实程序表码的情形相反。"
            "HD-7：H4 **无** TB 发布门（publishToTb 在 H4 链路 0 处；发布链首例是 H6）。"
            "`adapter_registered=False` 同前两条：BP-1~BP-3 属平台缺口，不手改 manifest。"
        ),
    },
    # ── H8 58 列全 1:1、零 template-only（spec: h4-h8-sub-entry-lanes-…）──
    {
        "contract_id": "h8.right_of_use_assets_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_h8_right_of_use_assets"
        ),
        "delivered_by_task": "H8-full-isomorphic",
        "pilot_class": "phase5_right_of_use_assets_detail",
        "entry_id": "xlsx/gt-h8-right-of-use-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H8 使用权资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**第四条** entry，是剩余各条里最规整的一条："
            "🔴 **58 有效列全部 1:1 映射、`template_only_columns` 为空** —— **全 H 唯一**"
            "（H4 有 18 条、H9 有 2 条）。前端 `H8DetailRow` 的 `cost*`/`dep*`/`impair*` "
            "三族与模板三大区块逐列同构，连『本期租入/租赁负债调整/其他增加/转租赁为融资租赁/"
            "转让或持有待售/其他减少』六个增减去向都一一对上 ⇒ **无需任何审计域裁决**"
            "（对比 H10 与 H3/H5/H7 的结构性不匹配）。"
            "四项闭合自检全绿：58 映射 + 0 template-only == 58 有效列；列序连续 A..BF 无缺口；"
            "17 个公式模板与模板 R12 **逐字**一致；58 个 header_text 与模板最下层表头**逐字**一致。"
            "🔴 **四级表头 + 四大区块**（原值 D8:V8 / 累计折旧 W8:AM8 / 减值准备 AN8:BD8 / "
            "审定净值 BE8:BF9，51 个表头合并域），**数据区 20 行**（R12-R31，全 H 最长）。"
            "🔴 **三处『看着像、其实不同』**（照抄会静默出错，已在 sheet 声明逐条钉住）："
            "①原值块 **3 增 3 减** vs 折旧/减值块 **2 增 3 减** —— 照抄原值块会多映一列、"
            "整块列位右移；②未审期末 `K=SUM(D:G)-SUM(H:J)`（**含期初 D**）vs "
            "`AC=SUM(W:Y)-SUM(Z:AB)`（首格即期初）—— 区块起始列不同，range 端点不能平移；"
            "③`BE`/`BF` 是**审定**净值（`=S-AJ-BA` / `=V-AM-BD`）⇒ 映 netBeginAud/netEndAud，"
            "前端 netBeginUnadj/netEndUnadj 模板**无列**是 store-only —— "
            "按名字直觉映过去会把审定净值写进未审字段。"
            "另：审定减少 `AL=Z+AI+AB+AA+AG+AH` 是**乱序但等价**的模板原式，逐字保留不做整理"
            "（整理等于改模板）。"
            "🔴 **footer R32 之下还有不受管区域 R33-R38**（按类别 SUMPRODUCT 小计）。"
            "与 H4 的同族区块**分组列不同**：H8 按 **A 列**（使用权资产类别）、H4 按 **B 列** ⇒ "
            "守卫不得共用写死的分组列。"
            "🔴 **`H8-2-rows` 的 12 个消费方全在 entry 内**（不是跨 entry）—— 与 H9/H6 的"
            "冻结理由不同，冻结力度更强：改名要同步改 12 个文件，其中 useH8Adjudication / "
            "useH8CrossSheet / useH8Disclosure 三处是审定勾稽与附注推送入口。"
            "（早先按直觉写成 useH9CrossSheet + h8DisclosureSyncPayload 是错的，"
            "按值 grep 零命中；H8↔H9 的联动方向是 H8 读 `H9-2-rows`。）"
            "🔴 **3 条 `H8T` 子入口**按 AC 1.6 复用本 adapter，逐字取 manifest 的 "
            "parent_duplicate entry_id：h8-tab-recoverable / h8-tab-measurement-annual / "
            "h8-tab-measurement-monthly。后两条对应册内**同名两张** sheet "
            "`使用权资产 租赁负债初始及后续计量（按年/按月）H8-6`（HC-5 变体轴），"
            "也是本册裸 IF 的主来源（按月版 361 行 × 16 列）。"
            "（按目录名猜成 H8TabImpairment / H8TabDepreciation* 是错的，manifest 无对应 entry。）"
            "🔴 **HD-7：H8 无 TB 发布门**（publishToTb 全链路 0 处，同 H9）。"
            "`H8-adj-tb-amount-{ending,opening}` 是 **TB 核对种子**不是发布门 —— "
            "它们供审定表比对试算平衡表，不写 TB；sync 对 trial_balance 写 0 次。"
            "另 10 个 sibling 键（H8-1 审定表 7 + H8-8 折旧 1 + TB 核对种子 2）登记在 "
            "review.sibling_tables_not_managed，属另表不在本轮受管面。"
            "幻影码 `H8R` 是**真**幻影码（程序表码是 `H8A`）。"
            "册 465,476 B 全 H 最大。`adapter_registered=False` 同前三条：BP-1~BP-3 属平台缺口。"
        ),
    },
    # ── I6 canary（spec: i-cycle-sync-foundation-and-first-canary · Task 22）──
    {
        "contract_id": "i6.research_development_expense_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_i6_research_development_expense"
        ),
        "delivered_by_task": "I6-canary",
        "pilot_class": "phase5_research_development_expense_detail",
        "entry_id": "xlsx/gt-i6-research-development-expense",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I6 研发费用.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环**首条** entry（spec i-cycle-sync-foundation-and-first-canary，canary = I6）。"
            "I 循环起点：6 条独立 entry 零 provider / 零契约 / 零 representation、**无 pilot**"
            "（四个 pilot 是 B60/D2/H1/G7，逐文件读 review.entry_id 无一条属 I）。"
            "canary 选型硬依据：**真库有非空主表载荷** —— 现算 checklist_responses 的 remark，"
            "I 前缀只 7 个 item_id 有行，6 条主表键里只有 2 条非空"
            "（I5-2-rows 745 B 但 rowId 是 E2E 种子 e2e-i52-contract ⇒ 成色不如 I6 · "
            "**I6-2-detail-rows 194 B / 2 行**），I1/I2/I3/I4 主表键 + I6-2-rows(legacy) 全零；"
            "几何最简（**单级**表头 R8 全 I 最浅 · 数据 R9-18 十行 · 84 公式 · "
            "裸 IF 45 格全 I 最少 · definedName 0 · merged 仅 2）；"
            "🔴 **与 H10-2 / D4-2 高度同构**（12 月度列 B-M + 年度合计 N=SUM(B:M)）⇒ "
            "months/0..months/11 数组路径复用 D4-2 已验通范式，json_path 是唯一数组段真源。"
            "受管 sheet = `明细表I6-2`，公式列 N·Q·R·W（🔴 R 的分母是 footer 绝对引用 $Q$19，"
            "抄成相对引用会让每行占比指向错误分母行）；UUID 列 AA = 有效内容列 26 + 1"
            "（🔴 **不得放 66** —— max_column 是 65，有效与 max 之间 39 列全空，放 66 会让 "
            "OO 打开后列宽错位）。"
            "🔴 **双 footer**：R19 合计（B..Y 各 =SUM(x9:x18)）+ R20「各月比例」"
            "（B..N 各 =IF($N$19=0,0,x19/$N$19)）。R20 是 R19 的**派生**不是第二个合计锚点 ⇒ "
            "引擎 footer_row 只取 R19，契约 review.footer_rows=[19,20] 是**事实声明**"
            "（供 roundtrip 判据知道 R20 不是业务行），两者不得混用。"
            "🔴 **身份 backfill 是 canary 第一道前置**：真库那 2 行原本既无 id 也无 rowId，"
            "useI6Detail.ts#L303 的 raw.id ?? raw.rowId ?? `row-${Date.now()}` 兜底会每次读都"
            "生成新 id、roundtrip 恒判「全删全增」⇒ 已一次性 backfill 为 "
            "i6-detail-bf01-zhptyd / i6-detail-bf02-xplcsy。"
            "🔴 **键名冻结**（IC-17）：I6-2-detail-rows 有 5 个跨 entry 消费方，其中 "
            "h1DepAllocCounterpartPull.ts 属 **H1 pilot**（adapter 已注册、golden 已锁）⇒ "
            "本条任何改动完成后回归 H1 契约 golden digest，且**不得修改 H1 的契约/adapter/golden**。"
            "另有 legacy alias I6-2-rows（LEGACY_STORAGE_KEY 真存在）⇒ 契约声明"
            "「读认两键、写只写主键」，删它历史数据读不出。"
            "🔴 **BP-5②禁接**：useI6FormData.ts（448 行）含完整 checklist GET/PUT + "
            "trial-balance/writeback 管道，但 import 生产/测试消费**双零**（按 import 路径字面量"
            "三形态现算，禁符号名 grep）⇒ 契约 forbidden_carriers 显式禁接。接到它上面会让宿主"
            "行为一点不变而守卫因「文件确实被改了」全绿 = **假绿第①源**。"
            "🔴 **范式裁决**：走 `phase5_*`；七段公共流程**直接复用** phase5_h_cycle_common"
            "（实测零 H 硬编码，类名带 H 只是历史命名）⇒ I 不再造第二份骨架。"
            "唯一复用 pilot 的是 `oo_crash_neutralization_fn`（IC-9，per-file 挂，本册 45 格；"
            "整册统一挂不行 —— I1 的 321 与 I6 的 45 差 7 倍）。"
            "🔴 **GC-9 在 I 反向**：I 循环 **6/6 全有 TB 发布门**（与 H 的 H8/H9 完全无门相反）⇒ "
            "canary 直接覆盖发布链，不外移首例。I6 的门在 useI6Adjudication.ts（publishToTb ×3）"
            "+ i6/core/I6TabAdjudication.vue（×2），只走 POST "
            "/api/workpapers/{wpId}/audit-determination/publish-to-tb + 二次确认。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/H9 卡在同一平台级缺口"
            "（BP-1~BP-3：instrumentation candidate / 人工审核契约 / approved bundle 三缺），"
            "供给就绪后真栈注册。🔴 capability 从 single_onlyoffice → bidirectional 只能由 "
            "`register_from_manifest()` 在注册成功后驱动，**禁止手改 manifest 文件**（IC-1）。"
        ),
    },
    # ── I2（spec: i2-i4-i5-carrier-and-structure-exceptions · Task 17）────────
    {
        "contract_id": "i2.development_expenditure_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_i2_development_expenditure"
        ),
        "delivered_by_task": "I2-lane2",
        "pilot_class": "phase5_development_expenditure_detail",
        "entry_id": "xlsx/gt-i2-development-expenditure",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I2 开发支出.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第二条（canary I6 之后）。选它先接的理由：**除 canary 外几何最简的单区表**"
            "（单区无派生区 · 有效列 20 即 A..T · 数据 R13-22 十行 · footer R23）。"
            "受管 sheet = `明细表I2-2`，🔴 **三级表头 R10/R11/R12**（header_rows=3，"
            "各列 header_text 取该列最深非空标题 —— A/Q/S/T 在 R10 · B/G/H/I/L/M/P 在 R11 · "
            "C/D/E/F/J/K/N/O 在 R12；照「统一取 leaf 行」会让 12 列取到 None）；"
            "公式列 G·L·M·N·O·P·R（🔴 G 与 P 是**减两项**口径「期初+增加−计入资产−计入损益」，"
            "抄成「期初+增加−减少」会漏一个减项）；UUID 列 U = 有效 20 + 1"
            "（🔴 **不得放 62** —— max_column 61，有效与 max 之间 41 列全空，全 I 差距最大）。"
            "🔴 **footer 非单一形态**：B..P 十四格纯 SUM，但 **R23 例外是 =P23-Q23** 套用行公式"
            "（同 I3-2 R23 的 row_formula_applied，本表只此一格）⇒ roundtrip 判据不得对 footer "
            "做统一形态假设。"
            "🔴 **I2 是 I 循环唯一「双例外」entry**：①唯一**缺二级 UI 门控**"
            "（宿主 isOoAvailable 与「仅结构化视图」tag 命中均 0 ⇒ OO 探测失败时切换按钮照样显示，"
            "违反 AC 1.5；判据写「全 slice 都有二级门控」会在本条上静默恒真、恰好漏掉最严重那条）"
            "②唯一**发布门不在 composable**（useI2Adjudication.ts 里 publishToTb **0 命中**，"
            "门在 I2TabAdjudication.vue#L384 自建）⇒ 契约 gate_layer='host_tab'；"
            "「I 循环 6/6 全有发布门」是 **entry 维度**成立的结论，判据按 composable 找门会假红。"
            "🔴 **第三个例外：有第二写路径且是活代码** —— useI2FormData.ts（501 行）import "
            "生产消费现算 **4**（宿主 + useI2Adjudication + useI2Impairment + "
            "i2/core/I2TabAdjudication.vue）。对比 useI4FormData(394 行)/useI6FormData(448 行) "
            "**双零消费**是死代码 ⇒ 三个文件名同型但只有 I2 那个是活的，一刀切「I 的 FormData "
            "都是孤儿」会把 I2 的写路径删掉、保存静默失效。两条写路径打同一端点同一 item 形状 "
            "{item_id, conclusion, remark}，注册 adapter 后不应分叉。"
            "🔴 **主表键 I2-2-rows 是跨 lane 冻结键**：lane 1 的 useI1AdditionCheck.ts#L250-251 "
            "读它且读法是 `?.remark ?? ?.conclusion` ⇒ ①不得改键名 ②不得在未通知 lane 1 的"
            "情况下改 payload 列语义；i2ConsistencyModel.ts#L213 的前缀映射 "
            "'I2-2-': ['I2-2-rows'] 也依赖它，改名会同时打断一致性检查前缀表。"
            "🔴 **IC-12 全 I 最严重的 wp_index 问题落在本条**：真库 wp_index 里 `I2-1` "
            "**一码两名两底稿** —— `商誉减值测试`（×1，业务上属 **I3**）与 `开发支出审定表`（×3）"
            "指完全不同的底稿（比 H 的 H1-2 同底稿不同名严重）⇒ 契约 source_ref 只用 "
            "{workbook_sha256, sheet_name}，**禁任何 wp_index 来源字段**。"
            "🔴 **IC-5 两个 verdict 同属本 entry**：CD-5 主表无 impl 分类常量 ⇒ "
            "NO_IMPL_CLASSIFICATION_BY_DESIGN/clean；CD-6 defaultPerCapitaPeers ⇒ "
            "HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF/scanned_and_classified_not_a_defect"
            "（不是缺陷 —— 「同业人均数」对照表的默认行数种子，模板本来就没有对应分类区间）。"
            "status 维度上两者**不相加**。"
            "🔴 **IC-6 在本 entry 命中 0** 且不是漏扫（8 个位置化 site 全在 lane 1 的 {I1,I3}）"
            "⇒ 按 IC-20 断言「现算 0」但**不宣称该维度通过**。"
            "**源模板真源断链登记不修**：明细表I2-2!A17 是字面「数据资源」（不是 =底稿目录!A18）"
            "⇒ 改 A18 不传播；另 2 处同型在 I1 归 lane 1。不改模板字节。"
            "IC-9 per-file 裸 IF **113**（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，"
            "总 777）⇒ 整册统一挂不行，最重与最轻差 7 倍。"
            "真库 `I2-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
    # ── I4（spec: i2-i4-i5-carrier-and-structure-exceptions · Task 17）────────
    {
        "contract_id": "i4.long_term_prepaid_detail",
        "provider_module": "app.services.workpaper_sync.phase5_i4_long_term_prepaid",
        "delivered_by_task": "I4-lane2",
        "pilot_class": "phase5_long_term_prepaid_detail",
        "entry_id": "xlsx/gt-i4-long-term-prepaid",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I4 长期待摊费用.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第三条。受管 sheet = `明细表I4-2`，🔴 **三级表头 R8/R9/R10**（header_rows=3，"
            "各列 header_text 取该列最深非空标题 —— A/B/C/D/E/T/U 在 R8 · F/G/J/K/L/O/P/S 在 R9 · "
            "H/I/M/N/Q/R 在 R10）；数据 R11-22 十二行；footer R23 合计（E..S 各 =SUM(x11:x22)，"
            "A/B/C/D/T/U 无合计）；公式列 J·O·P·Q·R·S（🔴 J 与 S 是**减两项**口径"
            "「期初+增加−本期摊销−其他减少」）；UUID 列 W = 有效 22 + 1。"
            "🔴 **双区（IC-19）**：第 2 区 `R24「其中：」+ R25-28` 四行是**派生区** —— A 列逐格 "
            "`=底稿目录!A9`..`A12`、E..J 等列是 **ArrayFormula** 按 B 列类别回汇总第 1 区 ⇒ "
            "标 `derived`、**不纳入业务行比对**（否则 roundtrip 会把「第 1 区改动引起的派生区重算」"
            "判成用户编辑了派生区）；且 `editable_labels=false` —— 允许用户改标签会被下次 render "
            "从 `底稿目录` 静默覆盖。"
            "🔴 **本条与 I5 是 definedName「基线不增长」口径的唯一实证场**：本册 **476**"
            "（全 I 最多；I5 334、其余四册 I1/I2/I3/I6 全 0，合计 810）⇒ 判据 SHALL 用"
            "「登记基线 + 断言不增长」，**不得**照抄 H 循环 HC-14 的「断言全 0」—— 那在 "
            "I1/I2/I3/I6 上恒真悄悄通过，**只有 I4/I5 会打红**。"
            "🔴 **不删这 476 个**：是模板公式的命名引用，删了会让 max_column 内的公式整片失效；"
            "只声明「同步时不新增、不改写」。"
            "🔴 **BP-5 双零消费死代码禁接**：`useI4FormData.ts`（394 行）import 生产/测试消费"
            "**双零**（按 import 路径字面量三形态现算，禁符号名 grep —— I 循环有 4 处注释链式"
            "提及 dual-mode composable，符号名口径会把注释当消费边）。**对比 I2**："
            "`useI2FormData.ts`（501 行）消费计数 **4** 是**活代码**（_doSave 内真 PUT = I2 的"
            "第二写路径）—— 三个 FormData 文件名同型（i2/i4/i6）但**只有 I2 那个是活的**，"
            "一刀切「I 的 FormData 都是孤儿」会把 I2 的写路径删掉、保存静默失效。"
            "⇒ 契约 forbidden_carriers 禁接；🔴 **本轮不删文件**（跨 spec 清理动作，"
            "与并发会话有冲突风险；禁接已足够防误用）。"
            "🔴 **payload mode `dual_write` 未被真库证实**：slice 记 "
            "dual_write_remark_and_conclusion_for_status_marker，但真库 I 循环 **7 行全部 "
            "remark_only**（conclusion 全 NULL）⇒ 标 `unverified_in_live_db`，"
            "**不得**把 slice 声明当已验证事实；落地时须断言写 conclusion 列**不破坏** "
            "remark_only 读侧（I2 的第二写路径与 lane 1 的 useI1AdditionCheck 都读 conclusion 兜底）。"
            "🔴 **CD-8 = BP-8②**：impl `CATEGORY_OPTIONS` **6 条** vs 源 `明细表I4-2!A11` 真读"
            "**仅 1 条**（`使用权资产改良及维护支出`；A9/A10 空 + A12:A22 全空）⇒ verdict "
            "PREFIX_MATCH_WITH_UNSOURCED_TAIL，无真源尾部 **3 条**（租入固定资产改良支出 / "
            "固定资产大修理支出 / 开办费）。修法归**业务确认**（是否属长期待摊费用的合法分类是"
            "会计判断）⇒ 本轮登记不修。"
            "🔴 **删行 API 属 id 族**（`useI4Detail.ts#L672 removeRow(rowId: string)` 先 "
            "findIndex 再 splice），与同 lane 的 I2 `removeRow(index: number)` 下标族不同 ⇒ "
            "本 lane 是 **1:2 跨两族**，而 lane 1 两条 entry **100% 下标族** ⇒ 两个 lane "
            "**不得复用同一个签名断言**，否则一边必然假红或假绿。"
            "🔴 **IC-6 在本 entry 命中 0** 且不是漏扫（8 个位置化 site 全在 lane 1 的 {I1,I3}）；"
            "**IC-18 derived_total_keys 现算 0** 且已裁非漏扫（I1 8 / I2 2 / I6 3 · I3/I4/I5 皆 0）"
            "⇒ 两项均按 IC-20 空分母纪律断言「现算 0」但**不宣称该维度通过**。"
            "**模板侧其他字段不进本契约**：`I4DetailRow` 的摊销政策族（amortizationMethod / "
            "totalMonths / accAmortization / …）与基础族（occurDate / contractNo / startDate / …）"
            "属 `摊销测算I4-6` 与 `摊销测算表I4-7（工作量法）` 两张后置 sheet"
            "（🔴 后者禁 strip 括号）—— Requirement 6.1 禁止无来源自造字段。"
            "IC-9 per-file 裸 IF **186**（全 I 第二重；I1 321 / I4 186 / I2 113 / I3 63 / "
            "I5 49 / I6 45，总 777）⇒ 整册统一挂不行。"
            "真库 `I4-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I2/I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
    # ── I5（spec: i2-i4-i5-carrier-and-structure-exceptions · Task 11/13/17）──
    {
        "contract_id": "i5.other_noncurrent_assets_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_i5_other_noncurrent_assets"
        ),
        "delivered_by_task": "I5-lane2",
        "pilot_class": "phase5_other_noncurrent_assets_detail",
        "entry_id": "xlsx/gt-i5-other-noncurrent-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I5 其他非流动资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第四条，**结构最深的一条**。受管 sheet = `明细表I5-2`（两级表头 R8/R9，全 I 最浅）。"
            "🔴 **三区完全镜像 —— 平台新形态（同一行同时在三个区）**："
            "R10 区标题`其他非流动资产原值：` + 区① R11-21 十一行（A 列**字面标签**）+ footer R22 · "
            "R23 区标题`减值准备：` + 区② R24-34 十一行（🔴 A 列 **=A11..=A21 镜像公式**）+ footer R35 · "
            "R36 区标题`净值：` + 区③ R37-47 十一行（🔴 **A..O 全列 =x11-x24 逐格派生**）+ footer R48。"
            "与既有两种多区范式**都不同** —— `phase5_d3_04_analysis` 的「一区一 store 键」"
            "（各区行集互斥）与 G9/G1 的 `region_filter`（行按字段值**分到**某一个区）都是"
            "「一行属一个区」；本表是**一行的 gross 在区①、impairment 在区②、净值在区③派生**。"
            "⇒ 处置 = **两个 spec 共享同一 store_item_id `I5-2-rows`**（契约两个 table："
            "`other_noncurrent_gross_rows` 10 字段 / `other_noncurrent_impairment_rows` 9 字段），"
            "json_key 走嵌套路径 `gross/*` 与 `impairment/*`；**区③不建 spec**。"
            "`all_store_item_ids()` 去重后仍只有 1 个 item、`all_managed_sheet_names()` 只有 1 张 sheet。"
            "🔴 **区②的 A 列是 FORMULA 不是 editable**（=A11 镜像）⇒ 它进 formula_columns 而"
            "**不映射任何 store 字段**；否则 merge 会拿 HTML 的 None 覆盖镜像公式、"
            "让减值区行标签整列变空。区①的 A 列才是 editable 的 `projectName`。"
            "🔴 **区③ fully_derived_region** ⇒ 整区跳过不接受用户输入；若允许写入，"
            "用户改的净值会在下次 render 被 =x11-x24 覆盖、**静默丢失**。"
            "🔴 **三区行数必须相同（各 11）且按行序镜像对应**；变异「把某一区改成 10 行」SHALL 打红"
            "—— 镜像一破，区③就会按错行去减。三个 footer（R22/R35/R48）**分别**标 kind，"
            "不得只声明第一个。"
            "🔴 **I5 是 IC-2 载体二分的直接证据**：载体族 **formdata_composable**（全 I 唯一，"
            "写在 `useI5FormData.ts`），宿主 `GtI5OtherNoncurrentAssets.vue`（**289 行，全 I 最短**）"
            "里**无任何 http / api client import**（现算 0）⇒ 变异「按 F 版守卫要求宿主自带 "
            "GET+PUT」SHALL 在本条上打红。`http_import`=**0** 的解释是「I5 无导入入口，"
            "靠 composable 建行」⇒ 按 IC-20 断言「现算 0 且不是漏扫」但**不宣称该维度通过** "
            "—— 没有解释的 0 就是漏扫的伪装。"
            "🔴 **IE-4 内置行「删除」= 原位重置且曾换掉 rowId**："
            "`useI5Detail.ts#L821-839` 的 removeRow 在 `row.isBuiltin` 分支走 "
            "`rows[idx] = emptyI5DetailRow({projectName, name, isBuiltin, indexRef})`，"
            "传入字段里**原本不含 rowId**，而 emptyI5DetailRow 内 #L305 `rowId: generateRowId()` "
            "⇒ 重置后 rowId 变了且 _persist() 把新 rowId 落库。双重影响：①行数不变"
            "（按行数或 projectName 比对会认为没变）②rowId 变了（按 rowId 比对会认为"
            "「删一行 + 增一行」）⇒ roundtrip 会把「重置的内置行」当成「已删的业务行」。"
            "**双保险已落地**：修复①（治未来）#L826 传 `rowId: row.rowId`；"
            "修复②（治历史）契约声明 `builtin_row_identity_field='projectName'` —— "
            "实现自己就在用它反查 indexRef（#L830）。判据 SHALL 断言**两个身份字段都存在**，"
            "只声明 rowId 一侧 SHALL 打红。"
            "🔴 **真库载荷是 E2E 种子不可作基线**：`I5-2-rows` **745 B**（全 I 最大）但 "
            "`rowId == 'e2e-i52-contract'` —— **不符 `i52-` 生成器格式、是 E2E 测试种子**"
            "（随 E2E 套件可被重置）⇒ 标 `live_payload_is_e2e_seed_not_business_data`；"
            "`passthrough` mode **未被业务数据证实**（真库 I 循环 7 行全 remark_only）；"
            "roundtrip 用**合成载荷**并标 synthetic_payload。"
            "🔴 **本条与 I4 是 definedName「基线不增长」口径的唯一实证场**：本册 **334**"
            "（I4 476；其余四册全 0，合计 810）⇒ 照抄 H 循环 HC-14 的「断言全 0」在那四册上"
            "恒真悄悄通过，**只有 I4/I5 会打红**。**不删**（模板公式的命名引用）。"
            "**CD-3 分类 clean（唯一正例之一）**：impl `I5_BUILTIN_CATEGORIES` **10 条** vs "
            "源 `明细表I5-2!A11:A20` 真读 10 格，**有序等值 10/10** ⇒ MATCH/clean；"
            "边界 A21=`……`（可扩位）· A22=`合计`。"
            "两区同形公式列 E=SUM(B:C)-D · L=B+F+G · M=C+H+J · N=D+I+K · O=L+M-N"
            "（由同一处 `_formula_templates()` 生成 —— 抄两遍就是两个漂移面）；"
            "有效内容列 17 即 A..Q / max_column 26 ⇒ UUID 放 R / **334 公式（全 I 最多）**。"
            "store-only 四字段（isBuiltin / indexRef / name / remark）在 17 有效列里无对应列。"
            "🔴 **删行 API 属 id 族**（`removeRow(rowId: string)`）⇒ 本 lane **1:2 跨两族**"
            "（I2 index / I4+I5 identity），而 lane 1 两条 entry **100% 下标族** ⇒ "
            "两个 lane **不得复用同一个签名断言**。"
            "🔴 **IC-6 命中 0** 且非漏扫（8 个 site 全在 lane 1）；**IC-18 derived_total_keys "
            "现算 0** 且已裁非漏扫 ⇒ 两项均按 IC-20 断言「现算 0」但不宣称通过。"
            "IC-9 per-file 裸 IF **49**（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，总 777）。"
            "`adapter_registered=False`：同 I2/I4/I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
    # ── I3（spec: i1-i3-disclosure-positional-identity-… · Task 13/15）────────
    {
        "contract_id": "i3.goodwill_detail",
        "provider_module": "app.services.workpaper_sync.phase5_i3_goodwill",
        "delivered_by_task": "I3-lane1",
        "pilot_class": "phase5_goodwill_detail",
        "entry_id": "xlsx/gt-i3-goodwill",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I3 商誉.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第五条（lane 1 两条之一）。受管 sheet = `明细表I3-2`。"
            "🔴 **四级表头 R10/R11/R12/R13 ⇒ header_rows=4**，正好用到平台上界"
            "（H9 那轮从 3 扩到 4，结清 Task 42 登记的 "
            "pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE 欠账）。"
            "数据 R14-22 九行；有效内容列 **30 == max_column 30**（无空列间隙，与 I2 的 20/61 "
            "差 41 列、I6 的 26/65 差 39 列形成对照）⇒ UUID 放 AE。"
            "🔴 **左右两表同一行**：左表 A..P 商誉原值滚动 + 右表 Q..AD 减值准备滚动；"
            "`Q` 列是**镜像** `=A{r}` ⇒ 进 formula_columns 且**不映射 store 字段**"
            "（同 I5 区② A 列口径）。11 个公式列 I·M·N·O·P·Q·W·AA·AB·AC·AD；"
            "🔴 `AB`/`AC` 是**三项相加**口径（本期增加 = S+Y+T / 本期减少 = U+Z+V），"
            "抄成两项会漏掉「其他增加 T」与「其他减少 V」。"
            "🔴 **B/C 两列在数据区全空**（B 是间隔列；C11='发生日期' 只是表头，C14..C22 全 None）"
            "⇒ 两列都不进 field_specs。"
            "🔴 **footer R23 三形态混行** ⇒ `footer_kind=row_formula_applied` + "
            "`footer_convention_split`：14 格纯 SUM（E·G·J·K·L·R..Z）+ **5 格套用行公式**"
            "（I23=SUM(D23:E23)-G23 · M23=D23+J23 · N23=E23+K23 · O23=G23+L23 · "
            "P23=M23+N23-O23）+ **4 格引错区间**（缺陷①）。照 I1/I2 的 pure_sum 口径去验"
            "本表 R23 会因「不是 SUM 开头」而**假红**。"
            "🔴 **两处模板真实缺陷，两种不同处置（不得混写）**："
            "**①（IC-14/ID-3）`AA23:AD23` 四格引错区间 ⇒ `overlay_fixed`**：实际 "
            "=SUM(<列>27:<列>30) 应为 =SUM(<列>14:<列>22)；根因 R27-29 是**编制说明文本行**"
            "（B27='编制说明：'）、R30 **超出 max_row(29)** ⇒ 区间完全落在数据区外 ⇒ "
            "**减值准备区审定数四列（期初数/本期增加/本期减少/期末数）合计恒 0**；"
            "同行左侧 S23..Z23 全部正确 ⇒ 四格错法一致 = **复制粘贴错误**。"
            "走**模板覆盖层**（FC-5 的第 **5** 个例外；前四个 F2-26!J9 / F5-7!G31 / G5-2 45 格 / "
            "G5-1!B35），`backend/wp_templates/` 字节不动（改字节会破坏与纸质底稿的对应关系，"
            "且 sha256 变了会让 6 条 I entry 的 source_ref 全失效），覆盖层**只替换这 4 格**。"
            "🔴 判据载荷必须是「**只有减值准备区（R14:R22 的 AA:AD）有数、其他区为 0**」—— "
            "用「全区都有数」时修复前后合计都非 0（R27:R30 可能被别的公式带出值）⇒ **假绿**；"
            "用「全区都是 0」则恒真；同时断言 R23 的**非 AA:AD 列**前后取值**不变**（不误伤）。"
            "**②（本轮新发现）`I14` 缺公式 ⇒ `registered_not_fixed`**：I15..I18 逐行都有 "
            "=SUM(Dx:Ex)-Gx，唯**数据区首行 I14 是 None** ⇒ 首行的「商誉原值未审期末」不会自动计算。"
            "处置与①**不同**（不开第二个覆盖层例外）：前端 `costEnding` 本就按同一套公式重算并落库 "
            "⇒ merge 时该格由 formula_columns 重新写入，**不影响回写正确性**；但须登记，"
            "否则后来者会以为「I 列公式逐行齐全」。"
            "🔴 **mount=4 是全 I 唯一 ≠2**（legacyOO=6 亦全 I 最多）⇒ `force_component_type` "
            "判据 SHALL 覆盖**全部 4 个挂载点**；变异「只验 1 个」SHALL 打红 —— 这是"
            "「分母为空的重言式」的**反面**：分母是 4 却只验 1，同样是假绿。"
            "断言注册 adapter 后 legacyOO 分支不再被走到，但**不删代码**（删它会牵动 OO 不可用时"
            "的降级路径）。"
            "🔴 **BP-6：全 I 8 处位置化 site 里 I3 占 7**，但全在 `useI3Disclosure.ts`"
            "（族 A′ #L488 `cgu-${i}` + 族 B #L441/#L463/#L503 + 族 D #L665/#L725）与 "
            "`i3/impairment/I3TabRecoverableTest.vue#L686`（族 B）—— **披露层 / 减值测试层**。"
            "本 sheet 的行身份是 `useI3Detail.ts` 的 rowId（族 A 安全生成）⇒ 本契约 "
            "positional_identity_sites 为空，🔴 但**不得**据此推断「I3 无位置化问题」—— "
            "那 7 处的修复归 lane 1 的 Task 3~9。"
            "🔴 **删行属下标族**（`useI3Detail.ts#L580 removeRow(rowIndex: number)`）⇒ "
            "**lane 1 两条 entry 100% 下标族**，而 lane 2 是 1:2 跨两族 ⇒ 两 lane **不得复用"
            "同一签名断言**。🔴 **本 lane 是唯一「下标族删行 × 位置化行身份」双重叠** ⇒ "
            "有一条组合判据「删中间一行后剩余行 rowId 集合不变」，两个单独判据都抓不到。"
            "🔴 **排除 sheet 三张**：`参考－商誉减值测试示例`（**全角连字符 `－`** U+FF0D、"
            "**非 hidden**、104 行/114 公式 —— 是**示例数据不是项目数据**，同步会把示例数字当审定数；"
            "🔴 变异「用半角连字符匹配」SHALL 找不到而打红）· `市场平均收益率2017`"
            "（hidden 167 行 —— **固定年份基准表**不随项目变）· `GT_Custom`（hidden 平台自用）。"
            "**CD-7 分类 clean**：I3 无 impl 分类常量 ⇒ SOURCE_ITSELF_DERIVES_FROM_DETAIL。"
            "`I3DetailRow` 的 Section 2（入账测算 30+ 字段）与 Section 3（基础信息）属 "
            "`入账价值测算表I3-4` / `商誉减值测试I3-6` / `可收回金额测试I3-7` 三张后置 sheet，"
            "**不进本契约**（Requirement 6.1 禁止无来源自造字段）。"
            "`defined_name_baseline=0` 但判据仍须用「基线不增长」口径 —— 同一套判据到 lane 2 的 "
            "I4(476)/I5(334) 会直接假红。**IC-18 derived_total_keys 现算 0** 且已裁非漏扫。"
            "IC-9 per-file 裸 IF **63**（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，总 777）。"
            "真库 `I3-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I2/I4/I5/I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
    # ── I1（spec: i1-i3-disclosure-positional-identity-… · Task 14）───────────
    {
        "contract_id": "i1.intangible_assets_detail",
        "provider_module": "app.services.workpaper_sync.phase5_i1_intangible_assets",
        "delivered_by_task": "I1-lane1",
        "pilot_class": "phase5_intangible_assets_detail",
        "entry_id": "xlsx/gt-i1-intangible-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I1 无形资产、累计摊销及减值准备.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第六条（**6/6 全覆盖**）。受管 sheet = `明细表I1-2`，**全 I 最宽的一张**。"
            "🔴 **四个「全 I 最」**：有效列 **47**（A..AU；I3 30 / I4 22 / I2 20 / I5 17 / I6 26）· "
            "merged **72**（I3 47 / I4 27 / I2 21 / I5 8 / I6 2）· 裸 IF **321**"
            "（I4 186 / I2 113 / I3 63 / I5 49 / I6 45）· `derived_total_keys` **8**"
            "（I2 2 / I6 3 / I3·I4·I5 各 0）；反过来数据区**仅 6 行是全 I 最少**。"
            "🔴 **四级表头 R8/R9/R10/R11 ⇒ header_rows=4**（与 I3 同为平台上界）。"
            "结构：三大滚动区各 13 列（原值 C-O / 累计摊销 P-AB / 减值准备 AC-AO）+ "
            "净值区 AP-AS（**四列全公式** AP=C-P-AC · AQ=L-Y-AL · AR=H-U-AH · AS=O-AB-AO）+ "
            "合规区 AT/AU（文本）。**28 个受管字段 / 19 个公式列**。"
            "🔴 **三大区结构同构但公式口径各不相同，用同一套模板会算错两区**："
            "原值区审定增减是**两项**（M=D+J / N=F+K）；摊销/减值区是**三项**"
            "（Z=Q+W+R / AA=S+X+T / AM=AD+AJ+AE / AN=AF+AK+AG，含「其他增加 R/AE」与"
            "「其他减少 T/AG」）；🔴 **减值区未审期末是两个 SUM 相减**"
            "（AH=SUM(AC:AE)-SUM(AF:AG)）而非前两区的 SUM(x:y)-z —— 抄前两区会漏掉「其他减少 AG」。"
            "🔴 **footer R18 是全 I 唯一单一形态**：`C18..AS18` **41 格全部纯 SUM**"
            "（=SUM(x12:x17)）⇒ 本表可以安全用 pure_sum 口径，但**该口径不得复用到 I2/I3**"
            "（I2 有 1 格 R23=P23-Q23 例外、I3 有 5 格套用行公式 + 4 格引错区间）。"
            "🔴 **双区（IC-19/ID-4）**：第 2 区 `R19「其中：」+ R20-30` **11 行**是派生区 —— "
            "A 列逐格 `=底稿目录!A9`..`A19`，C/D/F/H/I/J/K 等列是 **ArrayFormula / SUMPRODUCT**"
            "（`=SUMPRODUCT(($B$12:$B$17=$A20)*(F$12:F$17))`）按 **B 列类别**回汇总第 1 区 ⇒ "
            "标 `derived` + `editable_labels=false`（允许用户改标签会被下次 render 从 `底稿目录` "
            "静默覆盖）。数据区 A 列模板预填的是**占位符** A/B/C/D/… 不是业务名。"
            "🔴 **源模板真源断链（本 sheet 内 1 处）**：`明细表I1-2!A29` 是**字面** `数据资源`"
            "（其余 10 行都是 =底稿目录!Ax）⇒ 改 `底稿目录!A18` **不传播**到 R29。"
            "另 2 处同型：`附注披露信息（上市公司）!K10`（本册另一 sheet）与 `明细表I2-2!A17`（I2）。"
            "登记不修，不改模板字节。"
            "🔴 **CD-1 impl 边曾是双定义（ID-2 本轮新发现，已收敛）**："
            "`I1_DEFAULT_CATEGORIES` 曾在 `i1CategoryScope.ts#L19`（`I1CategorySlot[]` 有 "
            "key/label/seq/removable）与 `useI1Adjudication.ts#L105`（纯中文串数组）**两处独立定义**，"
            "两边 11 条 label **有序完全一致**但是**两个独立真源** —— 改一处不传播。"
            "平台在 `i1ListedDisclosureModel.ts#L41` 收敛过一次却**漏掉了 useI1Adjudication.ts**。"
            "✅ **已收敛**为 `I1_DEFAULT_CATEGORIES.map(c => c.label)` 派生，保留导出名与 "
            "`as const` 语义；零回归 `i1CategoryScope.spec.ts` / `useI1Adjudication.spec.ts` "
            "**16 tests passed**。🔴 判据仍 SHALL 同时比对两处导出并断言第二处不再有独立字面量；"
            "变异「只改 i1CategoryScope.ts 的第 8 条 `软件`」SHALL 打红。"
            "🔴 **BP-7 五项差异（登记不修）**：impl `I1_SOE_CATEGORIES` **12 条** vs 源 "
            "`附注披露信息（国有企业）!A9:A19` **11 格** —— 条数 12↔11 · `软件` 位次 1↔8 · "
            "`房屋使用权`↔`住房使用权` · `特许权`/`采矿权`↔`特许经营权`/`矿产权` · 多出 `探矿权`。"
            "🔴 第二真源 `note_template_soe.json` 里 `采矿权`/`探矿权`/`房屋使用权` 命中 **0** "
            "⇒ **两个真源都不支持 impl 的写法**。修法归**业务确认**（国企附注该用哪套分类名是"
            "会计披露口径问题），且改常量会同时改附注列头（涉已归档的附注同步 spec）⇒ 登记不修。"
            "🔴 **BP-6：全 I 8 处位置化 site 里 I1 占 1 处** —— `i1DisclosureEnhance.ts#L241` "
            "`tc-i18-${r.rowId || i}`（族 B 下标兜底，在**披露增强层**）。本 sheet 的行身份是 "
            "`useI1Detail.ts` 的 rowId（族 A 安全生成）⇒ 本契约 sites 为空，那 1 处归 lane 1 Task 5。"
            "🔴 **删行属下标族**（`useI1Detail.ts#L623 removeRow(rowIndex: number)`）⇒ "
            "**lane 1 两条 entry 100% 下标族**，与 lane 2 的 1:2 跨两族不同 ⇒ 判据不得复用；"
            "**lane 1 是唯一「下标族删行 × 位置化行身份」双重叠**。"
            "🔴 **IC-11 命名陷阱本册命中三条**：①**`审定表I1` 不带 `-1`**（其余 5 册是 "
            "`审定表I{n}-1`）⇒ 按 `审定表I{n}-1` 模式定位失配 ②`摊销测算表（不含减值）I1-10"
            "（剩余年限法）` **两个括号后缀** ⇒ 禁 strip ③`附注披露信息（上市公司）`/`（国有企业）` "
            "**多「信息」二字**（其余 5 册是 `附注披露（…）`）⇒ 统一模式匹配在 I1 上失配。"
            "🔴 `prefill_formula_mapping.json` 的 16 条 I mapping **已正确用 sheet 全名** ⇒ "
            "契约照此口径，不另造。"
            "🔴 **IC-16 门控判据须按 toolbar 选择器定位**：本宿主 `el-segmented` 共 **3** 个，"
            "其中 `#L171` 是 **Tab 内部分段控件**不是模式切换器 ⇒ 判据 SHALL 按 "
            "`i1-header-toolbar` 截区块再判，全文件 grep 会误判成有第二个模式切换器。"
            "**12 个 store-only 字段**分两类：①摊销政策族（acquisitionDate / usefulLifeMonths / "
            "salvageRate / amortizationMethod / indefiniteLife / notReadyForUse）属 "
            "`使用寿命检查表I1-7` / `摊销测算表（不含减值）I1-10（剩余年限法）` / "
            "`摊销测算表（含减值）I1-11` 三张后置 sheet ②兼容/派生字段（amortTransferOut = "
            "amortDisposal + amortOtherDecrease · impairmentReversal · netBegin/netValue/"
            "auditedNetBegin/auditedNetEnd 对应 AP-AS 四个全公式列）。"
            "🔴 `derived_total_keys` **8 个**注意 `I1-9-alloc-totals` 是**复数** —— "
            "正则只写 `-total$` 会漏它。UUID 列 AV = 有效 47 + 1（🔴 不得放 57 —— max_column 56，"
            "有效与 max 之间 9 列全空）。`defined_name_baseline=0` 但判据仍须用「基线不增长」口径。"
            "真库 `I1-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I2/I3/I4/I5/I6 卡 BP-1~BP-3 平台级缺口。"
            "🔴 **本条交付后 I 循环 6/6 provider 全覆盖**（i1/i2/i3/i4/i5/i6），"
            "表头层级覆盖 1/2/3/4 四种（i6 单级 · i5 两级 · i2+i4 三级 · i1+i3 四级=平台上界）。"
        ),
    },
    # ── J1（spec: j-cycle-sync-foundation-and-first-canary · Task 22）─────────
    {
        "contract_id": "j1.accrual_check_short_term",
        "provider_module": "app.services.workpaper_sync.phase5_j1_employee_compensation",
        "delivered_by_task": "J-T22",
        "pilot_class": "phase5_accrual_check_short_term",
        "entry_id": "xlsx/j1/gt-j1-employee-compensation",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "J/J1 应付职工薪酬.xlsx",
        "adapter_registered": False,
        "reason": (
            "J 循环 canary，**manifest 里 J 只有 2 条 entry**（1 独立 + 1 parent_duplicate）⇒ "
            "本条即 J 唯一可独立发布的 entry。受管 sheet = `计提情况检查表J1-6` 短期薪酬区。"
            "🔴 **canary 硬标准须改口径** —— D~I 六轮用的「primary managed table 真库有非空载荷」"
            "在 J **不成立**：`J1-2-detail-{shortTerm,postEmployment,severance}` 三键 + "
            "`J1-1-rows`（审定表）+ `J1-3-adjustment-rows`（调整分录）真库**全部无行**。"
            "改成四项「真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组」，"
            "`J1-6-short-term` 真库 **3473 B（全 J 最大）**且满足其余三项 ⇒ 选它。"
            "三个落选：`J1-disc-soe-short-term`（1325 B **且有真金额**，但披露层叠 5 个最难形态 —— "
            "双变体 / 49 硬编码序号 id / **同 id 跨变体语义不同**（SOE `st-7`=其他 vs Listed "
            "`st-7`=住房公积金）/ 第三条写路径写**另一张表** / 与明细表**非行对行映射** 12 行←20 行）· "
            "`J1-8-voucher-check`（911 B，但属 **parent_duplicate** ⇒ 不独立发布 contract/bundle/"
            "candidate/evidence）· `J1-2-detail-*`（primary managed table 真库 0 行）。"
            "🔴 **三条逆风如实登记**：①3473 B 载荷的**金额字段全 0**"
            "（baseAmount/rate/estimated/actual/diff 全 0，baseName/baseIndex/diffReason/"
            "conclusion 全空串）= 「骨架已落库、业务未填」⇒ roundtrip 第一轮只验结构、"
            "第二轮须另造带金额合成载荷验 `G=ROUND(D*F,2)` 与 `I=G-H` ②RD-5 三边校验缺口"
            "须在 canary 内先补 ③同 Tab `J1-6-questions` 真库 **901 B 是 AI 生成 markdown 长文本**"
            "（5 元素字符串数组，首元素含 `###` 标题与列表）⇒ representation 须区分"
            "`structured_row_array` 与 `free_text_array` 两种形态，按行数组解析会失败。"
            "🔴 **JC-2 载体是平台第三种族 `shared_platform_persistence_adapter`** —— 写路径在 "
            "`composables/workpaper/useChecklistPersistence.ts`（消费边现算 **23**），client 是 "
            "**`api` from `@/services/apiProxy`**（不是 `http` from `@/utils/http`）。"
            "两条对照反证：按 H 的「载体里必须有 `http.put`」核本适配器**假红**（它用 `api.put`）· "
            "按 I 的「宿主必须 import `@/utils/http`」核 J1 宿主**假红**（259 行宿主两种 client "
            "import 命中**均为 0**）⇒ 判据 SHALL 按 entry 声明的 `write_client` 名字去找 "
            "`{client}.put(`，**不写死 `http`**。"
            "🔴 **JC-3 写路径按端点字面量判定，禁按函数名** —— 符号名 `publishToTb` 在全 J 域命中 "
            "**0**，而端点 `publish-to-tb` 命中 **2**（同一文件 `j1/core/J1TabAdjudication.vue` "
            "内两处）：「按函数名得 0、按端点得 1 个文件」是本条判据存在的**全部理由**。"
            "⇒ **GC-9 在 J 是 1/1 有门**（推翻「J 无发布门」误判），canary **可以**覆盖发布链。"
            "四类端点现算：checklist-responses PUT **13 文件**（主写）· publish-to-tb POST **1** · "
            "disclosure-notes/sync POST **4**（写**另一张表**）· ai/generate-text POST **16**"
            "（AI 生成，**非持久化**，不得计入写路径）。"
            "🔴 **几何**：两级表头 R15/R16 ⇒ **header_rows=2**（R15 是 项目/计提基数/计提比例/"
            "应提金额/实际计提数/差异/差异原因/结论，R16 只有 C=名称·D=金额·E=索引 三个"
            "「计提基数」子列）· 分区标题行 R14 `（1）短期薪酬` · 数据 **R17-R35（19 行）** · "
            "**8 受管字段 / 2 公式列**（G=ROUND(D*F,2) 应提金额 · I=G-H 差异，19 行同形）· "
            "有效内容列 **11 即 A..K** 且 max_column **也是 11（两者相等）** ⇒ UUID 放 L · "
            "63 公式 · merged 17 · definedName **0**。"
            "🔴 **`footer_rows: []` 本 sheet 无 footer 合计行** —— R36 只有 "
            "G36=`=ROUND(D36*F36,2)` 与 I36=`=G36-H36` 两个公式但 **A36 无标签**，"
            "R37 已是第二分区标题 `（2）离职后福利中设定提存计划…` ⇒ R36 是**模板预留的第 20 行**。"
            "引擎 spec 结构体必填 footer_row ⇒ 给 36 占位 + 契约显式 "
            "`footer_carries_total_formula=False`（`footer_anchor` 解析为 None）；"
            "判据 SHALL 断言该行**无 `合计` 标签**，"
            "变异「把它当 footer 验合计公式」SHALL 打红。判业务行按 **A 列非空**，"
            "🔴 **不得**套同册 `明细表J1-2 ` 的「B 列 + 三 footer」口径。"
            "🔴 **RD-5 本轮新登记**：impl `SHORT_TERM_DEFAULTS` **19 项** vs 模板 `A17:A35` "
            "**19 格** —— 行数一致但**内容 10 处不等**，三类分开记：①序号分隔符 **9 处**"
            "（模板全角 `．` U+FF0E / impl 半角 `.`）②缩进前缀 **9 处**（模板带 3 个全角空格 "
            "`\\u3000` / impl 靠 `indent: 1` 字段表达）③🔴 **单元格内换行符 1 处**"
            "（模板 `八、辞退福利\\n（因解除劳动关系给予的补偿）` / impl 写成一行）。"
            "🔴 **禁标点归一化** —— `NFKC` 会同时洗掉 RD-2 的 5 处与本条的 9 处 ⇒ 逐格**字节**比对。"
            "修哪一侧属业务判断（模板是审计准则产物 / impl 是用户可见文案）⇒ 登记不修，"
            "`header_text` 取**模板原字节**。"
            "🔴 **JC-10 sheet 名禁 strip 任何空格**：本册**尾部空格 2 张**（`审定表J1-1 ` / "
            "`明细表J1-2 `）· **名中空格 3 张**（`应付职工薪酬实质性程序表 J1A` 等）· "
            "🔴 **跨 sheet 引用里带空格且单引号包裹**（`审定表J1-1 !B8 = ='明细表J1-2 '!C13`）"
            "⇒ 重写公式 SHALL 保留空格与单引号。本 canary sheet `计提情况检查表J1-6` 无空格，"
            "但同册其他 sheet 有 ⇒ 契约仍须登记。sheet 数 **23 = 业务 15 + retired 7 + "
            "GT_Custom 1**（四向等值比对；retired 7 张全 hidden）。"
            "🔴 **JC-11 `J1-10` 一码两义**：→ `辞退福利检查表J1-10`（**visible**, 48 行）+ "
            "`股份支付检查表J1-10-删除`（hidden, 66 行）—— 两张**完全不同业务**的表，不是版本变体 "
            "⇒ 按尾码定位 SHALL 带 **visible 过滤**，变异「只按尾码匹配」SHALL 取到两张而打红。"
            "另 `J1A` → `…程序表 J1A`(visible) + `…J1A-原版`(hidden) 才是版本变体。"
            "🔴 **跨循环程序表串册 2 处（slice 漏记，登记不修）**：本册 hidden 的 "
            "`应付职工薪酬实质性程序表 L1A-原` 是 **L 循环**程序表串进 J 册；J2 册 hidden 的 "
            "`长期应付职工薪酬实质性程序表 L2A` 同型。"
            "🔴 **JC-17 J 循环完全自闭（两侧都验）**：①J 的键无一个被非 J 路径文件消费 "
            "②J 文件里无任何非 J 循环的键字面量 ⇒ **HC-8 / IC-17 的跨循环键冻结在 J 不命中**"
            "（重大简化：改键名无跨循环风险）。🔴 **但端点跨循环复用 1 处** —— "
            "`composables/workpaper/j1/useJ1VoucherOcr.ts` 调 **D4 的** "
            "`POST /api/workpapers/{wpId}/d4/contract-ocr` ⇒ 冻结对象从「键」换成「**端点**」，"
            "且 **FC-8 在 J 命中**（不是不适用）：宿主层 `ocr` 命中 0 成立，但 composable 层"
            "有真 OCR 调用 ⇒ 判据扫描范围 SHALL 含 composable 层。"
            "🔴 **BP-11 键真源实际是 4 文件 5 处声明**（slice 只记「两份」）：`useJ1Detail.ts` "
            "前缀 `J1-2-detail-` + `storageKey()` 派生（**写方**）· `useJ1Adjudication.ts` 的 "
            "`J1_DETAIL_SECTION_KEYS` 三字面量 · `J1TabAccrualCheck.vue` 的 `DETAIL_KEYS` "
            "三字面量 · `J1TabAllocationCheck.vue` 的 `DETAIL_KEYS` · `useJ1DisclosureSections.ts` "
            "三处 `readJson('J1-2-detail-…')` 内联 ⇒ 判据 SHALL **五处同时比对**，"
            "变异「只改前缀」SHALL 打红。🔴 本 canary **不接**这三键（真库全空）⇒ 归后续批次。"
            "🔴 **IC-9 同源裸 IF per-file 挂**：整册 J1 **224**（`审定表J1-1 ` 56 / "
            "`与同行业对比分析表J1-5` 60 / `月度分析表J1-4` 16 等），但**本 canary sheet 为 0** —— "
            "中性化是 per-file（整册就地改写 substrate 副本）⇒ 即使受管表干净也必须挂。"
            "🔴 **definedName 基线 0 但判据须用「不增长」口径** —— 同册 0，可 J2 是 **37**（断链 30）/"
            "J3 是 **502**（断链 479，是跨循环复制残留 `_1固定资产数据库_筛选打印` / `_.dbf` / "
            "`AS2DocOpenMode` 等）⇒ 写死「必须为 0」到下游 lane 直接假红；J2/J3 的处置归下游 lane "
            "且**不删**（删会让公式整片失效）。"
            "🔴 **`derived_total_keys` J1 侧现算 5 个**（J1-1-audited-total · "
            "J1-1-audited-begin-total · J1-7-total-admin-expense · J1-7-total-production-cost · "
            "J1-7-total-selling-expense）—— 正则 SHALL 覆盖 **`-total-` 出现在中间**的形态，"
            "只写 `total$` 会漏 `J1-7-total-*` 三个；另 `J2-listed-summary`/`J2-soe-summary` 属 J2。"
            "🔴 **位置化行身份本 sheet 为空**：`AccrualRow.id` 形态 `acr-{ts}-{i}-{rnd}` 属安全族。"
            "J 循环 family_a（纯序号真落库）唯一一处是 `J2TabAdjustment` 的 `id: i + 1` → "
            "`J2-3-entries`（真库 171 B 载荷里 `\"id\":1` **已确证落库**）⇒ 归下游 lane。"
            "披露层另有 **49 个硬编码序号 id**（SOE 25 + Listed 24）—— **登记但不判为位置化缺陷**"
            "（id 与 label 写在**同一个对象字面量**里，绑定静态不随数组顺序变；报成位置化会造 "
            "49 个假缺陷）。"
            "🔴 **prefill 四处缺陷登记不修**（属另一条产品链路）：`sheet: '审定表J1-1'` "
            "**缺尾部空格**（模板真名带空格）⇒ 按名定位必失配 · `sheet: '明细表J1-2 '` 那条 "
            "`cells: []` **空数组**=死配置 · `=PREV('J1','分析程序J1-3','审定数')` 引用的 "
            "`分析程序J1-3` **在 23 张 sheet 里不存在** · J3 一条 `wp_name: '股份支付审定表'` 但 "
            "**J3 册没有审定表**。J 的 prefill mapping 现算 **10 条**，字段名是 **`sheet`** 不是 "
            "`sheet_name`，全部 `cells` 型 / `items` 全 0（⇒ **IC-11/FC-11 的 items 死配置在 J "
            "不命中**）；`wp_code` 只 `J1`/`J2`/`J3` 三值（非子码）。"
            "唯一 store-only 字段 `indent` 是缩进层级（0/1）—— 模板用**全角空格前缀**表达缩进"
            "（RD-5 类②），HTML 侧用独立字段 ⇒ 不映射格。"
            "`ws.protection.sheet=False` ⇒ locked 惰性，mode 按「该格逐行有没有真公式」判。"
            "`adapter_registered=False`：同 I 循环 6 条卡 BP-1~BP-3 平台级缺口"
            "（无真 OO 9.4 ⇒ roundtrip 与人工审核均未完成）。"
        ),
    },
)
