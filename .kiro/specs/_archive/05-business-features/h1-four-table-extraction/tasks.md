# Implementation Plan

## Overview

7 波实现 H1 四表取数扩展。Wave 0 先落安全网与可用性探测（数据条件已在需求/设计阶段实证，本波把结论固化为可执行探测与 characterization 基线），随后按"明细取数 → 序时账核对 → 折旧账面数 → 上下文 → 报表行映射 → 测试门"推进。全程灰度 `H1_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False，任一波可独立回退。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "desc": "灰度开关 + 零回归基线 + 可用性探测" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "后端明细级取数载荷" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "desc": "前端 helper + H1-2 seed + 来源面板" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "序时账增减核对" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "desc": "折旧账面数取数与分配核对" },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "desc": "项目上下文（关联方/资产负债表日）" },
    { "wave": 6, "tasks": ["7.1", "7.2"], "desc": "审定表报表行规则映射" },
    { "wave": 7, "tasks": ["8.1", "8.2", "8.3"], "desc": "属性测试 + 契约守卫 + live 验证" }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 灰度开关、零回归基线与可用性探测

- [x] 1.1 新增灰度开关与 characterization 基线
  - `backend/app/core/config.py` 加 `H1_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`
  - 新建 `backend/tests/test_h1_extraction_characterization.py`：锁定开关关闭时 `render()` 返回键集合与现状一致（不含 `h1_four_table_prefill`），并锁定既有 `adjudication_category_prefill` / `tb_values` 结构不变
  - _Requirements: 6.1, 6.4_

- [x] 1.2 折旧对方科目可用性探测
  - `_h1_fixed_assets.py` 加 `_probe_counterpart_availability(ctx)`：统计 1602 分录 `counterpart_account` 填充率，阈值 0.8；不足时返回 `{available: False, fill_rate, reason}`（中文原因含填充率与"凭证为合并记账"说明）
  - 单测覆盖：填充率 0 / 0.09 / 0.95 三档，以及无 1602 分录时 available=False
  - _Requirements: 3.4, 8.3_

- [x] 1.3 明细取数可行性契约测试（宁缺勿造前置）
  - 断言 `tb_aux_balance` 不作为 H1 明细取数来源（代码中无 H1 → tb_aux_balance 查询），确保 Card_Level_Detail 不被编造
  - _Requirements: 8.1_

- [x] 2. Wave 1 — 后端明细级取数载荷

- [x] 2.1 实现 `_build_h1_detail_prefill`
  - 复用已有 `_leaf_codes` 做叶子过滤、`_classify_fa_category` 做分类归类
  - **按分类聚合一行**（原值/累计折旧/减值叶子归入同一分类行，避免按单科目码拆行产生"折旧行原值为 0"的错乱）：`category/source_codes[]` + cost/dep/impair 各 `{begin,debit,credit,end}`（发生额 abs 归一，备抵 begin/end 取 abs）+ `formula` 文本
  - 输出 `totals`，无数据返回 `{"rows": [], "totals": {...0}}`
  - _Requirements: 1.1, 1.2, 1.6, 8.2_

- [x] 2.2 render 灰度接入
  - `render()` 在开关为 True 时追加 `h1_four_table_prefill = {enabled, detail, ledger_movement, counterpart}`；False 时输出不变
  - 三段各自 try/except fail-open
  - 单测：开关两态输出对比 + 单段抛错时 render 仍成功
  - _Requirements: 6.1, 6.3, 7.3_

- [x] 3. Wave 2 — 前端 helper、H1-2 种子填充与来源面板

- [x] 3.1 新建 `composables/h1FourTablePrefill.ts`
  - `buildDetailSeedRows(payload)`：映射为 `DetailRow[]`，经 `createEmptyDetailRow` + `recalcDetailRow` 保证公式列自洽；Card_Level 字段留空；`remark` 标注来源与科目码
  - 单测：分类映射、备抵期末自洽、空载荷返回 `[]`、Card_Level 字段恒空
  - _Requirements: 1.1, 1.5, 8.1_

- [x] 3.2 主入口 Persist_First 种子填充
  - `GtH1FixedAssets.vue` `onMounted`：仅当 `H1-2-rows` 缺失/为空数组时写入 seed 行；provide 取数载荷供各 tab
  - 单测/属性测试：已有行时不覆盖
  - _Requirements: 1.3, 6.2_

- [x] 3.3 来源面板与「重新取数」
  - 新建 `h1/core/H1FourTableSourcePanel.vue`（科目码/公式/期初增减期末/空态原因）
  - `H1TabDetail.vue` 顶部挂载；「重新取数」二次确认后覆盖取数行、保留手工新增行
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 4. Wave 3 — 明细增减与序时账核对

- [x] 4.1 后端 `_build_h1_ledger_movement`
  - `tb_ledger` 1601 借/贷方合计，经数据集有效过滤；无分录返回 `{"available": False}`
  - _Requirements: 2.1, 3.1_

- [x] 4.2 前端核对展示
  - `h1FourTablePrefill.buildMovementReconcile` 纯函数 + `H1TabDetail` 只读告警（差异 > 1 元）
  - `available:false` 时显示"未取到序时账发生额"
  - _Requirements: 2.2, 2.3, 2.4_

- [x] 5. Wave 4 — 折旧账面数取数与分配核对

- [x] 5.1 H1-12 账面折旧一键带入
  - 复用 `h1_depreciation_monthly`（已修 `voucher_date` + `get_active_filter`）
  - 三个折旧 tab（不含减值/含减值/多方法）以 Persist_First 带入账面折旧总额
  - _Requirements: 3.1, 3.2_

- [x] 5.2 H1-13 分配合计核对
  - 分配合计 vs 序时账折旧合计差异告警（只读），与既有对方底稿拉取结果并列展示
  - _Requirements: 3.3, 3.5, 2.4_

- [x] 5.3 按对方科目归集（条件性）
  - 新增 resolver `h1_depreciation_by_counterpart`：`available` 为 true 才返回分布，否则返回原因
  - 前端仅在 available 时渲染该区块，否则显示中文原因提示
  - _Requirements: 3.4, 3.5, 8.3_

- [x] 6. Wave 5 — 项目上下文补齐

- [x] 6.1 render 注入 `related_parties` 与 `bs_date`
  - 查 `related_party_registry`（`is_deleted=false`），fail-open 返回 `[]`
  - `bs_date` 取项目审计期末
  - _Requirements: 4.1_

- [x] 6.2 H1-18 关联方漏项告警
  - 「登记表有但本表未登记」差集告警 + 一键补充为待填行；空清单显示空态不产告警
  - _Requirements: 4.2, 4.3_

- [x] 6.3 H1-17 年检过期用注入 bs_date
  - 优先使用 `project_context.bs_date`，缺失回退现有推导
  - _Requirements: 4.4_

- [x] 7. Wave 6 — 审定表试算核对走报表行规则映射

- [x] 7.1 后端接入 `resolve_report_line_account_codes`
  - 解析固定资产报表行科目码；未配置回退 1601/1602/1603；输出 `project_context.tb_source_codes`
  - 单测：有配置 / 无配置（回退）两态
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 7.2 H1-1 溯源展示
  - 试算核对区展示所用科目码；映射含明细未覆盖科目时如实显示差异
  - _Requirements: 5.3, 5.4_

- [x] 8. Wave 7 — 测试门、契约守卫与 live 验证

- [x] 8.1 属性测试补齐
  - 覆盖 Property 1-13（叶子过滤 / Persist_First / 归一 / 空数据 / 灰度等价 / fail-open / available 语义 / 只读核对 / 数据集隔离 / 报表映射回退 / 关联方空态 / Card_Level 不编造）
  - _Requirements: 9.1_

- [x] 8.2 契约守卫
  - 断言 H1 后端四表查询统一经数据集有效过滤入口；断言明细取数只有一个入口函数（无第二套口径）
  - _Requirements: 9.2, 3.1_

- [x] 8.3 全量回归与 live 验证
  - 现有 H1 前后端测试全绿；开关两态 render 对比
  - 对已导入余额表的真实项目跑进程内脚本，核对 `detail.totals` 与 `trial_balance` 1601/1602 一致，跑完清理临时脚本
  - _Requirements: 6.4, 1.1_

- [x]* 8.4 Playwright 端到端（需灰度开启的实例化项目）
  - H1-2 空表 → seed 行 → 来源面板 → 重新取数 → 增减核对告警；H1-12 带入账面折旧；H1-18 漏项告警
  - 条件不满足时如实标注留待，不伪造通过
  - _Requirements: 7.1, 7.2, 2.2_

## Notes

- **宁缺勿造是硬约束**：`tb_aux_balance` 无资产卡片维度、序时账对方科目填充率 9% 且凭证为合并记账，二者均已实证 → 卡片级明细与折旧费用归属默认不做自动取数，只如实提示原因。
- **不新增存储键**：H1-2 沿用 `H1-2-rows`，避免第二真源；取数与手工数据靠行 `remark` 来源标注区分。
- **复用不新造**：叶子过滤 `_leaf_codes`、分类归类 `_classify_fa_category`、折旧月度 resolver、`report_account_mapping`、来源面板范式（E1）全部复用现成实现。
- 本 spec 不改 H1 内部各表之间既有"带入"链路（H1-2 → H1-4/7/8/9/10/16~19/披露表），只让 H1-2 自身多一个四表来源。
- 迁移：本特性**无数据库迁移**（只读四表 + 复用既有存储键）。
