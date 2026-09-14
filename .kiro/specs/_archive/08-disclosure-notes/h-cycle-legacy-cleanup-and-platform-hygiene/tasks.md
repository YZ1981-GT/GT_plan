# Implementation Plan: H 循环遗留收口与平台级数据卫生

## Overview

19 个任务分 6 波。Wave 1~2 无依赖可先行；Wave 3 依赖 Wave 1 的守卫骨架；Wave 4 需 DB 只读查询建反查索引；Wave 5 最重（共享件收敛 + 7 循环推广）；Wave 6 需临时改库（破坏性，须用户确认）。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "命名与 registry 统一（最便宜、无依赖）",
      "tasks": ["1", "2"]
    },
    {
      "wave": 2,
      "name": "平台级 `**` 残迹清理",
      "tasks": ["3", "4", "5"]
    },
    {
      "wave": 3,
      "name": "H 循环披露 AI 与复核接线",
      "tasks": ["6", "7", "8", "9"]
    },
    {
      "wave": 4,
      "name": "report_row_code 重映射",
      "tasks": ["10", "11", "12"]
    },
    {
      "wave": 5,
      "name": "勾稽共享件与 H 循环推广",
      "tasks": ["13", "14", "15", "16"]
    },
    {
      "wave": 6,
      "name": "活体验证与收口",
      "tasks": ["17", "18", "19"]
    }
  ]
}
```

## Tasks

- [x] 1. 新建 H4 薄壳映射 `h4NoteSectionMap.ts`
  - 内联 `H4_NOTE_SECTION`（与 `h2NoteSectionMap` 逐字一致）与 `H4_DISCLOSURE_SHEET_NAME`（openpyxl 读源 xlsx tab 名核实）
  - re-export 既有 `h4DisclosureSyncPayload` / `h4SoeDisclosureSyncPayload` 的 builder
  - 对象体内**禁写注释**、章节号**必须内联字面量**（生成器两条硬约束）
  - 重跑 `gen_note_wp_sync_registry.py --write` 并确认 H4 两变体进 registry
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 2. 平台级命名覆盖守卫 `noteSectionMapNamingCoverage.spec.ts`
  - Property 9：凡有 payload/map 文件的循环码必在 registry；allowlist 须写理由（`mEquityChangeNoteSectionMap.ts` 属共享文件，由 m4/m5/m7 薄壳代表）
  - 新建 `h4NoteSectionMapShell.spec.ts` 实现 Property 10
  - _Requirements: 4.3, 4.4_

- [x] 3. 新建 `backend/scripts/fix/fix_note_bold_markers.py`
  - `strip_pairs` 成对剥离 + `odd_marker_paragraphs` 列示不成对段
  - 扫描范围：`text_sections` / `tables[].guidance` / `tables[].headers` / 各级 `rows[].label`（含 `children` 嵌套）
  - `--dry-run`（默认）/ `--check` / `--apply`；复用 `_note_structure_kit` 的读写与报告骨架
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 4. 后端守卫 `test_note_bold_marker_hygiene.py`
  - 全库无成对 `**`；`strip_pairs` 的 Property 1/2/3（hypothesis `max_examples=5`）
  - 反向自检：内联 fixture 断言检测器抓成对、放行奇数个
  - _Requirements: 1.5, 1.6_

- [x] 5. 执行清理 + CI job `note-bold-marker-hygiene`
  - `--apply` 剥离 38 段中的成对标记与 guidance 22 处；2 段脱敏占位原样保留
  - 二次运行确认 0 变更；`governance-checks.yml` 挂 `--check`
  - _Requirements: 1.1, 1.4_

- [x] 6. H8/H9 四个披露 Tab 接 AI 与复核
  - 删 `emit('open-ai')` / `emit('open-review')`，改接 `useDisclosureNoteAi` + `<GtReviewTrigger>`
  - `context` 值全部 `String()`；按钮加 `:loading` 与 `:disabled="isReadonly"`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 7. H1/H2/H4/H5/H6 披露 Tab 补 AI 按钮
  - 逐 Tab 清点说明文本域，每个文本域旁加 AI 按钮（section 标题行右侧，非只在底部）
  - _Requirements: 3.1_

- [x] 8. 后端 `_SECTION_PROMPTS` 登记 H 循环披露 prompt
  - 每条 ≥20 字，写明源模板/15 号文口径 + 「不得虚构」
  - _Requirements: 3.2_

- [x] 9. AI 接线守卫
  - 前端 `hDisclosureAiWiring.spec.ts`（Property 6/7，`stripComments` 自检用内联 fixture）
  - 后端 `test_review_dialog_h_cycle_prompts.py`（Property 8）
  - CI job `h-cycle-ai-wiring`
  - _Requirements: 2.6, 3.3_

- [x] 10. 新建 `backend/scripts/fix/remap_note_report_row_codes.py`
  - `build_label_index` 从 `report_config` 建归一化标签→码索引；`normalize_label` 去 `其中：`/`减：`/尾冒号/全角空格
  - 三态 `ok` / `ambiguous` / `not_found`；`--apply` 只改 `ok`
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 11. 后端守卫 `test_note_report_row_code_alignment.py`
  - Property 4/5；`ambiguous`/`not_found` 走 allowlist 且每条写 `reason`；含错码 fixture 反向自检
  - _Requirements: 6.4_

- [x] 12. 执行重映射 + CI job `note-report-row-code`
  - `--check` 出清单 → 人工核对 → `--apply` → 二次 0 变更
  - _Requirements: 6.1, 6.5_

- [x] 13. 勾稽共享件收敛
  - 核实 `composables/shared/disclosureConsistency.ts` 现有 API 覆盖度；不足则扩展（`eqCheck` / `subsetCheck` / `summarize`）
  - D1/F1/H1/J1/N1 五份引擎改委托共享件，既有测试零回归
  - _Requirements: 5.1, 5.2_

- [x] 14. H2/H3/H5 勾稽规则与面板接入
  - 规则全部标注源模板依据（层间派生 / 子集约束 / 「—」列示约定）
  - 复用 `WpDisclosureConsistencyPanel.vue`
  - _Requirements: 5.3, 5.4, 5.5_

- [x] 15. H7/H8/H9/H10 勾稽规则与面板接入
  - H7 两版四层派生 + 产业行=类别行之和；H8 五层派生；H9 净额派生；H10 合计=分项和
  - _Requirements: 5.3, 5.4, 5.5_

- [x] 16. 勾稽守卫 + CI job `h-cycle-consistency`
  - `hDisclosureConsistency.spec.ts`：Property 11/12 + 逐循环规则断言 + PBT
  - _Requirements: 5.1, 5.4_

- [x] 17. 上市变体活体验证
  - 快照 `0ec33ac9` 的 `applicable_standard_v2` → 临时置 `entity_type=listed` → 验 H1~H10 上市披露 Tab 渲染与同步 → 逐字复原
  - 同时验国企项目上打开上市 Tab 显示「当前不适用」且零写入
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 18. H1/H2 真实数据端到端验证
  - 选含真实 `1601`/`1604` 余额的项目，验四表叶子聚合预填（叶子和 == 父科目期末）、披露层间派生、附注金额一致
  - 验证后复原
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 19. 收口
  - 更新 memory.md 任务状态与踩坑铁律
  - 清理本会话 `probe_*` / `tmp_*` 诊断产物
  - _Requirements: 1.5, 4.4, 6.4_

## Notes

### 探针实证（2026-07-31，本 spec 立项依据）

- **`**` 残迹**：`text_sections` 38 段 / 22 章节（listed 20 + soe 2）；`guidance` listed 14 + soe 8；`headers` 与 `rows[].label` 均 0 处。**2 段不成对**（`listed §十三、或有事项` 段23、`soe §九、【企业应当在附注` 段11，内容都是 `诉讼金额为**元`）→ 脱敏占位，必须保留。
- **H 披露 AI 现状**：H3（`generateH3AI` 真调 `/h3/ai-generate` 与通用端点）、H7（`runAi` 走共享 composable）、H10（`/h10/ai/disclosure-analysis`，端点存在于 `_h10_asset_disposal_income_ai.py`）**正常**；H8/H9 四 Tab 是 `emit('open-ai'|'open-review')` 而宿主 `@xxx=` 只有 `change`/`navigate-sheet`/`refresh-complete`/`save` → **死按钮**；H1/H2/H4/H5/H6 披露 Tab AI 按钮数 = 0。
- **H3 一度误报**：用 `body(s,'function generateAI')` 截函数体会吞掉 `async` 前缀，看起来像「非 async 函数里写 await」的语法错误；Vite transform 实测 200。**教训：括号配对截函数体时起点要含修饰符**。
- **`report_row_code`**：listed 96 行 + soe 38 行 = 134 行全部带 `account_codes`（故 `REPORT()` 不触发 = inert）；位移量不一致（固定资产差 14、存货差 2、应收票据差 1）→ 禁用统一偏移，必须按标签反查 `report_config`。
- **命名**：66 个 map 文件被生成器扫到；不匹配者仅 `mEquityChangeNoteSectionMap.ts`（属预期，由 m4/m5/m7 薄壳代表）；**H4 是唯一缺 map 的循环**（H6 已有）。
- **勾稽引擎**：全平台仅 `d1/f1/h1/j1/n1DisclosureConsistency.ts` 五份 + 7 个面板组件。

### 实测结论

**Wave 1（命名/registry）**：`gen_note_wp_sync_registry.py` 扩展支持嵌套双章节形态（`listed: { trading, derivative }`），修 G3/H6 标识符引用为内联字面量，新建 H4 薄壳。registry 62→67 条，既有 62 条零回归（逐字段 diff 确认）。前端守卫 23 绿 + 后端 68 绿。

**Wave 2（`**` 残迹）**：全库 58 处成对 `**`（listed 49 / soe 9）已剥离，2 处不成对脱敏占位（`诉讼金额为**元`）原样保留。隔离验证脚本证明剥离**只删除 `*` 字符**（去 `*` 后与 HEAD 逐字相等，delta 精确等于 4×对数）。后端 23 绿。

**Wave 3（H 循环 AI 接线）**：H8/H9 四个死按钮（`emit('open-ai'|'open-review')` 宿主零处理）+ H1/H2/H4/H5/H6 共 24 处文本域原无 AI，全部接入统一 `useHCycleDisclosureAi`。顺带修 H5 两版文本域**原无持久化**（刷新即丢）与 H5 复核**字符串签名错误**（平台签名是对象入参）。13 个 Tab 全部 Vite 200。后端新增 238 行 prompt 登记（7 循环 × 2 变体），交叉守卫 238 绿。

**Wave 4（`report_row_code`）**：134 行陈旧编号中 92 行按 `report_config.row_name` 唯一反查重映射成功（位移量 1~14 不一致，证伪「统一偏移」假设）；13 行库内确有歧义（同名多码，如「资本公积」BS-079/BS-083）或查不到，原样保留并逐条登记 allowlist 理由。二次运行 exit=0（幂等）。后端 10 绿。

**Wave 5（勾稽引擎）**：H1/D1/F1 三份既有引擎改委托 `shared/disclosureConsistency.ts` 的容差常量（值不变，H1 既有 18 例零回归）；新建 H2/H5/H8/H9/H10 五个规则文件并接入 `WpDisclosureConsistencyPanel`（H3/H7 的合计是纯 `sumOf` 自派生、无独立第二来源可比对，宁缺勿造未建）。全量 `src/components/workpaper` 19969 例 / 90 失败，13 个失败文件全部核实为预存在基线（`git status` 确认对应源文件本次未触碰）或已修复的过时测试断言（`useH10Disclosure.spec.ts` 5 处断言引用 H10 早前修复前的旧章节号/表名，已更新并验证 5/5 绿）。

**清理**：本会话全部 `probe_*` 诊断脚本与输出（backend 与仓库根）已删除；`report_row_code_index.json`（DB 反查快照，81KB）予以保留供 CI 离线消费。

**Wave 6（活体验证，2026-08-01 完成）**：

- **Task 17 上市变体活体验证**：临时把项目 `0ec33ac9` 的 `applicable_standard_v2.entity_type` 由 `soe` 改为 `listed`（用后端脚本 `CAST(:v AS jsonb)`，asyncpg 下 `:v::jsonb` 混合语法会报语法错误，须用 `CAST`）。chrome-devtools 打开 H1 上市披露 Tab：两级表头、5 个 AI 辅助按钮、勾稽面板「一致 10」全部正确渲染；点击「同步到附注」→ toast「已同步 39 行到附注「五、22」」→ postgres 只读确认 `last_sync_at` 由 `None` 前移、`source_template='listed'`。反向验证：国企项目 `2aa00f57`（`entity_type=soe`）打开 H1 上市 Tab 点同步 → `last_sync_at` 保持 `None`、`source_template` 保持 `soe`——变体门控生效、零写入。验证后立即 `--restore`，`applicable_standard_v2` 逐字段核对与快照 `{"scope":"standalone","stage":"normal","entity_type":"soe"}` 一致。
  - **踩坑记录**：验证同步动作前漏做 `disclosure_notes` 该条记录的快照（操作疏漏）。事后核实同项目其他未同步章节（§五、23/24/25）的形态确认「未同步」态 = 无 `sub_table_data`/`_source`/`_sub_table_columns`/`_last_sync_*`/`_current_standard`/`_note_texts` 顶层键、`last_sync_at=None`，`source_template` 是项目模板本身属性不受同步动作影响。据此把 §五、22 的 `table_data` 精确恢复到同构形态（保留原 `rows`，只删同步引入的键），最终态与兄弟章节逐字段一致。**教训**：改库前一律先查再改，本次因中间步骤多而漏做，所幸系统有足够多同构记录可比对复原，未造成数据丢失。
- **Task 18 H1/H2 真实数据端到端**：复用 Task 17 的同一次同步即完成验证（`0ec33ac9` 是含真实台账数据的项目）。postgres 只读核实叶子聚合：`tb_balance` 的 `1601.01+1601.02+1601.03+1601.04+1601.99 = 41,049,967.97+802,866.44+2,515,338.93+1,806,900.48+5,013,897.50 = 51,188,971.32`，精确等于父科目 `1601` 期末余额 `51,188,971.32`（叶子和==父额勾稽成立）。UI 层间派生（账面原值−累计折旧−减值准备=账面价值）与附注金额（固定资产合计 46,250,956.06 / 62,442,453.10）均与底稿显示一致。
- 全部验证后测试数据已逐字复原，无遗留破坏性变更。
