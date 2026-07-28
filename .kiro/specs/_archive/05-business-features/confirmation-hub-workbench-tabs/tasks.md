# Implementation Plan

## Overview

按 design 的 M0 → M5 阶段实施。**M0 是硬前置**（Linkage_Matrix 未核实完不得执行 skip / override 变更）。

P0 已完成不再重做：`confirmation-hub` 进 `HTML_RENDERER_ROUTE_SET`、`WorkpaperEditor` 移除整体重定向 + Center_Entry、相关三个测试断言同步。本计划从 M0 起。

**E0 采用 B 方案**（用户拍板）：E0 重建为 confirmation-* 结构，落在 Wave 2。

**改动集中在**：`wp_code_overrides.json`（override / skip）、`GtConfirmationSummary.vue`（空态入口 / 同步状态）、4 个 Alternative_Sheet 组件（STUB 替换）、`ConfirmationHub.vue`（回跳来源底稿）、新增 `confirmationLinkageMatrix.ts` + 测试。**不改**后端 render 策略、台账数据模型与状态机、OCR 附件链、替代程序区块列结构。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"], "note": "只读核实 + 零回归基线，无代码风险" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"], "note": "呈现治理 + 路由解析治理：skip / 污染纠正 / G0 差异表可达 / 程序表模板父码优先 / Index_Code_Map 与非兜底守卫（依赖 1.1 矩阵与 1.4 实测定案）" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "note": "E0 重建（B 方案），依赖 1.1 + 2.x override 机制就绪" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "note": "Sync_To_Center 空态入口 + 只读门控 + 同步状态可见" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"], "note": "Unreplied_Pull 四处逐套落地，彼此独立" },
    { "wave": 5, "tasks": ["6.1", "6.2"], "note": "Reply_Backflow 持久化读取 + 手工优先 + 台账回跳" },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "note": "属性/契约测试 + 覆盖守卫" },
    { "wave": 7, "tasks": ["8.1", "8.2"], "note": "零回归门 + 七枢纽 Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：只读核实与基线（硬前置）

- [x] 1.1 补全并落地 Linkage_Matrix 数据源
  - 新建 `audit-platform/frontend/src/components/workpaper/confirmation/coordination/confirmationLinkageMatrix.ts`
  - 按 design「Linkage_Matrix」表写入 7 个 `HubCycleSpec`（cycle / summarySheet / alternativeSheets / capabilities / notApplicableReason）
  - 实现纯函数 `findLinkageGaps(matrix)`：返回 state 为 `stub` / `missing` 的 (cycle, capability)；`not_applicable` 必须带 `notApplicableReason` 否则也算 gap
  - **核实项（写入注释作为依据）**：`D0A` / `E0A` / `E0-6` / `E0-7` / `回函情况汇编` 在无 override 时经 class_code 派生的实际 componentType（用 render-config 或 `derive_component_type` 实测，不猜）
  - 不改任何生产行为（纯新增数据 + 纯函数）
  - _Requirements: 6.1, 6.3_

- [x] 1.2 建立零回归基线快照
  - 运行并记录基线：函证域前端全量测试（`src/components/workpaper/confirmation` + G0/H0 集成 spec）、`htmlRendererRegistry.spec`、`useEditorMode.spec`、`componentTypeContract.spec`
  - 记录 7 个枢纽当前 render-config 的 sheet 集合与各 sheet componentType（作为 Wave1/Wave2 前后对照基准）
  - _Requirements: 8.2, 8.3_

- [x] 1.3 为 Linkage_Matrix 与路由契约写测试
  - 新建 `coordination/__tests__/confirmationLinkageMatrix.spec.ts`：`findLinkageGaps` 行为（stub/missing 被列出、not_applicable 无 reason 被列出、全 implemented 返回空）
  - 断言 `confirmation-hub` ∈ `HTML_RENDERER_ROUTE_SET` 且 ∉ `HTML_COMPONENT_TYPE_SET`
  - _Requirements: 9.4, 9.5, 1.4_
  - _Properties: 2, 16_

- [x] 1.4 实测路由解析落点与程序表模板现状（Requirement 10 前置）
  - 用 render-config 实测 G0 两张差异核对表（`函证差异核对表G0-3（证券投资）` / `函证差异核对表G0-4(非证券投资)`）当前的 componentType 与 html_data 形态（预期落 `onlyoffice-sheet`，因 `_cls_code.startswith("G-")` 强制改写；也可能落 `confirmation-hub`）——**实测结果写入 1.1 的注释，不猜**
  - 实测各 Hub_Workbook 程序表 sheet 的 Program_Template_Code 与 `get_template()` 命中情况（重点 L0 的 `函证程序表F0A` → `F0A` 是否无模板、`L0A` 模板是否存在且含 `risk_for_cycle`）
  - 汇总 Index_Code_Map 初稿：七枢纽每张未 skip 的 sheet 的 sheet_name / Sheet_Code_Tail / 源模板真实索引号 / 偏差原因
  - 纯只读，不改代码
  - _Requirements: 10.1, 10.4, 10.6_

- [x] 2. Wave 1：Hub_Sheet 呈现治理与路由解析治理

- [x] 2.1 遗留 / 占位 sheet skip
  - 在 `backend/app/data/wp_code_overrides.json` 按 **sheet_name 精确 key** 加 `"skip"`：`函证程序表-原版本备份`、`函证结果汇总表E0-1（原）`、`函证结果汇总表E0-1 (备份)`、`函证结果汇总表-旧版`、`货币资金及借款函证结果汇总表-旧版`、`核实被函证单位信息F1-10-原`、`参考用-往来函证程序`、`GT_Custom`
  - **不 skip**：`邮件传真回函核对记录F1-12`、`回函情况汇编`（design 注 2 定案：命名无遗留标记者保留）
  - 改后需重启后端或触发 `.py` 变更使 `_WP_CODE_OVERRIDE` 重新加载（该 JSON 不随 watchfiles 热重载）
  - 用 1.2 基线对照：仅目标 sheet 从页签消失，其余逐一不变
  - _Requirements: 1.1_
  - _Properties: 1_

- [x] 2.2 跨枢纽编码污染纠正
  - 按 sheet_name 精确 override：`函证程序舞弊风险评价表F0-8`（G0 内）→ `confirmation-fraud-risk`；`函证程序表F0A`（L0 内）→ `a-program-console`
  - 索引号偏差（显示 F0-8 / F0A）登记为已知偏差写入注释，不改源 xlsx
  - _Requirements: 6.2_
  - _Properties: 4_

- [x] 2.3 修 G0-3 编码冲突
  - 按 sheet_name 精确 override：`函证差异核对表G0-3（证券投资）` → `confirmation-diff-securities`
  - 核实并注释 `G0-3S` 编码 key 为死配置（sheet 名中不存在该编码）
  - 验证 `跟函函证过程控制G0-3` 仍为 `confirmation-followup`（两张同尾码 sheet 各归其位）
  - _Requirements: 6.2, 1.3_
  - _Properties: 4_

- [x] 2.4 程序表模板 key 父码优先（修 L0A 模板永不生效）
  - `backend/app/routers/wp_render_strategies/_a_program.py`：抽纯函数 `resolve_program_template_code(sheet_name, wp_code)`——提取到的编码循环前缀 ≠ 父 wp_code 循环前缀时先试 `{wp_code}A`，`get_template` 命中才采用，否则回退原提取值
  - 单测锁定三态：`("函证程序表F0A","L0") → "L0A"`、`("函证程序表F0A","F0") → "F0A"`、同循环 sheet 逐字不变
  - 验证 L0 程序表渲染后使用 `L0A` JSON 模板（程序行数与 `risk_for_cycle` / `control_test_result_for_cycle` 联动出现），且其他循环程序表行数与 1.2 基线逐一相同
  - _Requirements: 10.4, 10.5, 10.9_
  - _Properties: 22_

- [x] 2.5 G0 两张差异核对表可达 + Index_Code_Map + 非兜底守卫
  - 按 sheet_name 精确 override：`函证差异核对表G0-3（证券投资）` → `confirmation-diff-securities`（与 2.3 同一条）、`函证差异核对表G0-4(非证券投资)` → `confirmation-diff-reconcile`（先保可达；三维结构属 `g0-investment-diff-model` spec）
  - 标注 `G0-3S` 为死配置（sheet_name 中不存在该编码），确认移除或保留都不改变解析结果
  - 落地 Index_Code_Map（可写入 `confirmationLinkageMatrix.ts` 或同目录数据文件）：sheet_name / Sheet_Code_Tail / 源模板真实索引号 / 偏差原因；G0 差异表尾码比真实索引号错位一位、G0 内 `F0-8`、L0 内 `F0A`、K0-1 调节索引写 `K1-12`、L0-1 调节索引写 `F0-4` 等均登记，不改源 xlsx
  - 契约守卫：七枢纽每张未 skip 的 sheet 解析结果 ∉ {`confirmation-hub`, `skip`}，漏配即失败
  - _Requirements: 10.1, 10.2, 10.3, 10.6, 10.7, 10.8_
  - _Properties: 21, 23, 24_

- [x] 3. Wave 2：E0 重建（B 方案）

- [x] 3.1 E0 sheet componentType 重建
  - 按 design「E0 重建映射表」在 `wp_code_overrides.json` 写入 **sheet_name 精确 override**：
    - `函证结果汇总表E0-1` → `confirmation-summary`
    - `核实被函证单位信息E0-2` → `confirmation-entity-verify`
    - `跟函函证过程控制E0-7` → `confirmation-followup`
    - `邮件传真回函核对记录F1-12` → `confirmation-reliability`
    - `函证程序表E0A` → `a-program-console`（显式登记）
    - `理财产品发函记录表E0-6` → `d-form-table`（显式登记）
    - `银行函证其他信息核对表E0-5` → `d-form-table`（消除与发函记录表 E0-5 的编码冲突）
  - 保留 `货币资金发函记录表E0-3` / `借款发函记录表E0-4` / `应付银行承兑汇票发函记录表E0-5` 为 `d-form-table`（发函前清单，上游）
  - **迁移检查**：执行前复核 E0 系列 `checklist_responses` 行数（design 实证近零）；若某项目已有数据则先备份该行再切换
  - _Requirements: 6.2, 6.3_
  - _Properties: 4, 15_

- [x] 3.2 E0-1 承载五类账户验证
  - 验证 `confirmation-summary` 在 E0 下渲染正常，且行数据含 银行存款 / 其他货币资金 / 短期借款 / 应付票据 / 理财产品 时 `accountTabs` 派生出全部 5 个页签
  - 不改 `useConfirmationData`（accountTabs 已是动态派生）
  - 新增测试锁定该派生（构造 5 类 account_type 行 → 断言 tabs）
  - _Requirements: 3.1, 6.2_
  - _Properties: 13_

- [x] 3.3 E0 清单 → E0-1 带入
  - 在 E0-3 ~ E0-6 清单 sheet 提供「带入 E0-1」能力：筛 `是否函证 = 是` 的行 → 生成 Summary_Sheet 行，`account_type` 按来源品种置值（E0-3→银行存款/其他货币资金、E0-4→短期借款、E0-5→应付票据、E0-6→理财产品）
  - 复用既有 confirmation-v1 写入路径（新增函证对象 / 导入清单），**不新造写入实现**
  - 去重：同一账户/借款重复带入不产生重复行
  - _Requirements: 5.4, 6.4_
  - _Properties: 14, 17_

- [x] 4. Wave 3：Sync_To_Center 可达性与状态可见

- [x] 4.1 空态入口与只读门控
  - `GtConfirmationSummary.vue`：在空态引导视图（「开始编制函证底稿」）内保留 Sync_To_Center 入口
  - 只读 / EQCR 态下隐藏或禁用 Sync_To_Center
  - **不动** `handleSyncHub` / `_autoSyncAfterSave` / `syncHubFromSummary` 既有逻辑
  - _Requirements: 3.3, 3.6_
  - _Properties: 6, 7_

- [x] 4.2 同步状态可见与幂等回写
  - 在 Summary_Sheet 行上呈现同步状态（已同步 / 未同步），数据源为行上已持久化的 hubId
  - 核实并（如缺）补齐 hubId 回写持久化路径，使重复同步幂等
  - _Requirements: 3.4, 7.1_
  - _Properties: 5, 20_

- [x] 5. Wave 4：Unreplied_Pull 四处落地（逐套独立可发布）

- [x] 5.1 F0-5 替代程序带入
  - `GtConfirmationAlternativeF05.vue`：替换 `handleImportF01` 的 STUB（`ElMessage.info('...待跨底稿引用 API 接入后启用')`）
  - 走适配器旁挂的 `importFromSummary`（内部经 `coordination/importFromSummary`，对齐 K06/L05 proven 范式）
  - 成功提示带入条数；无未回函项目提示「无未回函项目」；读不到 F0-1 给可理解提示不抛异常
  - 带入行标注来源为 F0-1
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 6.4, 7.3_
  - _Properties: 10, 11, 12, 17_

- [x] 5.2 F0-6 替代程序带入
  - 同 5.1 手法处理 `GtConfirmationAlternativeF06.vue`
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 6.4, 7.3_
  - _Properties: 10, 11, 12, 17_

- [x] 5.3 D0-6 替代程序带入
  - 同 5.1 手法处理 `GtConfirmationAlternativeD06.vue`
  - 与同枢纽已实现的 D0-5 行为保持一致
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 6.4, 7.3_
  - _Properties: 10, 11, 12, 17_

- [x] 5.4 K0-5 补带入入口
  - `GtConfirmationAlternativeK05.vue`：补「从 K0-1 带入」入口（当前无入口）
  - 复用 `useAlternativeK05Data` 已有的 `importFromSummary`（适配器已暴露，仅缺 UI 接线）
  - 与同枢纽 K0-6 行为一致
  - _Requirements: 5.3, 5.1, 5.4, 5.5, 6.4, 7.3_
  - _Properties: 10, 11, 12, 17_

- [x] 6. Wave 5：Reply_Backflow 与台账回跳

- [x] 6.1 回函结果持久化读取与手工优先
  - Summary_Sheet 打开时按行 hubId 拉取台账回函状态与回函金额刷新（不依赖同会话 `confirmation:received` 事件）
  - 手工优先：底稿行目标字段已有审计师手工值时不覆盖
  - 差异结果可被 X0-4 差异调节表消费（带入或提示存在未调节差异）
  - 科目明细「已函证」批量回写仍走 `coordination/emitConfirmationCompleted`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.4_
  - _Properties: 8, 9, 17_

- [x] 6.2 台账回跳来源底稿
  - `ConfirmationHub.vue`：台账行提供跳回来源 Hub_Workbook 的 Summary_Sheet 入口
  - 经 `source_wp_code` → wp_id 解析 → `router.push({ name:'WorkpaperEditor', query:{ sheet: summarySheetName } })`
  - 解析失败 / 底稿未生成 → 明确提示，不静默跳底稿目录
  - _Requirements: 2.4, 2.5_

- [x] 7. Wave 6：属性测试与守卫

- [x] 7.1 联动属性测试
  - Sync_To_Center 幂等（Property 5）、Unreplied_Pull 去重（Property 10）、Reply_Backflow 手工优先（Property 8）——用 fast-check 属性测试
  - 空集合 / 不可读反馈（Property 12）、空态入口可达（Property 6）、只读门控（Property 7）——单元测试
  - E0 五类 accountTabs（Property 13）、E0 带入去重与品种置值（Property 14）
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 7.2 覆盖守卫与复用守卫
  - Linkage_Matrix 无 gap（Property 16）：`findLinkageGaps` 返回空
  - 无 STUB 残留（Property 11）：断言 Alternative_Sheet 组件中不存在「待接入后启用」类文案
  - 复用共用能力（Property 17）：断言 Unreplied_Pull / Sync_To_Center / 明细回写分别经 `importFromSummary` / `syncHubFromSummary` / `emitConfirmationCompleted`
  - E0 不臆造（Property 15）：断言 E0 的 diff / unreplied_pull 为 `not_applicable` 且带 reason
  - _Requirements: 6.4, 6.5, 5.2, 5.3_

- [x] 7.3 sheet_name override 优先级契约
  - 断言 sheet_name 精确 override 优先于编码尾码解析（保证 2.2 / 2.3 / 3.1 生效）
  - 覆盖 G0-3 双 sheet、G0 内 F0-8、L0 内 F0A、E0-5 双 sheet 四组冲突场景
  - _Requirements: 6.2_
  - _Properties: 4_

- [x] 8. Wave 7：零回归门与端到端

- [x] 8.1 零回归门
  - 函证域前端全量测试 + `htmlRendererRegistry.spec` + `useEditorMode.spec` + `componentTypeContract.spec`：**706/707 绿**
  - 改动文件 `get_diagnostics` 全清（本 spec 8 个改动/新建文件逐一 No diagnostics）；后端契约 35 passed（override contract 29 + program template 6）
  - **唯一 1 failed = 范围外并发缺陷**：`alternativeCallerMount.smoke.spec.ts > GtConfirmationAlternativeL05`（`data.getBlockTotalByDirection is not a function`）。经 git status + grep 实证：`GtConfirmationAlternativeL05.vue` 是并发 `confirmation-alternative-structure-alignment` spec（L05 借贷拆表 Task 3.3）改动（**M** 状态）引用了 `getBlockTotalByDirection`，而其适配器 `useAlternativeL05Data.ts` **未改（committed）** 尚未透传该方法 → 半成品状态。该方法在工厂 `createAlternativeConfirmationData` 已实现，K05/K06（工厂型，本 spec 触及的 K05 亦在内）caller smoke **全通过**。与本 spec 五组件零交集，按 git-safety 不擅自修（clobber 风险），留并发会话收敛。
  - `confirmations/match-queue` 500 同属范围外既有缺陷，不阻断底稿层能力
  - _Requirements: 8.1, 8.2, 8.3, 8.5_
  - _Properties: 18, 19_

- [ ] 8.2* 七枢纽 Playwright 端到端（可选，诚实留待）
  - 对 D0 / E0 / F0 / G0 / H0 / K0 / L0 各一次：打开 Hub_Workbook → 页签集合符合 Property 1（含 skip 生效）→ 逐 tab 无占位 / 无加载失败 → Center_Entry 跳转 → Summary_Sheet 空态入口可见 → Alternative_Sheet 带入按钮非桩提示
  - E0 额外验证：E0-1 渲染为 confirmation-summary、E0-2/E0-7/F1-12 渲染为对应专属组件、清单→E0-1 带入可用
  - Sync_To_Center 的 live 验证采用 design 的避污染范式：备份受影响 `confirmation` 行 → HTTP 同步 → 断言 → 精确恢复 + `RESTORED_IDENTICAL` 断言
  - **环境不满足诚实留待**（不假绿）：需七枢纽全部实例化的项目 + 全栈起服务；且本会话期间检测到并发 Kiro 会话正 SSE 推事件反复劫持编辑器（EventSource 跳转），Playwright 整链在单次调用内完成的稳定性无法保证。功能正确性已由 707 前端测试（含 Linkage_Matrix / 属性 / 覆盖守卫 / 复用守卫 / E0 accountTabs / 带入去重）+ 35 后端契约测试（sheet override 解析 + 程序表模板父码优先）充分覆盖。
  - 并发 SSE 跳转风险应对：用 `addInitScript` 中和 EventSource，整链在单次调用内完成（待环境稳定后补跑）
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 3.3, 5.2_
  - _Properties: 1, 3, 6, 11_

## Notes

- **M0（Wave 0）是硬前置**：1.1 的核实未完成不得进 Wave 1（skip 掉在用 sheet 会让数据在编辑器内不可达）
- **skip 判定唯一依据是命名显式标记**（`-原版本备份` / `（原）` / `(备份)` / `-旧版` / `-原` / `参考用-`）：分类表全部 sheet 的 `is_real_workpaper=True` 不提供遗留标记；命名无标记者一律保留
- `wp_code_overrides.json` **不随 watchfiles 热重载**（`_WP_CODE_OVERRIDE` 模块级加载一次），每次改完需重启后端或触发 `.py` 变更
- Wave 4 的四个任务彼此独立，可逐套发布 / 逐套回退
- 全程复用既有共用能力（`importFromSummary` / `syncHubFromSummary` / `emitConfirmationCompleted`），禁止新造并行实现
- 不改后端 render 策略（**唯一例外**：2.4 的程序表模板 key 父码优先，带回退兜底）、`workpaper_sheet_classification`、台账数据模型与状态机、OCR 附件证据链、替代程序区块列结构
- **Requirement 10（路由与编码治理）由 `docs/proposals/confirmation-cycles-polish-assessment.md` 的 spec-1 并入本 spec**（与既有 Wave 1 高度重叠，不另起 spec）
- 该评估报告另划出的后续增量 spec：`confirmation-shared-model-extension`（共享行模型补列）、`confirmation-alternative-structure-alignment`（替代程序结构对齐）、`g0-investment-diff-model`（G0 非证券三维差异 + diffSecurities 补列）、`e0-send-list-components`（E0 发函前清单组件）——均在本 spec 之后，不在本 spec 范围
