# 实施计划：K2 披露表 ↔ 附注对齐

- [ ] 1. 附注模板结构修订（幂等脚本）
- [ ] 1.1 建 `backend/scripts/fix/fix_note_k2_structure.py`：§五、13 表②③重命名 + 表② `headers[0]` 修正 + 表③删 `header_label` 假行
  - _Requirements: 4.1, 4.2, 4.3, 4.5_
- [ ] 1.2 同脚本补 4 张表的 `columns`（显式 `flat`）+ `guidance`（源模版 text_sections + 校验预设勾稽 + 数据来源）
  - _Requirements: 4.4_
- [ ] 1.3 `--dry-run` 核对 diff 后 `--apply`，再 `--check` 验幂等
  - _Requirements: 4.5_

- [ ] 2. 同步映射模块重写
- [ ] 2.1 `k2NoteSectionMap.ts`：`sheet_name` 改全角括号；加子表名常量、历史表名常量、行名常量
  - _Requirements: 5.1, 5.3_
- [ ] 2.2 加 `buildK2ListedColumns` / `buildK2SoeColumns`（全部 `flat`）
  - _Requirements: 1.1, 1.2, 5.2_
- [ ] 2.3 重写 `buildK2SyncPayload`：3 表 / 1 表、`_note_texts`、`_removed_table_keys`
  - _Requirements: 2.4, 3.3, 5.3_
- [ ] 2.4 重跑 `gen_note_wp_sync_registry.py --write`
  - _Requirements: 5.4_

- [ ] 3. 纯函数引擎
- [ ] 3.1 `composables/useK2DisclosureEngine.ts`：`sumMainRows` / `recalcContractCost` / `checkK2Consistency`
  - _Requirements: 1.5, 2.2, 6.1_

- [ ] 4. 底稿披露组件重写
- [ ] 4.1 `K2TabDisclosureListed.vue`：主表三列 + 13 固定行 + 动态行 + 合计公式行，金额用 `WpAmountInput`
  - _Requirements: 1.1, 1.3, 1.4, 1.5_
- [ ] 4.2 上市补「合同取得成本」区块（类别列增删 + 公式行 + 启用开关）
  - _Requirements: 2.1, 2.2, 2.4_
- [ ] 4.3 上市补「碳排放配额变动情况」区块（11 固定行 + 启用开关）
  - _Requirements: 2.3, 2.4_
- [ ] 4.4 上市文本区三段 + 每段 AI 按钮（prompt ≥20 字、含「不得虚构」）
  - _Requirements: 3.1, 3.4_
- [ ] 4.5 勾稽校验 bar（紧凑单行 + 折叠明细 + 规则 tooltip）
  - _Requirements: 6.1_
- [ ] 4.6 `K2TabDisclosureSoe.vue`：主表三列 + 8 固定行 + 一段文本 + 勾稽
  - _Requirements: 1.2, 1.3, 3.2_

- [ ] 5. 守卫
- [ ] 5.1 `k2NoteSubtableContract.spec.ts` 接入共享 helper
  - _Requirements: 6.1_
- [ ] 5.2 `disclosureColumnsCoverage.spec.ts` 登记 `P1_ROUTE`
  - _Requirements: 6.2_
- [ ] 5.3 `backend/tests/services/test_note_k2_structure.py`
  - _Requirements: 6.3_
- [ ] 5.4 引擎单测（合计 / 公式 / 勾稽 / `_removed_table_keys`）
  - _Requirements: 6.1_

- [ ] 6. 验证
- [ ] 6.1 前端 vitest（K2 相关 + 三个跨循环守卫）+ 后端 pytest 全绿
  - _Requirements: 6.1, 6.2, 6.3_
- [ ] 6.2 浏览器实测：录入 → 自动同步 → 查 `disclosure_notes.table_data` 落库
  - _Requirements: 6.4_
