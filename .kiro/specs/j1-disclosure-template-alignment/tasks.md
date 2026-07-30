# Tasks — J1 披露表 ↔ 附注模板对齐

- [ ] 1. 附注模板幂等修订脚本
- [ ] 1.1 新建 `backend/scripts/fix/fix_note_j1_employee_comp_structure.py`（`--dry-run`/`--check`/`_aligned_by`，按 `aliases` 游标匹配保幂等）
  - _Requirements: R1, R2, R7.1_
- [ ] 1.2 soe 八、40 第 3 表改名 `短期薪酬列示` → `设定提存计划列示`（消重名）
  - _Requirements: R1.1_
- [ ] 1.3 6 张表补 `columns`（5 列，标签列 `flat` + 4 金额列 `format: amount`）+ `_column_groups: []`
  - _Requirements: R1.2, R1.5_
- [ ] 1.4 6 张表补 `guidance`（源模板红字 + CAS 9 + 「勾稽：」前缀的实证公式）
  - _Requirements: R1.3_
- [ ] 1.5 listed 表2 删 `……` 占位行，语义移入 `guidance`
  - _Requirements: R1.4_
- [ ] 1.6 `text_sections` 补齐：listed 4 段说明 + 现金流量注；soe 追加 3 条说明正文（不得用 `####` 前缀）
  - _Requirements: R2_
- [ ] 1.7 执行 `--dry-run` 复核后 apply，再跑 `--check` 确认幂等
  - _Requirements: R7.1_

- [ ] 2. 后端结构守卫
- [ ] 2.1 新建 `backend/tests/services/test_note_j1_employee_comp_structure.py`（表名/表数/columns 三态/guidance 非空/无 `……` 行/text_sections 关键词）
  - _Requirements: R7.1_
- [ ] 2.2 CI job `note-j1-structure` 挂 `governance-checks.yml`
  - _Requirements: R7.1_

- [ ] 3. 勾稽引擎（纯函数）
- [ ] 3.1 新建 `j1DisclosureConsistency.ts`（6 类规则，容差 0.01 元，返回 `J1CheckResult[]`）
  - _Requirements: R3.2, R3.3, R3.4, R3.6_
- [ ] 3.2 新建 `j1DisclosureConsistency.spec.ts`（正向全平 + **反向**制造差异必须报出）
  - _Requirements: R7.3_

- [ ] 4. 父行派生
- [ ] 4.1 `useJ1DisclosureSections.ts` 新增纯函数 `applyParentSums(rows)`（非缩进行后紧跟连续缩进行时，父行三列 = 子行之和）
  - _Requirements: R3.1_
- [ ] 4.2 `hydrate` / `onRowChange` / 增删行后调用；派生行在 UI 标公式单元格
  - _Requirements: R3.1_
- [ ] 4.3 单测覆盖：无子行时不改动、多组父子、新增子行后自动生效
  - _Requirements: R7.3_

- [ ] 5. 展示组件
- [ ] 5.1 新建 `J1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细 + 规则 tooltip，13px）
  - _Requirements: R3.5_

- [ ] 6. 底稿披露表改造（上市）
- [ ] 6.1 方法论上下文块（琥珀色）移到表1 上方；合并重复 `details`
  - _Requirements: R4.3_
- [ ] 6.2 挂勾稽面板；表2/表3 父行改公式单元格（虚线 + tooltip）
  - _Requirements: R3.1, R3.5_
- [ ] 6.3 辞退福利说明 placeholder 改源模板 R54 原文口径
  - _Requirements: R4.1_
- [ ] 6.4 删死代码 `import GtIndexChip`
  - _Requirements: R4.4_

- [ ] 7. 底稿披露表改造（国企）
- [ ] 7.1 方法论上下文块 + 勾稽面板 + 父行公式单元格
  - _Requirements: R3.1, R3.5, R4.3_
- [ ] 7.2 说明拆 3 个文本域（各带 AI 辅助），placeholder 用源模板 R42~R44 完整原文
  - _Requirements: R4.2_

- [ ] 8. 载荷映射
- [ ] 8.1 `j1NoteSectionMap.ts` 头注释撤销 Decision 3；`SOE_NOTE_KEYS` 扩为 3 段
  - _Requirements: R6.1, R6.2_
- [ ] 8.2 新建 `j1NoteSubtableContract.spec.ts` 接共享 helper（5 Property）
  - _Requirements: R7.2_

- [ ] 9. AI prompt
- [ ] 9.1 `wp_guidance_chat._SECTION_PROMPTS` 追加 6 条 J1 披露 section（≥20 字 + 源模板口径 + 不得虚构）
  - _Requirements: R5_
- [ ] 9.2 新建 `backend/tests/test_j1_ai_sections.py` 参数化守卫
  - _Requirements: R5.2_

- [ ] 10. 验证
- [ ] 10.1 前端 J1 相关 vitest 全绿 + 改动文件 `get_diagnostics` 清 + Vite transform 200
  - _Requirements: R7_
- [ ] 10.2 后端 J1/附注相关 pytest 全绿
  - _Requirements: R7_
- [ ] 10.3 浏览器实测国企侧：底稿录入 → 勾稽面板 → 同步 → 附注八、40 三张表 + 文本区（postgres 只读验 `_last_sync_at` + 字段值）
  - _Requirements: R7.4_
- [ ] 10.4* 上市侧：无活体 listed 项目（8 个在册全 soe）→ 记录为未活测，靠契约测试 + 纯函数单测覆盖
  - _Requirements: R7.4_

- [ ] 11* 可选（本轮不做，另立任务）
- [ ] 11.1* 披露表导入导出（复用 F2 `_f2_disclosure_import_export.py` 表驱动范式，3 区块 3 sheet + 文本说明 sheet）
- [ ] 11.2* `el-input-number` → `WpAmountInput`（平台级存量替换 spec 统一收口）
