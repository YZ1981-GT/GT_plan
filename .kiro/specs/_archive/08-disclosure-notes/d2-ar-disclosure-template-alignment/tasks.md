# Implementation Plan: d2-ar-disclosure-template-alignment

## Overview

以源模板 `附注披露信息(上市公司)` sheet 为基准，分 5 个 Sprint 校正底稿层 / 同步层 / 附注层。
Sprint 1–2 恢复被压扁的列结构（收益最大），Sprint 3 补两张缺失表与文本节，
Sprint 4 修订附注模板，Sprint 5 清理改名遗留空表并收口验收。

## Tasks

- [x] 1. Sprint 1 — 底稿数据模型对齐源模板
  - [x] 1.1 重命名 `soeClassEndRows`/`soeClassPriorRows` → `classWideEndRows`/`classWidePriorRows`
    - `useD2DisclosureNote.ts` 导出名 + `D2DisclosureNoteBody.vue` 引用 + 快照字段
    - override key `soeClass:*` → `classWide:*`，`rehydrate()` 读时兼容旧键（写只写新键）
    - _Requirements: 1.1_

  - [x] 1.2 组合分表增 `priorProvision` 并派生双期损失率
    - `D2PortfolioRow` 增 `priorProvision: number`；hydrate/persist/新增行默认 0
    - 暴露 `portfolioLossRate(row, period)` 纯函数（坏账准备 ÷ 应收账款，分母 0 → 0）
    - _Requirements: 3.2_

  - [x] 1.3 分类宽表组合子行取组合分表坏账准备合计
    - 期末取 `Σ provision`、上年取 `Σ priorProvision`，替换 `provision: 0` 占位
    - `ratio` 分母按期分别取本期合计
    - _Requirements: 1.3, 1.4_

  - [x] 1.4 变动表首行口径与联动
    - `MOVEMENT_LABELS[0].label` → `上年年末余额`；autoSource 文案同步
    - `priorBalance` 自动值改取账龄表「减：坏账准备」上年年末列，D2-3 期初审定合计次级回退
    - 新增一致性检查：变动表期末余额 ↔ 分类披露期末坏账准备合计
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 1.5 终止确认行增 `transferMethod`，新增 `derecognition` 说明键
    - `D2DerecognizedRow` 增 `transferMethod: string`；hydrate/新增行默认 `''`
    - _Requirements: 4.1, 6.1_

- [x] 2. Checkpoint — Sprint 1 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 门槛：`npx vitest run` D2 相关全绿；底稿页可正常渲染（Vite transform 200）

- [x] 3. Sprint 2 — 同步层列头恢复源模板结构
  - [x] 3.1 分类披露双期 6 列列头
    - 改写 `CLASS_COLUMNS_LISTED_END/PRIOR` 为 6 列（`账面余额`/`坏账准备` 两组）
    - `buildD2SyncPayload` 上市分支改推 `classWideEndRows`/`classWidePriorRows` 五业务键
    - _Requirements: 1.1, 1.2_

  - [x] 3.2 单项计提双期 5 列列头
    - `INDIVIDUAL_COLUMNS_LISTED_END/PRIOR` = 名 称/账面余额/坏账准备/预期信用损失率（%）/计提依据
    - 合计行「计提依据」输出 `/`
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 组合分表专用列头（双期 6 值列）
    - 新增 `PORTFOLIO_COLUMNS_LISTED`，上市分支不再复用 `AGING_COLUMNS_LISTED`
    - 行输出 `end_amount/end_provision/end_loss_rate/prior_amount/prior_provision/prior_loss_rate`
    - _Requirements: 3.1, 3.3_

  - [x] 3.4 变动表首行行名同步
    - 上市 movement 行 `期初余额` → `上年年末余额`
    - _Requirements: 5.1_

  - [x]* 3.5 列头契约测试（P1/P2）
    - **Property 1: 列头字面一致 / Property 2: 双期同构**
    - **Validates: Requirements 1.1, 2.1, 3.1**
    - 断言各列头 label 与源模板字面一致；期末表/续表 key 序列等长、label 逐字相同

- [x] 4. Checkpoint — Sprint 2 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 门槛：同步载荷分类/单项/组合三类表列数分别为 6/5/7（含标签列）

- [x] 5. Sprint 3 — 补齐终止确认 / 继续涉入 / 文本节 / 法规上下文
  - [x] 5.1 同步层新增两表与两文本节
    - `D2_TABLE_NAMES.listed` 增 `derecognized` / `continuedInvolvement`
    - 新增 `DERECOGNIZED_COLUMNS_LISTED`（含转移方式）与 `CONTINUED_INVOLVEMENT_COLUMNS`
    - `D2_NOTE_TEXT_SECTIONS` 追加 `derecognition` / `continuedInvolvement`
    - _Requirements: 4.2, 6.1_

  - [x] 5.2 底稿组合分表改两级表头 6 值列
    - 上市版 `el-table-column` 分组：期末余额 / 上年年末余额 各 3 子列，损失率只读
    - _Requirements: 3.1_

  - [x] 5.3 底稿终止确认块补列与说明
    - 上市版增「转移方式」列、标签列 label 改 `项 目`；新增说明 textarea（含 A/B/C 占位）
    - _Requirements: 4.1, 4.3_

  - [x] 5.4 前五名「汇总披露格式」+ 15 号文法规上下文
    - 前五名块加汇总披露范式文本与二选一提示
    - 变动重要转回 / 核销逐项 / 前五名 / 终止确认 / 继续涉入 5 处加 `.methodology-context`
    - _Requirements: 6.2, 6.3_

- [x] 6. Checkpoint — Sprint 3 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 门槛：上市同步载荷固定表 = 13 张（含双期拆表）+ `_note_texts` 9 节

- [x] 7. Sprint 4 — 附注模板 五、5 结构修订
  - [x] 7.1 编写幂等修订脚本 `fix_note_ar_listed_structure.py`
    - 重写 五、5 `tables`：分类/单项双期拆表 + 两级表头 `columns`/`_column_groups`、
      组合分表补 `账龄` 标签列、账龄 10 行、变动首行、前五名表名、新增终止确认表
    - 追加 `text_sections`：终止确认说明 A/B/C、继续涉入说明
    - 幂等标记 `_aligned_by: 'd2-ar-disclosure-template-alignment'`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 7.2 执行脚本并核对产出
    - 运行后重跑 `_dump` 核对 五、5 结构；确认 JSON 合法且 `note_template_service` 可加载
    - _Requirements: 7.1_

  - [x]* 7.3 结构契约测试（P8 + R7）
    - **Property 8: 模板幂等**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7**
    - 断言 五、5 表名集合/列头/行口径符合源模板；脚本连跑两次结果相等

- [x] 8. Checkpoint — Sprint 4 验收
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Sprint 5 — 改名遗留空表清理 + 收口
  - [x] 9.1 后端支持 `_removed_table_keys`
    - `_extract_note_texts` 同款剥离元数据键；浅合并后删除（跳过本次推送键）
    - 同步删除 `_sub_table_columns` 对应键
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 9.2 前端上报遗留键
    - `D2_LISTED_OBSOLETE_TABLE_KEYS` 随载荷写入 `sub_table_data._removed_table_keys`
    - _Requirements: 8.1_

  - [x]* 9.3 删除语义测试（P7）
    - **Property 7: 删除不误伤**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - 断言删除既有键、跳过本次推送键、未声明时不清空

  - [x] 9.4 清理临时脚本并跑全量回归
    - 删除 `scripts/_dump_d2_listed_sheet.py`、`scripts/_dump_note_tpl_ar.py` 及 dump 产物
    - `python -m pytest` 相关子集 + `npx vitest run` D2 子集
    - _Requirements: 全部_

- [x] 10. Checkpoint — 最终验收
  - 编译与单测：4 个改动前端文件 Vite transform 均 200；`d2NoteSectionMap.spec.ts` +
    `d2DisclosureNote.spec.ts` 46 项全绿；后端 `test_wp_disclosure_sync` / 投影器 /
    模板契约全绿。
  - **交互实测已完成（2026-07-30，chrome-devtools MCP + postgres MCP，项目 `c8621493` /
    wp `6d5bd4a6`）**：上市披露 TAB 正确挂载（`披露版本：上市公司版（五、5）`，10 张表，
    证明 wp_code 后缀 `附注披露信息(上市公司）D2-1` 的分发修复生效）→ 录入账龄 + 逐节说明
    → 点「同步到附注」→ 落库 §五、5 共 **12 张子表**、`按坏账计提方法分类披露` 与
    `（续：上年年末余额）` **各 6 列**（`账面余额/金额`·`账面余额/比例(%)`·
    `坏账准备/金额`·`坏账准备/预期信用损失率(%)`·`账面价值`，两级 `group` 齐备）、
    `text_content` **10 节说明标题齐备**。清空后重新同步 `text_content` 归零，无残留。
  - 🔴 **实测揪出一个缺陷并已修**：`D2_NOTE_TEXT_SECTIONS` 声明 10 节、AI 按钮也备好了
    `ctx.组合计提项目` 上下文，但 `D2DisclosureNoteBody.vue` **缺 `portfolio` 那个说明
    文本域** → AI 生成的组合说明既看不见也改不了，同步永远只落 9 节（首轮实测实测到
    9 节即此因）。已在「组合计提项目」卡片补上 `sectionNotes['portfolio']` 文本域，
    复测 10 节全落。
  - _Requirements: 全部_

## Task Dependency Graph

```
1.1 ─┬─> 1.3 ─┐
1.2 ─┘        ├─> 2 (Checkpoint) ─> 3.1 ─┐
1.4 ─────────┤                    3.2 ─┤
1.5 ─────────┘                    3.3 ─┼─> 3.5 ─> 4 (Checkpoint) ─> 5.1 ─┐
                                  3.4 ─┘                            5.2 ─┤
                                                                    5.3 ─┼─> 6 (Checkpoint)
                                                                    5.4 ─┘        │
                                                                                  v
                                                            7.1 ─> 7.2 ─> 7.3 ─> 8 (Checkpoint)
                                                                                  │
                                                                                  v
                                                            9.1 ─> 9.2 ─> 9.3 ─> 9.4 ─> 10
```

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.4", "1.5"] },
    { "wave": 2, "tasks": ["1.3"] },
    { "wave": 3, "tasks": ["2"] },
    { "wave": 4, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "wave": 5, "tasks": ["3.5"] },
    { "wave": 6, "tasks": ["4"] },
    { "wave": 7, "tasks": ["5.1"] },
    { "wave": 8, "tasks": ["5.2", "5.3", "5.4"] },
    { "wave": 9, "tasks": ["6"] },
    { "wave": 10, "tasks": ["7.1"] },
    { "wave": 11, "tasks": ["7.2"] },
    { "wave": 12, "tasks": ["7.3"] },
    { "wave": 13, "tasks": ["8"] },
    { "wave": 14, "tasks": ["9.1"] },
    { "wave": 15, "tasks": ["9.2"] },
    { "wave": 16, "tasks": ["9.3"] },
    { "wave": 17, "tasks": ["9.4"] },
    { "wave": 18, "tasks": ["10"] }
  ]
}
```

依赖说明：

- `1.1`（重命名）先行，`1.3` 复用重命名后的宽表行；`1.2` 提供 `priorProvision` 供 `1.3` 汇总。
- Sprint 2（同步层）依赖 Sprint 1 的模型字段，否则推不出五业务键。
- `5.2`/`5.3` 底稿 UI 改动依赖 `5.1` 的列头常量与表名常量。
- Sprint 4（附注模板）独立于 Sprint 1–3，但排在其后以源模板结论为唯一基准，避免两次返工。
- `9.2` 依赖 `9.1` 的后端删除能力；`9.4` 为最终清理，须在全部实现任务完成后执行。

## Notes

- **可选任务标记 `*`**：本项目约定 optional 任务同样必须完成（见 steering `memory.md`），
  `*` 仅表示「测试类任务」，不表示可跳过。
- **持久化兼容**：`1.1` 的 override key 迁移采用「读兼容、写新键」，不引入 fallback 死代码；
  下一次保存后旧键自然消失。
- **不触碰致同源 md**：`基础数据/附注模版/上市报表附注.md` 为外部权威文档，只读。
- **模板重建风险**：`scripts/fix/rebuild_note_from_md.py` 会重新生成
  `note_template_listed.json` 并丢失多级表头，故 `7.1` 必须做成幂等脚本 + 契约测试兜底。
- **UI 铁律**：新增金额列一律右对齐 + `fmtAmount`；比例/损失率列不套用金额格式化器；
  Vue 模板属性禁用中文引号（`“”` 会触发 Vite 编译崩溃）。
