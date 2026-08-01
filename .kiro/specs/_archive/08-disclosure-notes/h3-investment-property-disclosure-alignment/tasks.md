# Implementation Plan: H3 投资性房地产披露结构对齐

## Overview

H3 披露映射是从未与模板对齐的半成品（章节号指向固定资产、表名全不匹配、行形态位置化、国企两级表头压扁、上市列转置被压成变动矩阵、无自动同步、columns/guidance 全缺）。本 spec 以源 xlsx 为裁决者重建三层结构并补守卫。不改四表取数与既有跨底稿勾稽。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "rationale": "源模板确权 + 已修章节号补守卫（独立可并行）" },
    { "wave": 2, "tasks": ["3"], "rationale": "附注模板结构与列 key 是前端映射的真源" },
    { "wave": 3, "tasks": ["4", "5"], "rationale": "后端守卫与前端映射重写并行（均依赖模板列 key）" },
    { "wave": 4, "tasks": ["6", "7"], "rationale": "宿主自动同步 + 前端契约守卫依赖映射就位" },
    { "wave": 5, "tasks": ["8"], "rationale": "CI 挂载依赖两侧守卫" },
    { "wave": 6, "tasks": ["9"], "rationale": "两变体实测依赖全链完成" }
  ]
}
```

## Tasks

- [x] 1. 逐 sheet 精读 H3 源 xlsx，确权两版结构
  - openpyxl 读两张披露 sheet：上市 4 段（成本计量 38 行四层 / 公允价值 / 未办妥产权证书 / 房地产转换情况纯文本）列转置 4 类别；国企 3 段（以成本计量 7 列两级 5 层 / 以公允价值计量 8 列两级 3 层 / 未办妥产权证书）。
  - _Requirements: 1.2, 2.1, 2.2, 3.1, 3.2, 3.3, 3.4_

- [x] 2. 章节号纠正（soe 八、22 → 八、21）
  - `h3NoteSectionMap.H3_NOTE_SECTION.soe` 原指向**固定资产**章节 → 已修为 `八、21`（`variant_matrix` + DB 双证）。守卫在 Task 7 补。
  - _Requirements: 1.1_

- [x] 3. 附注模板结构重建幂等脚本 `fix_note_h3_investment_property_structure.py`
  - 用 `_note_structure_kit` 的 `grouped_columns`/`flat_columns`/`rule`/`run_section`/`build_cli`。
  - listed §五、21：3 表（成本计量 flat 5 列列转置 + 四层行集 / 公允价值 flat 5 列 + 3 段行集 / 未办妥产权证书 flat 3 列），删「可无限量添加行」占位行，`text_sections` 补 (4) 房地产转换情况（`#### ` 前缀）。
  - soe §八、21：`以成本计量` 两级 7 列（本期增加{购置或计提,自用房地产或存货转入} / 本期减少{处置,转为自用房地产}，期初/期末无 group）+ 5 层×(合计+2类别)；`以公允价值计量` 两级 8 列 + 3 层；第 3 表由重名 `以公允价值计量` **走 rule aliases 改名**为「未办妥产权证书的投资性房地产」（不能进 drops）。
  - 每表补 `guidance`（源模板红字 / 15 号文 / 证监会年报会计监管报告提示 / 勾稽，不自造）。
  - `--dry-run` 预览 → 应用 → `--check` 幂等 0 欠账。
  - _Requirements: 1.3, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2, 7.2_

- [x] 4. 后端结构守卫 `test_note_h3_investment_property_structure.py`
  - `--check` 无欠账 / 表数表名序 / 无重名 / 两级分组自洽 / flat 表态 / columns key 与前端一致 / 行集层次（5 层·3 层·各 2 类别）/ 无 header_label 与占位行。
  - openpyxl 直读源 xlsx tab 名 + 国企两级子表头（购置或计提 / 自用房地产或存货转入 / 处 置 / 转为自用房地产 / 公允价值变动损益）交叉比对。
  - 反向自检（validate 能抓出缺 columns / 重名 / header_label）。
  - _Requirements: 6.3, 1.3, 3.5_

- [x] 5. 前端映射重写 `h3NoteSectionMap.ts`
  - **顺带修掉真 bug**：`H3TabDisclosureSoe.vue` 的 `costImpairRows` 与 watch 都读 `getSectionRows('cost-impair')`——那是**上市**组件的 section key，国企自身是 `'soe-impair'` → 国企减值行永远取空、减值层与账面价值层恒 0、改减值也不触发自动同步。已改正并补 `titleRows: getSectionRows('soe-unlicensed')`。
  - **实测确认自动同步已接**（两 Tab 均有 `watch(...) → autoSync.scheduleAutoSync`，非自调度），故 Task 6 只剩上市 (4) 文本段与子列录入。
  - 表名常量对齐模板 + `H3_LEGACY_OBSOLETE_TABLES`（旧 8 条载荷表名 + 重名旧键）。
  - `buildH3ListedColumns()` / `buildH3SoeColumns()`（两级用 `group`，单级标 `flat`；rowspan=2 列不带 group）。
  - `buildH3SyncPayload`：行形态改 `{业务键 dict}`（弃位置化 `values`）；按 `measurementModel` 二选一 + `_removed_table_keys`；合计行 `withTotalRow()` 幂等补齐；`_note_texts` 带中文 title + 空文本过滤。
  - _Requirements: 1.2, 1.4, 4.1, 4.2, 4.3, 4.4, 5.4_

- [x] 6. 宿主接自动同步 + (4) 转换情况文本段
  - 自动同步**原本已接**（两披露 Tab 各有 `watch(实际数据) → autoSync.scheduleAutoSync`，非自调度）→ 本任务只补上市 (4) 段。
  - 上市新增「（4）房地产转换情况及改变计量模式的情况」区块：源模板红字三段（琥珀色 `.src-hint`）+ `sectionTexts['conversion']` 文本域 + 🤖 AI（`generateH3AI('conversion')` 走通用 `/ai/generate-text`，`useH3AiGenerate` 接受自由 section）。
  - 披露 Tab 接 `useDisclosureAutoSync`（watch 构建载荷的实际数据，非横幅、非自调度）；宿主传 `:project-id`。
  - 上市补 (4)「房地产转换情况及改变计量模式的情况」文本域 + AI 辅助（prompt 写明源模板口径 + 不得虚构）+ `GtReviewTrigger`。
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 7. 前端契约守卫 `h3NoteSubtableContract.spec.ts`
  - 复用 `_disclosureSubtableContract.helper` P1~P6 + H3 专属：章节号（含断言 `八、22` 不出现）、两级分组、行形态为 dict、计量模式互斥与 `_removed_table_keys`，含反向自检。
  - _Requirements: 1.5, 6.4, 4.1, 4.2_

- [x] 8. CI 挂载 `note-h3-structure` job（governance-checks.yml）
  - 跑 `fix_note_h3_investment_property_structure.py --check` + 两侧守卫测试（需 openpyxl）。
  - _Requirements: 6.5_

- [x] 9. 两变体浏览器 + 只读 DB 实测（soe 已完成；listed 见备注）
  - **soe 实测通过**（项目 `2aa00f57` / wp `899bf861`）：国企 Tab 5 区块正常渲染无 Vite 错误；录入 原值(1000/200/50)·折旧(300/60/10)·减值(100/20/0)·未办妥产权证书(办公楼A/500/正在办理产权登记) → **不点按钮**自动同步落库 §**八、21**（正确章节）、子表 `以成本计量` + `未办妥产权证书的投资性房地产`（表名对齐模板、无孤儿）。
  - **五层派生全部正确**：原值 1150 / 折旧 350 / 净值 800（期初 700）/ 减值 120 / 账面价值 680（期初 600）—— 减值层非 0 直接证明 `soe-impair` key bugfix 生效（此前恒 0）。
  - `project_sub_tables` 读时投影：`以成本计量` → `_column_groups=[{本期增加,2,2},{本期减少,4,2}]`（期初/期末 rowspan=2 正确排除）、headers 7 叶子列与源模板逐字一致；`未办妥产权证书的投资性房地产` → `[]` 单级。
  - 测试数据已清空复原。
  - **listed 未活体**：8 个在册项目仅 `0ec33ac9` 为 `template_type=listed` 且其 `entity_type=soe`（数据不一致 → listed 门控关闭），需临时改 `entity_type` 才能测；本轮未再动该项目数据。结构与载荷由后端 13 + 前端 33 守卫双向锁定。
  - _Requirements: 7.4_
  - soe（项目 `2aa00f57`）与 listed（`0ec33ac9`，需临时置 `applicable_standard_v2.entity_type=listed`，**测后还原**）：Tab 挂载、两级表头渲染、推送后表名/两级 `_column_groups` 正确落库、无孤儿表、`last_sync_at` 前移；`project_sub_tables` 读时投影验证；测试数据复原。
  - _Requirements: 7.4_

- [x] 11. 存量污染清理脚本 `cleanup_h3_misrouted_note_tables.py`（默认 dry-run，**待用户确认后 --apply**）
  - 章节号 bug 造成的存量污染不会自愈：实测项目 `2aa00f57` 的 §八、22（**固定资产**章节）残留
    3 张 H3 孤儿子表（`投资性房地产（账面原值/累计折旧和累计摊销/减值准备）`，`last_sync_wp_id`
    指向 H3 底稿）。全库扫描仅此 1 处 3 表。
  - 三重保守条件（宁漏不误杀）：章节 ∉ {五、21, 八、21} + 键名命中 H3 历史载荷白名单/`投资性房地产（` 前缀
    + `last_sync` 底稿 `wp_code == 'H3'`；同步清 `_sub_table_columns`，`_tables` 交回读时重算。
  - `--apply` 属破坏性写库，已产出并 dry-run 验证，**未执行**。
  - _Requirements: 1.4, 7.4_

- [x] 10. 底稿补齐源模板要求的录入位置（Task 5 已按主渠道退化，此处收口）
  - 国企两级子列：底稿目前只有聚合「本期增加/本期减少」，源模板要求 `购置或计提` / `自用房地产或存货转入` / `处 置` / `转为自用房地产`（公允价值表另有 `公允价值变动损益`）四~五个子列 → 补独立录入列后，`toMovement` 自动改用细分值（现为聚合额归入主渠道的退化映射）。
  - **上市缺「未办妥产权证书」行录入区块**（原只有 `restriction` 文本域）→ 该表永远无法推送。**已补**动态行区块（项目 / 账面价值 / 未办妥产权证书原因 + ＋插行/删除 + 合计）并接 `titleRows`（sync 与 watch 均已接）。
  - 原因列字段兼容：底稿该区块用 `usage` 承载原因（`reason` 为通用回退），载荷两者都认；`isMeaningfulRow` 也认「只填原因」的行。
  - **国企两级子列已补齐（退化映射退役）**：4 个成本类区块（`soe-cost` / `soe-cost-dep` / `soe-impair`）与公允价值区块（`soe-fair-change`）改为源模板两级表头 —— `本期增加{购置或计提, 自用房地产或存货转入}` / `本期减少{处 置, 转为自用房地产}`（公允价值表另有 `公允价值变动损益`，共 5 子列）。新增 `onSubChange()` 在子列录入后把聚合 `increase`/`decrease` 回写为子列之和，使 **UI 期末 / 合计行 / 载荷期末派生三处口径一致**；`rowIncrease`/`rowDecrease` 纯函数供展示；`sumCol` 类型放宽为 `string` 以按子列求和；新增 `.group-th` 父表头样式。
  - **已浏览器实测**（项目 2aa00f57 / wp 899bf861）：3 张成本表各渲染 `本期增加`/`本期减少` 分组 + 4 子列（`thCount=39`）；录入 期初1000 / 购置或计提120 / 转入80 / 处置30 / 转出20 → UI 期末 **1,150.00**、合计行逐子列分别求和；**落库 §八、21 的 `一、账面原值合计` 行为 `buy_or_provision=120, transfer_in=80, disposal=30, transfer_out=20, end=1150`**（细分值原样落格，不再走主渠道退化）。测试数据已复原。
  - _Requirements: 3.1, 3.2, 4.1, 4.3_

## Notes

- H1 已直接修复（非 spec）；H2 spec 已完成。H3 是 H 循环里结构问题最重的一个（半成品映射 + 章节号指向别的科目）。
- **自动同步原本就已接**（两 Tab 有 `watch → scheduleAutoSync`）——首轮 grep 用 `useDisclosureAutoSync|syncToDisclosureNotes|scheduleAutoSync` 在宿主 `GtH3InvestmentProperty.vue` 上查为 0，是因为链路在**子 Tab 组件**里。判「有没有接」要查披露 Tab 本身，不能只查宿主。
- **章节号 `八、22` 是固定资产**，H3 soe 是 `八、21` —— 断言里禁写 `八、22`。
- 国企第 3 表改名走 `rule` aliases，**不可进 `drops`**（H2 已验证 drop 在 apply 前执行会连行删掉）。
- 上市列 key 用资产类别名（同 H1「固定资产情况」范式）；类别可按项目扩展，seed 保留源模板 4 列。
- 载荷单测须覆盖「行是 dict 非 values」这条 Property 5，否则回退到位置化形态不会被发现。
