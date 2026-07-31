# Implementation Plan: K2 其他流动资产披露表 ↔ 附注对齐

## Overview

三层同时对齐：底稿两版披露表（上市/国企）→ 同步载荷 `columns` → 附注模板 §五、13 / §八、14。

先做三源核查与裁决（源 xlsx / 附注模版 / 校验预设），再以幂等脚本修订附注模板（表名、标签列、假数据行、`columns`、`guidance`），
然后重写同步载荷契约（sheet 名全角、3 表/1 表、`_removed_table_keys`），最后重写两版底稿 UI 并浏览器实测全链路。

## Task Dependency Graph

```
0 (三源核查/裁决)
   ├──> 1 (附注模板幂等修订) ──> 2 (同步映射重写) ──┬──> 4 (底稿两版 UI) ──┐
   │                                                └──> 3 (纯函数引擎) ──┤
   └───────────────────────────────────────────────────────────────────────┴──> 5 (守卫) ──> 6 (验证)
```

- `1` 阻塞 `2`（子表名 / 列键 / 标签列头需与模板逐字一致）
- `3` 依赖 `2`（引擎复用行常量与快照类型）
- `4` 依赖 `2`+`3`
- `5` 同时读模板侧与载荷侧，故依赖 `1`~`4`
- `6` 依赖 `5`

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "desc": "附注模板幂等修订（§五、13 / §八、14）" },
    { "wave": 1, "tasks": ["2"], "desc": "同步映射与载荷契约重写", "depends_on": [0] },
    { "wave": 2, "tasks": ["3"], "desc": "纯函数引擎", "depends_on": [1] },
    { "wave": 3, "tasks": ["4"], "desc": "底稿上市 / 国企披露组件重写", "depends_on": [2] },
    { "wave": 4, "tasks": ["5"], "desc": "守卫（契约测试 / P1_ROUTE / 后端结构 / CI）", "depends_on": [3] },
    { "wave": 5, "tasks": ["6"], "desc": "测试回归与浏览器实测", "depends_on": [4] }
  ]
}
```

## Tasks

- [x] 1. 附注模板结构修订（幂等脚本）
  - [x] 1.1 建 `backend/scripts/fix/fix_note_k2_structure.py`：§五、13 表②③重命名 + 表② `headers[0]` 修正 + 表③删 `header_label` 假行
    - _Requirements: 4.1, 4.2, 4.3, 4.5_
  - [x] 1.2 同脚本补 4 张表的 `columns`（显式 `flat`）+ `guidance`（源模版 text_sections + 校验预设勾稽 + 数据来源）
    - _Requirements: 4.4_
  - [x] 1.3 `--dry-run` 核对 diff 后 apply，再 `--check` 验幂等
    - _Requirements: 4.5_

- [x] 2. 同步映射模块重写
  - [x] 2.1 `k2NoteSectionMap.ts`：`sheet_name` 改全角括号；加子表名常量、历史表名常量、行名常量
    - _Requirements: 5.1, 5.3_
  - [x] 2.2 加 `buildK2ListedColumns` / `buildK2SoeColumns`（全部 `flat`）
    - _Requirements: 1.1, 1.2, 5.2_
  - [x] 2.3 重写 `buildK2SyncPayload`：3 表 / 1 表、`_note_texts`、`_removed_table_keys`
    - _Requirements: 2.4, 3.3, 5.3_
  - [x] 2.4 重跑 `gen_note_wp_sync_registry.py --write`
    - _Requirements: 5.4_

- [x] 3. 纯函数引擎
  - [x] 3.1 `composables/useK2DisclosureEngine.ts`：`sumMainRows` / `recalcContractCost` / `contractCostRowTotal` / `checkK2Consistency` / `k2ConsistencySummary`
    - _Requirements: 1.5, 2.2, 6.1_

- [x] 4. 底稿披露组件重写
  - [x] 4.1 `K2TabDisclosureListed.vue`：主表三列 + 13 固定行 + 动态行 + 合计公式行，金额用 `WpAmountInput`
    - _Requirements: 1.1, 1.3, 1.4, 1.5_
  - [x] 4.2 上市补「合同取得成本」区块（类别列增删改名 + 公式行 + 启用开关）
    - _Requirements: 2.1, 2.2, 2.4_
  - [x] 4.3 上市补「碳排放配额变动情况」区块（10 固定行 + 启用开关）
    - _Requirements: 2.3, 2.4_
  - [x] 4.4 上市文本区三段 + 每段 AI 按钮（prompt ≥20 字、含「不得虚构」）
    - _Requirements: 3.1, 3.4_
  - [x] 4.5 勾稽校验 bar（紧凑单行 + 折叠明细 + 规则 tooltip）
    - _Requirements: 6.1_
  - [x] 4.6 `K2TabDisclosureSoe.vue`：主表三列 + 8 固定行 + 一段文本 + 勾稽
    - _Requirements: 1.2, 1.3, 3.2_

- [x] 5. 守卫
  - [x] 5.1 `k2NoteSubtableContract.spec.ts` 接入共享 helper（34 测试）
    - _Requirements: 6.1_
  - [x] 5.2 `disclosureColumnsCoverage.spec.ts` 登记 `P1_ROUTE`
    - _Requirements: 6.2_
  - [x] 5.3 `backend/tests/services/test_note_k2_structure.py`（16 测试，含反向自检）
    - _Requirements: 6.3_
  - [x] 5.4 引擎单测（合计 / 公式 / 勾稽 / 容差）15 测试
    - _Requirements: 6.1_
  - [x] 5.5 CI job `note-k2-structure`（`--check` + pytest）
    - _Requirements: 6.3_

- [x] 6. 验证
  - [x] 6.1 前端 vitest 94 绿（K2 契约 34 + 引擎 15 + 三个跨循环守卫 45）+ 既有 K2 套件 99 绿 + 后端 16 绿
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 6.2 浏览器实测（chrome-devtools 驱动 + postgres 只读比对）
    - _Requirements: 6.4_

## Notes

### 浏览器实测结论（2026-07-30，项目 2aa00f57 / K2 底稿 d5f0d168）

- 国企：3 列表头「项目 / 期末余额 / 期初余额」、8 固定行、千分符 `1,234,567.50`、合计自动汇总
  → §八、14 落库 `sub_table_data` 1 表 + `_sub_table_columns` 带 `flat`
  + `_last_sync_sheet=附注披露信息（国企）`；文本经 `_note_texts` 写入
  `text_content = 【其他流动资产说明】…`。
- 上市：3 表 + 3 文本段；②表期末余额 105,000 = 100,000 + 30,000 − 20,000 − 5,000（合计列同值）；
  ③表 10 行行名逐字（含全角 `．`）→ §五、13 落库 3 表 + `text_content = 【金额较大的其他流动资产说明】…`。
- 关闭③开关 → `sub_table_data` / `_sub_table_columns` 均降为 2 表（`_removed_table_keys` 生效），再开启复原。
- 附注编辑器 §八、14 渲染「项目 / 期末余额 / 期初余额」+ 数据可见（该项目模板为国企版，
  §五、13 不在目录树内，故上市侧以 DB 落库为准）。

### 遗留（本 spec 范围外，需另立 spec）

- **K8 / K9 / K10 / K11 / K12 / K13 的 `X_DISCLOSURE_SHEET_NAME` 是半角括号，源 xlsx tab 名是全角** ——
  与 K2 修复前同一类漂移，会让附注「打开同步底稿」的 `?sheet=` 精确匹配落空。
  另 **K1 上市**源 xlsx tab 名是**前半角后全角** `附注披露信息(上市公司）`，常量写的是全角全角。
- 既有项目的附注 `_tables` 是生成时快照，不随模板改动更新（表②③在从未同步过的老项目仍是旧表名）。
  存量修复范式：`backend/scripts/fix/backfill_note_prepayment_snapshots.py`。
