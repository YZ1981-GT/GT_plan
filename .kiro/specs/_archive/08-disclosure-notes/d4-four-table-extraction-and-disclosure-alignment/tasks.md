# Implementation Plan: D4 营业收入四表取数与披露/附注对齐

## Overview

8 个 wave、29 项任务。Wave 1 是全部后续的地基（取数纯函数 + resolver 口径），Wave 3（附注模板）与 Wave 6（公式预设）可与前端并行，Wave 8 实测不可省。

改动面：后端新建 2 模块 + 改 2 文件 + 2 幂等脚本；前端新建 2 composable + 重写 1 映射 + 改 5 文件；守卫 8 个测试文件 + 2 个 CI job。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "取数根基（后端纯函数 + resolver 口径纠正）",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"],
      "blocks": [2, 3, 4, 5, 6]
    },
    {
      "wave": 2,
      "name": "render 输出（预填 + 溯源）",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "blocks": [4, 6]
    },
    {
      "wave": 3,
      "name": "附注模板结构（幂等脚本 + 后端守卫）",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "blocks": [5]
    },
    {
      "wave": 4,
      "name": "前端消费（审定表 + 溯源面板）",
      "tasks": ["4.1", "4.2", "4.3"],
      "blocks": [7]
    },
    {
      "wave": 5,
      "name": "披露表重建（列结构 + 缺失表 + 载荷）",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
      "blocks": [7]
    },
    {
      "wave": 6,
      "name": "公式预设重写",
      "tasks": ["6.1", "6.2", "6.3"],
      "blocks": [7]
    },
    {
      "wave": 7,
      "name": "UI 铁律 + AI + 守卫 + CI",
      "tasks": ["7.1", "7.2", "7.3", "7.4"],
      "blocks": [8]
    },
    {
      "wave": 8,
      "name": "实测与收口",
      "tasks": ["8.1", "8.2", "8.3", "8.4"],
      "blocks": []
    }
  ]
}
```

## Tasks

### Wave 1 — 取数根基

- [x] 1.1 新建 `backend/app/services/d4_extraction/account_scope.py`：`D4AccountScope` / `resolve_d4_accounts`（走 `four_table` 共享件 + `IS-001`/`IS-002` + 区间兜底 + `account_mapping` 反解）/ `build_d4_source_codes`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7_
- [x] 1.2 同模块新增 `pair_revenue_cost_leaves`（后缀优先 + 名称校验非否决 + 双向缺口标记）
  - _Requirements: 2.4, 2.5_
- [x] 1.3 新建 `backend/app/services/d4_extraction/occurrence.py`：`ledger_occurrence_expr`（tb_ledger 单侧 + `COALESCE`）/ `normalize_trial_balance_pl`。**范围严格收窄**——`tb_balance` 侧符号约定与父额勾稽一律走共享件 `resolve_leaf_totals(absolute=True)`（该函数已明确「发生额无方向语义 → 原样求和」），禁在 D4 再造方向判定
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 2.1_
- [x] 1.4 改造 `_d4_revenue.py` 四个 resolver：全部 `get_active_filter`；月度/按产品改单侧发生额；`d4_analysis_indicators` 改走 `resolve_d4_accounts` + 符号归一；上期缺失返 `None`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1_
- [x] 1.5 守卫 `test_d4_account_scope.py` + `test_d4_occunce.py`（PBT + 反向自检：打乱配对优先级须失败、旧净额口径须命中恒 0 缺陷、替身 `get_active_filter` 返 `sa.true()`）
  - _Requirements: 9.2, 9.3, 9.4_

### Wave 2 — render 输出

- [x] 2.1 `_d4_operating_revenue.py` 新增纯函数 `build_d4_tb_values` / `build_d4_adjudication_prefill`（动态行、按标准码分主营/其他段、手工优先）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_
- [x] 2.2 新增 `build_d4_segment_prefill`（镜像配对 → 分行业披露行）
  - _Requirements: 4.2_
- [x] 2.3 render 输出 `tb_values` / `adjudication_prefill` / `segment_prefill` / `tb_source_codes`；推翻并改写既有「宁缺勿造」注释，写明推翻依据
  - _Requirements: 2.6, 3.1_
- [x] 2.4 守卫 `test_d4_render_prefill.py`（真实签名 await 调用断言非零 + 替身按绑定参数区分收入/成本 + 无叶子时逐字节等价）
  - _Requirements: 9.2, 9.3, 9.4_

### Wave 3 — 附注模板结构

- [x] 3.1 新建 `backend/scripts/fix/fix_note_d4_revenue_structure.py`（`--dry-run`/`--check`，用 `_note_structure_kit`）：两版 11 表补 `columns`（两级 `group` / 单级 `flat`）
  - _Requirements: 5.1, 5.2_
- [x] 3.2 同脚本：删 `header_label` 假行（（4）表两连）；表名改名走 `aliases`（（4）分解信息、（6）正名）；（6）年度列改审计年度派生；试运行表行名修正 + 删多余合计行
  - _Requirements: 5.3, 5.4, 5.5, 5.6_
- [x] 3.3 同脚本：补 `guidance`（只取源模板红字 R57-R62 / R66 / R71-R77 / R81，纯文本）；`text_sections` 上市 10 段标题化、国企补 (1)~(7) 与说明段
  - _Requirements: 5.7, 5.8, 5.9_
- [x] 3.4 守卫 `test_note_d4_revenue_structure.py`（openpyxl 直读源 xlsx 三向比对 + 归一函数 + 反向自检 + guidance 禁 markdown）
  - _Requirements: 9.1, 9.9_

### Wave 4 — 前端消费（审定表）

- [x] 4.1 新建 `composables/d4AccountScope.ts`（运行态取 `tb_source_codes`，常量仅兜底/展示；清零各文件写死科目码）
  - _Requirements: 2.6_
- [x] 4.2 `useD4Adjudication.ts` 接 `adjudication_prefill` + `dynamicAdjudicationRows` 共享件 + `previewSeedFromPrefill`（新子科目自动插行 / 金额变化弹确认 / 手工永不覆盖）
  - _Requirements: 3.2, 3.4, 3.5_
- [x] 4.3 `D4TabAdjudication.vue` 加「从四表库带入未审数」按钮 + `WpFourTableSourcePanel` 溯源面板（消 dead output）
  - _Requirements: 2.6, 3.7_

### Wave 5 — 披露表重建

- [x] 5.1 新建 `composables/d4DisclosureModel.ts`：（1）（2）（3）（8）4 数据列引擎；（4）列转置 + 动态类别列（稳定 key `{slot}_{seq}`）；（6）动态年度列 + 合计派生
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.7_
- [x] 5.2 上市 Tab 补上期两列（与国企对齐）；两版（3）叶子列名按变体分取；删死代码类型 `Top5CustomerRow`/`ContractBalanceRow`
  - _Requirements: 4.2, 4.3, 4.8_
- [x] 5.3 两版 Tab 新增（4）列转置区块（类别可增删改名）
  - _Requirements: 4.4_
- [x] 5.4 两版 Tab 新增（6）剩余履约义务结构化区块；上市 Tab 新增（8）试运行销售收入区块
  - _Requirements: 4.5, 4.6_
- [x] 5.5 重写 `d4NoteSectionMap.ts`：表名对齐源模板、两级 `group`、补（6）（8）、`_removed_table_keys` 求差集、`_note_texts` 带中文 title 并过滤空文本
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
- [x] 5.6 契约 `d4NoteSubtableContract.spec.ts`（接共享 helper P1~P6 + 两版列名不得统一 + （8）仅上市 + flat 双侧一致）+ `d4DisclosureModel.spec.ts`（含 PBT）
  - _Requirements: 9.1, 9.5, 9.6_

### Wave 6 — 公式预设

- [x] 6.1 新建 `backend/scripts/fix/fix_d4_prefill_presets.py`（`--dry-run`/`--check`）：4 条余额口径改 `'本期发生额'`；区间改 `'6001~6099'`；`6051` 单列；补 `6401`/`6402` 侧；每块补 `sheet_name`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
- [x] 6.2 同脚本：新增两个披露 sheet 预设块；纠正贴错标签块（`营业收入明细表` → 真实 tab）；删口径与维度双错的 `TB_AUX` 条目；审定表补 `WP()` 引用明细表
  - _Requirements: 7.5, 7.6, 7.7_
- [x] 6.3 守卫 `test_d4_formula_presets.py`（口径 / 科目属于 `IS-001`·`IS-002` 集合 / `(sheet, cell_ref)` 唯一 / 防成环 / 语法合法）
  - _Requirements: 7.8, 9.2_

### Wave 7 — UI 铁律 + AI + 守卫

- [x] 7.1 两版 Tab 33 个裸 `el-input type="number"` → `WpAmountInput`；2 处 `toLocaleString` → `displayPrefs.fmtAmount()`（setup 顶层 inject，禁从 stores 命名导入）
  - _Requirements: 8.1, 8.2_
- [x] 7.2 8 个文本域接 AI（走 `wpAiText` 共享件，`context` 为 `dict[str,str]`）+ 后端 `_SECTION_PROMPTS`/`_SUPPORTED_SECTIONS` 登记（每条 ≥20 字含「不得虚构」）+ 前端联合类型 + `AI_TARGETS` 四处齐备
  - _Requirements: 8.3, 8.4_
- [x] 7.3 宿主 `GtD4OperatingRevenue.vue` 透传 `:html-data` + 接 `useHostApplicableStandards`；核查并消除自调度
  - _Requirements: 8.5, 8.6_
- [x] 7.4 源码级守卫 `d4FourTableWiring.spec.ts`（无写死科目码 / 无自调度 / 金额控件归零 / AI 四处齐备 / builder 零入参 / D4 不引入账龄档位；先 `stripComments()` + 反向自检）+ 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE` + 新增 CI job `note-d4-structure` / `d4-four-table-extraction`
  - _Requirements: 9.5, 9.6, 9.8, 9.9_

### Wave 8 — 实测与收口

- [x] 8.1 真实 DB 直跑 render 三类项目：多 dataset（`0ec33ac9`，验数据集隔离与 2.01 倍双算已消除）、负值存储（`df5b8403`，验符号归一）、镜像有缺口（`2aa00f57`，验成本列留空）
  - _Requirements: 1.4, 1.5, 2.5_
- [x] 8.2 浏览器 + postgres 只读实测：审定表「从四表库带入」→ 动态行按客户实际科目建好；披露表填数 → 推送 → 附注两版子表数/列元数据/`_column_groups`/`text_content` 逐项核对
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.7_
- [x] 8.3 复原全部实测数据（附注键集、`last_sync_at` 回 NULL、`checklist_responses` 清理），并核对与未触碰项目逐字一致
  - _Requirements: 9.7_
  - **结论：无需复原 —— Tasks 8.1/8.2 全部为只读验证，数据库未受任何写入影响。**
  - postgres 验证（3 项全 PASS）：
    1. 5 条 D4 disclosure_notes（`五、62` ×1 + `八、64` ×4）：`last_sync_at` 全 NULL、`sub_table_data` 不存在、`_source`/`_last_sync_sheet`/`text_content`/`_note_texts` 均不存在
    2. 6 条 D4 checklist_responses（`D4-2-rows`×2 / `D4-3-rows` / `D4-4-rows` / `D4-disc-soe-tb-balances` / `D4-disc-listed-tb-balances`）：`updated_at` 最晚 2026-07-27 04:00:52，全部早于本次实测会话
    3. 灰度开关默认 OFF + 浏览器验证未点"同步到附注" + render 验证脚本纯 SELECT → 无写入路径
- [x] 8.4 全量测试（后端 D4 相关 + 前端 workpaper）、清理本会话 `tmp_*` 诊断产物、更新 memory 与 `.kiro/specs/INDEX.md`
  - _Requirements: 9.8_
  - **测试结果**：后端 124 passed / 1 skipped / 0 failed；前端 18 files / 492 passed / 0 failed。
  - **已清理**：`backend/tmp_d4_live_verify.py` + `backend/tmp_d4_browser_verify.py`
  - **INDEX.md 已更新**：D4 spec 进度 → 33/33

## Notes

### 立项实证摘要（供后续会话复核，勿凭推断改动）

**源模板**（`D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`）
- 上市披露 sheet A1:I85 共 8 小节；国企 A1:S72 共 7 小节（无试运行销售收入）
- （1）（2）（3）（8）= 5 列两级；（4）= 9 列列转置（`B45:I45` 顶层「本期发生额」+ 4 类别各 colspan2）；（6）= 4 列动态年度
- （3）叶子列名两版不同：上市 R37「主营业务收入/主营业务成本」vs 国企 R31「收入/成本」
- 源模板笔误留证：上市 R29 小计公式 `=SUM(B24:B28)-B24-B25-B26`（等价 B27+B28），语义上小计应为各明细行之和 → 实现按语义正确处理并留注释
- D4-1 审定表主营/其他各 4 行空白可扩行（R8:R11 / R14:R17）

**科目映射**
- `IS-001 = SUM_TB('6001~6099','本期发生额')`、`IS-002 = SUM_TB('6401~6499','本期发生额')`，四准则一致，**均为区间**
- `account_mapping` 逐项目反解齐全；`6001` 与 `6401` 子科目后缀完全镜像
- `.16` 名称差异：收入侧「医疗收入」/ 成本侧「医疗支出」→ 后缀优先、名称非否决
- `2aa00f57` 的 `6001.15 物业与租赁` 有收入无成本 → 成本列必须允许 null

**已实证缺陷（改造前基线）**
- `SUM(credit_amount - debit_amount)` 在 10 项目中 8 个返回 NULL（对侧列存 NULL）→ D4-2 按月/按产品取数恒为 0
- 7/10 项目 `SUM(credit) == SUM(debit)` 精确相等（结转损益）→ 净额口径结构性恒 0
- `0ec33ac9` 裸查 tb_ledger 6001 贷方 1,801,755,477.21 vs `trial_balance` 895,804,876.83 = **2.01 倍**（跨数据集双算）
- `df5b8403` 的 `trial_balance` 6001 = **-38,258,743.63**（负数存贷方性质）
- 附注两版 11 表 `columns` 全 0、`guidance` 全空、`_aligned_by` 为 None
- 上市 `text_sections` 10 段全裸标题；国企仅 4 段
- 公式预设 4 条用余额口径；6 个块 `sheet=None`；两个披露 sheet 零预设
- 两个披露 Tab 共 33 个裸 `el-input type="number"`、0 个 `WpAmountInput`、0 个 AI

**无存量污染**：全库 `五、62`/`八、64` 共 5 条，`last_sync_at` 全 NULL、`sub_table_data` 全不存在 → 结构改动安全，无需清理脚本。附带记录：上市项目 `0ec33ac9` 的 `五、62` 连 `_tables` 都是 0（soe 侧为 5），seed 骨架本身也缺。

### 与账龄枚举的关系（用户明确要求，需在守卫中固化）
D4 营业收入为损益类，源模板 8 小节**均无账龄维度** → D4 不引入账龄档位。（6）表的年度列是同族「枚举驱动动态列」问题（年度档位），复用同一原则：档位由审计年度派生、禁硬编码、key 与 label 分离。守卫 Property 28 反向锁死，防后续会话误加账龄。
