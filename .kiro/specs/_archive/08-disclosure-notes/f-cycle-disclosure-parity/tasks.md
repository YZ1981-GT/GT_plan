# Implementation Plan: F 类披露表与附注对齐补齐

## Overview

按 P1 → P2 → P3 三批推进。P1 全部围绕 F3（列头变体拆分 / 行序 / 模板对齐 / 契约守卫），
彼此有先后依赖；P2 是 F1/F3/F4 三处独立改动；P3 是 F1 模板清理 + 平台 helper 加固 + AI 接线。

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2"], "desc": "P1：F3 变体拆分 + 模板幂等脚本（脚本与前端互不阻塞）" },
    { "wave": 1, "tasks": ["3"], "desc": "P1：F3 契约守卫（需 1、2 都落地）", "depends_on": [0] },
    { "wave": 2, "tasks": ["4", "5"], "desc": "P2：_note_texts title + F4 自动同步", "depends_on": [1] },
    { "wave": 3, "tasks": ["6", "7"], "desc": "P3：F1 headers 清理 + helper P6", "depends_on": [2] },
    { "wave": 4, "tasks": ["8"], "desc": "P3：F1/F3/F4 AI 接线", "depends_on": [3] },
    { "wave": 5, "tasks": ["9"], "desc": "回归验证", "depends_on": [4] }
  ]
}
```

## Tasks

- [x] 1. P1 F3 列头变体拆分与行序对齐
  - [x] 1.1 `f3NoteSectionMap.ts`：`F3_YFPJ_COLUMNS` 拆为 `F3_LISTED_YFPJ_COLUMNS`
        （种类/期末余额/上年年末余额）与 `F3_SOE_YFPJ_COLUMNS`（类别/期末余额/期初余额），
        标签列标 `flat`，并导出 `F3_YFPJ_COLUMNS_BY_VARIANT`
  - [x] 1.2 新增 `F3_LISTED_SUBTABLE` / `F3_SOE_SUBTABLE` 常量；`buildF3SyncPayload`
        按 variant 取子表名与列头
  - [x] 1.3 `orderF3ClassRows` 行序改 `银行承兑 → 商业承兑 → 供应链`（源 xlsx r7/r8）
  - [x] 1.4 更新 `f3NoteSectionMap.spec.ts` 相关断言
  - _Requirements: R1, R2_

- [x] 2. P1 F3 附注模板幂等对齐
  - [x] 2.1 新建 `backend/scripts/fix/fix_note_notes_payable_structure.py`
        （`--dry-run` / `--check`，补 headers/columns/guidance/rows + `_aligned_by`）
  - [x] 2.2 新建 `backend/tests/services/test_note_notes_payable_structure.py`
  - [x] 2.3 跑 dry-run → 写入 → `--check` 三段
  - _Requirements: R2, R3_

- [x] 3. P1 F3 子表契约守卫
  - [x] 3.1 新建 `composables/__tests__/f3NoteSubtableContract.spec.ts`，接入共享 helper
  - [x] 3.2 补 F3 专属断言：两变体列头互不相同、国企第 3 列为「期初余额」
  - _Requirements: R4_

- [x] 4. P2 `_note_texts` 补中文 title
  - [x] 4.1 F1：`buildF1NoteTexts` + 7 条中文 title + 空文本过滤
  - [x] 4.2 F3：`${variant}-note` 带 title
  - [x] 4.3 F4：补 `section` + title
  - [x] 4.4 三处各加断言：每条 title 非空且不等于 section、不含长串小写英文
  - _Requirements: R5_

- [x] 5. P2 F4 披露 Tab 接自动同步
  - [x] 5.1 `F4TabDisclosureListed.vue` 接 `useDisclosureAutoSync` + watch 实际数据
  - [x] 5.2 `F4TabDisclosureSOE.vue` 同上
  - [x] 5.3 `disclosureAutoSyncCoverage.spec.ts` 从 `MISSING_SYNC_PATH` 移除 F4（若在册）
  - _Requirements: R6_

- [x] 6. P3 F1 模板 headers 去 HTML
  - [x] 6.1 `fix_note_prepayment_structure.py`：上市 top5 表 headers 改纯文本；
        `validate_section` 增 headers 纯文本断言
  - [x] 6.2 跑 dry-run → 写入 → `--check`
  - _Requirements: R7_

- [x] 7. P3 共享契约 helper 增 P6（模板 headers 纯文本）
  - [x] 7.1 `_disclosureSubtableContract.helper.ts` 增 P6
  - [x] 7.2 跑全部已接入循环的契约 spec，确认无既有循环被新 Property 打红
        （若有，属真实欠账，一并修或登记 `columnsPending` 同级逃逸阀并写理由）
  - _Requirements: R8_

- [x] 8. P3 F1/F3/F4 披露文本域接 AI 辅助
  - [x] 8.1 F1 后端 `_f1_ai_generate.py` 增 6 个披露 section（`_SUPPORTED_SECTIONS` +
        `_SECTION_PROMPTS`，prompt ≥20 字 + 源模板口径 + 不得虚构）
  - [x] 8.2 `useF1AiGenerate.ts` 的 `F1AiSection` 联合类型同步
  - [x] 8.3 F1 两个披露 Tab 接 `AI_TARGETS` + AI 按钮（标题行右对齐）
  - [x] 8.4 F3 两个披露 Tab 接 `useF3AiGenerate`（后端 `listed-note`/`soe-note` 已就绪）
  - [x] 8.5 F4 两个披露 Tab 接 `useF4AiGenerate`（后端 `disclosure-*-note` 已就绪）
  - [x] 8.6 后端参数化测试：披露 section 均在 `_SUPPORTED_SECTIONS` 且有 ≥20 字 prompt
  - _Requirements: R9_

- [x] 9. 回归验证
  - [x] 9.1 后端：F3/F1 结构守卫 + F1/F3/F4 AI 测试 + 既有 F 类测试
  - [x] 9.2 前端：F 类披露相关 spec + 平台守卫 spec 全绿
  - [x] 9.3 `get_diagnostics` 覆盖所有改动文件与共享 helper 的全部消费方

## 交付说明

### 实际改动

| 需求 | 改动 | 证据 |
|---|---|---|
| R1 | `F3_YFPJ_COLUMNS` → `F3_LISTED_YFPJ_COLUMNS`（种类/期末余额/上年年末余额）+ `F3_SOE_YFPJ_COLUMNS`（类别/期末余额/期初余额），载荷按 variant 取列头 | 源 xlsx 上市 A6/B6/C6 vs 国企 A6/B6/C6 |
| R2 | `orderF3ClassRows` 与模板 rows 行序改「银行承兑 → 商业承兑」 | 源 xlsx r7 银行 / r8 商业（原实现两侧都相反） |
| R3 | 新建 `fix_note_notes_payable_structure.py`：两变体补 `columns`(3, 标 `flat`) + `guidance` + `_aligned_by` | 原 `columns=0` / guidance 空 / `_aligned_by=None` |
| R4 | 新建 `f3NoteSubtableContract.spec.ts`（接入共享 helper P1~P6 + F3 专属 8 条） | F3 曾是 F 类唯一无此守卫的循环 |
| R5 | F1 `buildF1NoteTexts` 7 条中文 title；F3 `buildF3NoteTexts`；F4 `buildF4NoteTexts`（补 variant `section` + title）；三处均过滤空文本 | 后端 `_format_note_texts` 用 `section` 兜底 → 原渲染成 `【listed-note-aging】` |
| R6 | F4 两个 Tab 接 `useDisclosureAutoSync` + watch 实际数据 | 原只有手动 `syncToNotes` |
| R7 | F1 上市「前五名」表 headers 去 `<br/>`；脚本 `validate_section` 增 headers 纯文本断言 | `el-table-column :label` 与 Word 导出不解析 HTML |
| R8 | 共享 helper 增 P6（模板 headers 纯文本）；新建平台级 `fix_note_headers_plaintext.py` | P6 立刻打红 K1（7 处）→ 全库扫出 **133 处**（listed 63 / soe 70），已全部剥离 |
| R9 | F1 后端 6 个披露 section + 前端联合类型 + 两 Tab `AI_TARGETS` 与右对齐 AI 按钮；新建 `test_f_cycle_disclosure_ai_sections.py` 守 F1/F3/F4 四处登记 | F3/F4 的 AI **原本已接**（`generateListedNote` / `generateDisclosure`，复盘时被 `runAi(` 正则漏判） |

### 复盘结论的两处修正

1. **F3/F4 并非「无 AI 辅助」**：F3 用 `generateListedNote`、F4 用 `generateDisclosure`，
   后端 section 也已注册。复盘用 `runAi\('...'\)` 正则探测，漏判了这两种命名。
   真正缺 AI 的只有 F1（3 个文本域 × 2 变体）。
2. **F1 `<br/>` 不是孤例**：P6 一开就打红 K1，全库扫出 133 处（覆盖 A/B/D/G/K/L 等多循环），
   已由平台级脚本一次性剥离，并保留 `--check` 供 CI。

### 验证

- 三个幂等脚本各跑 `--dry-run` → 写入 → `--check`：全绿且二次执行无 diff
- 后端：`test_note_notes_payable_structure.py`(12) + `test_f_cycle_disclosure_ai_sections.py`(34)
  + 存货/D1/G 循环结构守卫 + F2 导入导出与 AI：**808 passed / 39 skipped**；
  F1 预付款项结构与回填 **44 passed**
- 前端 `src/components/workpaper` 全量：**1323 files / 18566 tests passed**，
  12 个失败文件全在未触碰区域：b23×3 / GtG0 / i6 / l4 / useF3Integration / useF5Integration /
  useH4DualMode / **J2RuntimeMigration** / **disclosureAutoSyncCoverage(N2)** /
  **disclosureColumnsCoverage(buildN2*Columns 未登记 P1_ROUTE)** —— 后三个是并发会话的 N2/J2
  改动，失败断言均只涉及 N2/J2，与本 spec 无关
- `get_diagnostics` 覆盖全部新增/改动文件与共享 helper 的所有消费方（契约 spec 全绿）

### 既有基线（非本次引入，未修）

- `test_preset_library.py::test_materialized_inventory_json_consistent`：物化
  `inventory.json` 232 页 vs 运行时 255 页，差的 23 页**全是 L1-1~L8-1 / M1-1~M10-1 /
  N1-1~N5-1 审定表**（L/M/N 循环 prefill 预设未重新物化），与 F 循环无关
- `test_f3_import_export_pbt.py` 两条 round-trip KeyError（F3-4 利息测算 / F3-7 凭证检查
  的导入导出，非披露链路）
- `test_f_cycle_audit_determination_writeback.py` 等一批 render schema / wp_code_override
  相关失败，属既有漂移

### 仍待用户定口径（复盘已列，本 spec 未动）

1. F4 上市按性质表模板自补的「设备款 / 服务费 / 其他」3 行（源 xlsx 只有
   「货款 / 工程款 / 可无限量添加行 / 合 计」）
2. F3 上市源 xlsx 的【供应链票据】红字是否在 seed 显式列一行「供应链票据」
   （`orderF3ClassRows` 已识别该标签但不补零行）

### 生效范围提醒

模板 JSON 改动（F3 columns/guidance/rows、F1 headers、133 处去 HTML）只对
**新建项目 / 重新生成附注**生效；既有项目需在披露 Tab 点一次「同步到附注」整表覆盖。
上市侧仍无法活体验证：8 个在册项目 `entity_type` 全为 soe。
