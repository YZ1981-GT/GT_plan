# Implementation Plan: J1 披露表 ↔ 附注模板对齐

## Overview

修掉 `j1-disclosure-note-linkage`（已归档）遗留的模板欠账与披露逻辑欠账，
让「J1 披露表 → 附注五、40 / 八、40」的推送链路在**结构、内容、勾稽**三层都成立。

权威源：`backend/wp_templates/J/J1 应付职工薪酬.xlsx`（运行时权威，逐格读出行结构 +
Excel 公式）+ `consol_note_sections_{listed,soe}.json`（第 4 方印证附注交付口径）。
`note_check_preset_formulas.json` 无 J1 条目，故裁决者退为 consol。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "note": "附注模板结构对齐 + 后端守卫（P0 前置：表名/columns/guidance/text_sections）" },
    { "wave": 2, "tasks": ["12", "13", "14", "15"], "note": "复盘增补 P0/P1：合计行推送 / 明细带入 / 复核触发器 / 契约守卫" },
    { "wave": 3, "tasks": ["11"], "note": "抽 J1MovementTable 消除 6 份重复表模板（放在 3~7 之前，后续每项改进省 6 倍工作量）" },
    { "wave": 4, "tasks": ["3", "4", "5"], "note": "勾稽引擎 + 父行派生 + 展示面板（纯函数先行）" },
    { "wave": 5, "tasks": ["6", "7", "8", "9"], "note": "两个 Tab 改造 + 载荷 3 段文本 + AI prompt" },
    { "wave": 6, "tasks": ["10", "17"], "note": "浏览器实测 + 实测挖出的 2 个预存在缺陷修复与守卫" }
  ]
}
```

## Tasks

- [x] 1. 附注模板幂等修订脚本
  - [x] 1.1 新建 `backend/scripts/fix/fix_note_j1_employee_comp_structure.py`
        （`--dry-run`/`--check`/`_aligned_by`，按 `aliases` 游标匹配保幂等）
    - _Requirements: R1, R2, R7.1_
  - [x] 1.2 soe 八、40 第 3 表改名 `短期薪酬列示` → `设定提存计划列示`（消重名，consol 五-41-3 印证）
    - _Requirements: R1.1_
  - [x] 1.3 6 张表补 `columns`（5 列，标签列 `flat` + 4 金额列 `format: amount`）+ 删残留 `_column_groups`
    - _Requirements: R1.2, R1.5_
  - [x] 1.4 6 张表补 `guidance`（源模板红字 + CAS 9 + 「勾稽：」前缀的实证公式）
    - _Requirements: R1.3_
  - [x] 1.5 listed 表2 删 `……` 占位行，语义移入 `guidance`
    - _Requirements: R1.4_
  - [x] 1.6 `text_sections` 补齐：listed 4→11 段（含现金流量注）；soe 3→7 段
        （追加 3 条说明正文，禁 `####` 前缀；设定受益计划交叉引用由过时的 八、47 改指 八、54）
    - _Requirements: R2_
  - [x] 1.7 `--dry-run` 复核后 apply，再 `--check` + 重跑确认幂等（三连验证通过）
    - _Requirements: R7.1_

- [x] 2. 后端结构守卫
  - [x] 2.1 新建 `backend/tests/services/test_note_j1_employee_comp_structure.py`（30 测试全绿）
    - _Requirements: R7.1_
  - [x] 2.2 CI job `note-j1-structure` 挂 `governance-checks.yml`
    - _Requirements: R7.1_

- [x] 3. 勾稽引擎（纯函数）
  - [x] 3.1 新建 `j1DisclosureConsistency.ts`（6 类规则 → 11 项结论，容差 0.01 元）
    - _Requirements: R3.2, R3.3, R3.4, R3.6_
  - [x] 3.2 新建 `j1DisclosureConsistency.spec.ts`（20 测试：正向全平 + **反向**制造差异必须报出
        + 差异可定位到列 + 边界降级不产假通过）
    - _Requirements: R7.3_

- [x] 4. 父行派生
  - [x] 4.1 `applyParentSums(rows)` / `derivedParentIds(rows)` 落在零依赖 leaf
        `j1DisclosureRowModel.ts`（非缩进行后紧跟连续缩进行时，父行三列 = 子行之和）
    - _Requirements: R3.1_
  - [x] 4.2 `hydrate` / `onRowChange` / 增删行（`afterRowSetChange`）/ 明细带入后调用；
        派生行由 `J1MovementTable` 的 `derived-ids` 渲染成只读公式单元格
    - _Requirements: R3.1_
  - [x] 4.3 单测 `j1DisclosureRowModel.spec.ts`（18 测试：无子行不动 / 多组父子 /
        新增删除子行自动跟随 / 幂等 / 合计行截断子项区间）
    - _Requirements: R7.3_

- [x] 5. 展示组件
  - [x] 5.1 新建 `J1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细 + 规则 tooltip
        + `GtIndexChip` 追溯，不平项置顶，13px）
    - _Requirements: R3.5_

- [x] 6. 底稿披露表改造（上市）
  - [x] 6.1 方法论上下文块（琥珀色）移到表1 上方 + 设定提存/辞退福利区各一块；删重复 `details`
    - _Requirements: R4.3_
  - [x] 6.2 挂勾稽面板；表2/表3 父行改只读公式单元格（虚线 + tooltip）
    - _Requirements: R3.1, R3.5_
  - [x] 6.3 辞退福利提示改源 xlsx R54 原文口径（与现金流量表「支付给职工以及为职工支付的现金」
        一致），删掉自造的"不得超过期初数加本期增加数之和"
    - _Requirements: R4.1_

- [x] 7. 底稿披露表改造（国企）
  - [x] 7.1 方法论上下文块 + 勾稽面板 + 父行公式单元格
    - _Requirements: R3.1, R3.5, R4.3_
  - [x] 7.2 说明拆 3 个文本域（各带 AI 辅助 + section 级复核），placeholder 取源 xlsx
        R42~R44 完整原文；交叉引用由过时的 八、47 改指 八、54
    - _Requirements: R4.2_

- [x] 8. 载荷映射
  - [x] 8.1 头注释撤销 Decision 3（模板已修）；说明域定义收敛为
        `J1_LISTED_NOTE_FIELDS` / `J1_SOE_NOTE_FIELDS` + `j1NoteFields` / `j1NoteKeys`
        单一真源（soe 由 1 段扩为 3 段，两个 Tab 的 placeholder 与 `_note_texts` 同源）
    - _Requirements: R6.1_

- [x] 9. AI prompt
  - [x] 9.1 `wp_guidance_chat._SECTION_PROMPTS` 追加 6 条 J1 披露 section
        （每条 ≥20 字 + CAS 9 口径 + 不得虚构约束 + 允许声明"不存在设定受益计划"）
    - _Requirements: R5_
  - [x] 9.2 新建 `backend/tests/test_j1_ai_sections.py`（18 测试；section 名从前端 `.ts`
        源码读出防双真源漂移，并用测试锁住"通用端点不做拒绝式白名单"这一前提）
    - _Requirements: R5.2_

- [x] 10. 验证
  - [x] 10.1 浏览器实测国企侧全链通过（chrome-devtools + postgres 只读双证）：
        录入 → 父行自动派生（社保 150/15/7 = 医疗 100/10/5 + 工伤 50/5/2，合计 180
        正确排除「其中：」）→ 勾稽面板由「4 项不平」转「全部一致」→ 同步 →
        `_last_sync_at` 写入、`_source=workpaper`、3 张表键正确、**每张表末行是
        `合计`/`is_total`**、`_column_groups: []`（证明 `flat` 生效未被反猜父表头）、
        guidance 齐备、`text_content` 2 段说明标题正确。**实测顺带挖出 2 个缺陷见 Task 17**
    - _Requirements: R7.4_
  - [x] 10.2* 上市侧无活体项目（5 个在册 J1 项目 `entity_type` 全 soe）→ 记录为未活测，
        由契约测试 + 纯函数单测 + 源码接线守卫覆盖
    - _Requirements: R7.4_

- [x] 11. 抽 `J1MovementTable.vue`（三张表模板在两组件里共 6 份几乎逐字相同）
  - [x] 11.1 抽子组件（props：rows / subtotal / 列头 / `labelEditable` / `removable` /
        `selectable` / `derivedIds` / 只读态；只读单元格三类：合计行、期末列、派生父行）
  - [x] 11.2 两个 Tab 各替换 3 处；只读金额同时收归 `displayPrefs.fmtAmount`
        （原本地 `fmtN` 把 0 显示成「-」）；守卫断言模板内 0 处裸 `el-table`
    - _Requirements: R3.1, R3.5_

- [x] 17. 浏览器实测追加的 2 个缺陷（均为**预存在**，vitest 与 get_diagnostics 都查不出）
  - [x] 17.1 🔴 **P0：两个 Tab 的同步按钮与自动同步全程失效**。
        `syncToDisclosureNotes()` 在 async 处理器里调 `useAuditContext()`，而它内部用
        `useRoute()`（`inject`）+ `onScopeDispose()` → 必须在 setup 顶层同步调用；
        点击时 `inject` 拿不到 route → `route.params` 上 TypeError → **在 `http.post`
        之前就抛错**，零网络请求、只弹「同步到附注失败」。实测该项目 `八、40` 的
        `_last_sync_at` 一直是 NULL。修法：`const { year: auditYear } = useAuditContext()`
        提到 setup 顶层，处理器只读 `auditYear.value`
  - [x] 17.2 手动同步成功分支里 `scheduleAutoSync(syncToDisclosureNotes)` = **调度自己**
        → 800ms 后重复发同一个 POST，用户在一次成功同步后又收到莫名的「同步到附注失败」。
        移除该行（自动同步只由数据变更触发：增删行 / 从明细带入 / AI 写入）
  - [x] 17.3 守卫 `j1/__tests__/j1DisclosureSyncWiring.spec.ts`（21 测试，读 `.vue` 源码正则）：
        `useAuditContext()` 恰好 1 次且不在 `syncToDisclosureNotes` 内 / 该函数内无
        `scheduleAutoSync` / 数据变更路径仍 ≥3 处触发 / 章节号 / 3 处 `J1MovementTable`
        且模板 0 处裸 `el-table` / 勾稽面板 + ≥3 个复核触发器 / `fmtAmount` 且无
        `return '-'` / noteKeys 走单一真源 / 辞退福利非自造文案。
        **守卫自身首版误报**（正则把说明注释里的 `useAuditContext()` 也数进去）→ 加
        `stripComments()` 预处理，这是写"读源码型契约测试"的通用坑
    - _Requirements: R6.2, R7.4_

- [x] 12. P0（复盘增补）：三张表的合计行从未推给附注
  - [x] 12.1 抽零依赖 leaf 模块 `j1DisclosureRowModel.ts`（`J1DisclosureRow` /
        `recalcDisclosureRow` / `buildDisclosureSubtotal`），`useJ1DisclosureSections`
        re-export 保持既有 import 可用（消除与新 pull 模块的循环依赖）
  - [x] 12.2 `j1NoteSectionMap.withTotalRow()` 在载荷层统一补合计行（复用 `buildDisclosureSubtotal`，
        与 UI 合计同源；上游若已带合计行先剔除再重算，幂等无双合计）
  - [x] 12.3 新增 `J1_NOTE_TOTAL_LABEL = '合计'`（附注模板字面**无空格**；底稿 UI 仍用源模板的「合 计」）
  - [x] 12.4 守卫 `j1NoteSyncPayload.spec.ts`（15 测试：末行是合计 / 字面与模板 `rows` 一致 /
        汇总合计 = 各类别之和 / 明细合计排除「其中：」/ 幂等 / 空表补全零合计）
    - _Requirements: R6.2, R6.3_

- [x] 13. P1-a（复盘增补）：明细两表缺「从 J1-2 明细带入」（12 + 8 行原需手打）
  - [x] 13.1 新建纯函数 `j1DisclosureDetailPull.ts`：两趟匹配（精确 → 包含聚合）+ 队列配对 +
        `absorb` 别名 + 未匹配顶层追加 / 「其中：」子项跳过。行名映射全部有源模板公式依据：
        `A18=J1-2!J13`（父行精确）/ `A21=J21+J22`（医疗 ← 基本+补充）/
        `A29=J26+J27`（工会 + 职工教育）/ 国企 `B28=J30+J31`（其他短期薪酬吸收非货币性福利）
  - [x] 13.2 `useJ1DisclosureSections.pullDetailSections()` 编排（读 `J1_DETAIL_SECTION_KEYS`，
        国企传 `J1_SOE_SHORT_TERM_ABSORB`，审定口径 = 未审 + 调整）
  - [x] 13.3 两个披露 Tab 的明细区加「从 J1-2 明细带入」按钮 + 确认框 + 如实提示
        （命中 / 追加 / 未匹配子项数），带入后触发自动同步
  - [x] 13.4 守卫 `j1DisclosureDetailPull.spec.ts`（23 测试，含**反向断言**：不传 `absorb` 时
        非货币性福利必被追加成多余行；披露行倒序结果一致；子项不双算）
    - _Requirements: R7.3_

- [x] 14. P1-b（复盘增补）：两个披露 Tab 不可复核（主入口已 provide 圆点，组件无触发器）
  - [x] 14.1 工具栏加 `GtIndexChip`（wp:J1-1 / wp:J1-2 / Note:章节号）+ Tab 级 `GtReviewTrigger`
        （顺带让原本未使用的 `import GtIndexChip` 死代码变为实际使用）
  - [x] 14.2 明细两区 section 标题行右侧各加 `GtReviewTrigger`（section 级复核）
    - _Requirements: R4.4_

- [x] 15. 契约守卫接共享 helper
  - [x] 15.1 新建 `j1NoteSubtableContract.spec.ts`（`runDisclosureSubtableContract` 5 条
        Property，22 测试）—— 这正是能拦住 soe 孤儿子表的那条 P1
    - _Requirements: R7.2_

- [x] 16. 可选（另立任务）
  - [x] 16.1* 只读金额改走 `stores/displayPrefs.fmtAmount()`
        （现本地 `fmtN` 把 0 显示成「-」，且无「元」单位偏好）
  - [x] 16.2* 披露表导入导出（复用 F2 `_f2_disclosure_import_export.py` 表驱动范式）
  - [x] 16.3* `el-input-number` → `WpAmountInput`（平台级存量替换 spec 统一收口）

## Notes

- **裁决 1**：附注侧列头统一「期初余额 / 本期增加 / 本期减少 / 期末余额」（consol 三表一致），
  底稿 UI 保留各自源模板列头（上市「上年年末数 / 期末数」），由 `j1MovementColumns()` 投影。
- **裁决 2**：撤销原 Decision 3 的"允许偏离模板"，改为**改模板**（soe 第 3 表更名）。
- **裁决 3**：soe 表2 社保「其中」项模板 seed 保持 3 项（consol 原文），底稿录 4 项，
  同步后附注按底稿实际行呈现，**不做聚合**（避免「生育保险费」在附注不可见 + 不可逆变换）。
- **裁决 4**：三张表是**平行勾稽**关系（源模板三表都独立引 J1-2），不是父子派生
  → 汇总表两行保持可手工编辑，差异由勾稽面板报出，不静默覆盖录入。
- **裁决 5**：同表内父行 = Σ 紧邻缩进子行（源公式 `B20=SUM(B21:B27)` / `B41=SUM(B42:B45)`）
  → 做成只读派生（Task 4）。
- 改模板 JSON 对**既有项目不生效**（`table_data._tables` 是生成时快照）→ 交付说明须写清
  「新建项目 / 重新生成附注才可见」；既有项目靠底稿「同步到附注」整表覆盖。
- **Task 16.2 交付说明（披露表导入导出）**

  区块设计（sheet ↔ item_id ↔ 形态）：

  | 变体 | workbook sheet | item_id | 形态 |
  |---|---|---|---|
  | 上市 | `应付职工薪酬` | `J1-disc-listed-summary` | rows（骨架 4 行） |
  | 上市 | `(1)短期薪酬` | `J1-disc-listed-short-term` | rows（骨架 12 行，含 3 个「其中：」子项） |
  | 上市 | `(2)设定提存计划` | `J1-disc-listed-post-employment` | rows（骨架 8 行，含 6 个子项） |
  | 上市 | `文本说明` | `J1-disc-listed-notes` | 说明域 3 段（单 item 存 `{key: text}`） |
  | 国企 | `(1)应付职工薪酬列示` | `J1-disc-soe-summary` | rows（骨架 5 行） |
  | 国企 | `(2)短期薪酬列示` | `J1-disc-soe-short-term` | rows（骨架 12 行，含 4 个子项） |
  | 国企 | `(3)设定提存计划列示` | `J1-disc-soe-post-employment` | rows（骨架 8 行，含 6 个子项） |
  | 国企 | `文本说明` | `J1-disc-soe-notes` | 说明域 3 段 |

  七列表头（`headers_of(variant)`，逐字取自底稿 UI）：`行标识(勿改)` | `项目` |
  `其中：子项(1=是)` | 上市`上年年末数`·国企`期初余额` | `本期增加` | `本期减少` |
  上市`期末数`·国企`期末余额` + `(公式，不导入)`。

  **F2 三形态的取舍**：J1 三张表列结构逐字相同 → 全为 `rows`，列头提到变体级函数
  `headers_of()`，不在每个区块里重复三份；`override` / `dr` 在 J1 无对应表
  （「从审定表/明细表带入」是前端读 J1-1/J1-2 的联动，不是可覆盖 map）；说明域是
  **单 item 存 `{key: text}`**（不同于 F2 一文本域一 item），故独立成「文本说明」
  sheet 而非 `_Block`。

  **整表覆盖语义**：

  - `rows` 区块导入即以表内容为准（表里没有的行 = 删除该披露行）；**整表未填任何金额
    时跳过写库**（`filled=0`），防「拿空模板只想导文本」误清既有明细。
  - 「文本说明」同理：内容全空则跳过；只要有一条填了内容，其余留空即视为清空该说明；
    表内**未出现**的说明键沿用既有值（三段存在同一 item，先读后合并再写）。
  - **行名可改 → 只能按「行标识」列匹配**（国企短期薪酬 `其他` 与设定提存 `其他` 重名，
    按标签匹配会静默覆盖）；重复行标识报 warning 并跳过后出现者。
  - 三类派生量导入时按底稿同口径**重算**，用户填的值不作权威：期末列、派生父行三列
    （Σ 紧邻「其中：」子行，源模板 SUM 公式）、合计行（压根不落库）。

  **双真源守法**：后端镜像了 4 组前端常量（期初/期末列头、骨架行 + `category`、
  说明域 (key,title)、落库字段集），全部由 `backend/tests/test_j1_disclosure_import_export.py`
  **直接正则读 `.vue` / `.ts` 源码逐条比对**守住；前端
  `j1DisclosureImportExportWiring.spec.ts` 反向读后端 `.py` 抽 `SHEET_*` 常量与 `.vue`
  的 `sheet="…"` 比对（跨语言双向）。路由**不新建 router**：分派挂在既有
  `_j1_import_export.py` 三路由上，`_resolve_sheet_type()` 同时接受共享组件的 `sheet`
  与历史 `sheet_type`，两个导出端点改 `GET`+`POST` 双方法（共享
  `useWorkpaperImportExport` 只发 POST，9 个既有 J1 Tab 的 GET 调用不受影响）。

  **验证结果**：

  - 后端 `test_j1_disclosure_import_export.py` **68 passed**（常量镜像 / workbook 结构 /
    往返一致 / 派生重算 / 行标识匹配 / 全空跳过 / 伪 session 写库路径 / 路由入参归一）
  - 回归 `test_j1_employee_compensation.py` + `test_note_j1_employee_comp_structure.py`
    + `test_j1_ai_sections.py` + 本文件 = **129 passed, 2 skipped**
  - 前端 `j1NoteSyncPayload` + `j1NoteSubtableContract` + `workpaper/j1` = **95 passed**
    （4 files，含新增接线守卫 18 项）
  - 两个 Tab Vite transform 200；改动/新增 7 个文件 `get_diagnostics` 无诊断
