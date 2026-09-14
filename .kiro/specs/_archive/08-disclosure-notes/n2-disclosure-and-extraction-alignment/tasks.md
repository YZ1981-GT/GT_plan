# Implementation Plan: N2 应交税费披露与四表取数对齐

## Overview

修正科目分类 bug、补齐源模板 13 税种行骨架、打通审定表→披露表数据自动带入、附注模板同步扩行。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "归一映射表 + classify 修正",
      "tasks": ["1.1", "1.2", "1.3"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "披露行骨架 + 附注模板扩行",
      "tasks": ["2.1", "2.2", "2.3"],
      "depends_on": ["1.1"]
    },
    {
      "wave": 3,
      "name": "审定表→披露表数据带入",
      "tasks": ["3.1", "3.2", "3.3"],
      "depends_on": ["1.1", "2.1"]
    },
    {
      "wave": 4,
      "name": "守卫与验证",
      "tasks": ["4.1", "4.2", "4.3", "4.4"],
      "depends_on": ["1.2", "1.3", "2.2", "2.3", "3.1", "3.2", "3.3"]
    },
    {
      "wave": 5,
      "name": "浏览器实测与公式预设核查",
      "tasks": ["5.1", "5.2", "5.3"],
      "depends_on": ["4.1", "4.2", "4.3", "4.4"]
    }
  ]
}
```

## Tasks

## 1. 归一映射表 + classify 修正（wave 1）

- [x] 1.1 新建 `composables/n2TaxLabelMap.ts`（归一映射单一真源）
  - 导出 `N2_TAX_LABEL_MAP`（13 条，key=规范名，含 disclosureLabel/classifyKey/sortOrder）
  - 导出 `normalizeTaxLabel(raw: string): string`（变体名→规范名，覆盖 memory 记的归一规则 + 源模板差异）
  - 导出 `DISCLOSURE_LABEL_BY_CLASSIFY_KEY: Record<string, string>`（classifyKey→源模板 label，供 prefill→disclosure 映射）
  - 导出 `N2_FIXED_TAX_LABELS: string[]`（源模板 R8~R20 逐字 label 数组，排序同源模板行序）
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 1.2 修正 `_n2_taxes_payable.py::_classify_tax_type`
  - 增值税 `"增值税" in name` → 返回 `"vat"`（不再返回 `"urban"`）
  - 新增：代扣代缴外国企业所得税 → `"wh-foreign-cit"`（在「企业所得税」之前判断）
  - 新增：代扣代缴个人所得税 → `"wh-iit"`（在「个人所得税」之前判断）
  - 新增：矿产资源补偿费 → `"mineral"`（在「资源税」之前判断，因含「资源」子串）
  - 新增：资源税 → `"resource"`
  - 保证判断顺序无子串误命中
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 1.3 修正 `_build_adjudication_prefill` 输出键集覆盖 13 种
  - 输出键 = `N2-1-{classifyKey}-audited` / `N2-1-{classifyKey}-opening`
  - 已有 `urban` 键值（历史含混增值税）的兼容：新数据分拆后旧键值自然被新 render 覆盖；不做 migration
  - 跑真实项目验证输出键 ≥ 实际存在的税种数
  - _Requirements: 1.4, 1.5_

## 2. 披露行骨架 + 附注模板扩行（wave 2）

- [x] 2.1 `useN2DisclosureTables.ts` 行骨架扩充
  - `N2_LISTED_TAX_ITEMS` = 源模板 13 行 label（从 `N2_FIXED_TAX_LABELS` 引用）
  - `N2_SOE_TAX_ITEMS` = 源模板 13 行 label（同上，两版行集完全一致）
  - `n2NoteSectionMap.ts` 的 `N2ListedTaxRow` / `N2SoeTaxRow` 接口不变
  - 勾稽函数 `runN2ListedChecks` / `runN2SoeChecks` 适配 13 行（逻辑不变，只是行数多了）
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2.2 附注模板幂等脚本 `fix_note_n2_tax_structure.py`
  - §五、41 rows 扩充到 13 种 + 合计（label 逐字源模板，`row_type: data`）
  - §八、41 rows 扩充到 13 种 + 合计
  - `--dry-run` / `--check` / `--apply`
  - `_aligned_by` 更新
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2.3 后端测试 `test_note_n2_tax_structure.py`
  - 断言两版 rows 各 13 + 合计 = 14 行
  - label 逐字比对 `N2_FIXED_TAX_LABELS`
  - `--check` exit 0
  - _Requirements: 3.1, 3.2_

## 3. 审定表→披露表数据带入（wave 3）

- [x] 3.1 `useN2DisclosureTables` 新增 `prefillFromAdjudication` 纯函数
  - 入参：`adjRows: N2Adj14Row[]`、`detailRows?: N2Detail16Row[]`（国企版需要）、`variant`
  - 归一：`normalizeTaxLabel(row.taxType)` → 匹配 13 固定行
  - 上市版：`end = adjRow.endAudited`、`prior = adjRow.beginAudited`
  - 国企版：`opening = detailRow.audBegin`、`payable = detailRow.audPayable`、`paid = detailRow.audPaid`、`end = computeN2SoeEnd()`
  - 仅填 null 格子（手工优先）
  - 同一规范名多行累加（如多种增值税子科目合并到「增值税」行）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 3.2 `useN2DisclosureTables.restore()` 集成带入逻辑
  - 无持久化数据时（首次渲染）调用 `prefillFromAdjudication`
  - 有持久化数据时不调用（保持现有行为）
  - 读 `allResponses` 的 `N2-1-adjudication-rows` 和 `N2-2-detail-rows` 作为入参
  - _Requirements: 4.1, 4.5_

- [x] 3.3 两个披露 Tab 组件（Listed/Soe）适配
  - `restore()` 调用时机不变（onMounted + adjudicated refresh）
  - 无需改模板/script 结构（restore 内部已扩展）
  - 确认 `emitNoteUpdated` 不被误触（prefill 是静默填入，不触发 autoSync）
  - _Requirements: 4.1_

## 4. 守卫与验证（wave 4）

- [x] 4.1 新建 `__tests__/n2TaxLabelMap.spec.ts`
  - `N2_FIXED_TAX_LABELS` 逐字比对源模板（测试内写死 13 条字面量）
  - `normalizeTaxLabel` 覆盖所有变体名→规范名
  - `DISCLOSURE_LABEL_BY_CLASSIFY_KEY` 覆盖 13 个 classifyKey
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 4.2 新建 `test_n2_classify_tax_type.py`（后端）
  - 13 种源模板科目名 → 逐一断言 `_classify_tax_type` 输出对应的独立 key
  - 增值税 → `vat`（非 `urban`）回归断言
  - 判断顺序测试：「代扣代缴外国企业所得税」先于「企业所得税」
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 4.3 新建 `__tests__/n2DisclosurePrefill.spec.ts`
  - 喂 13 种审定行 → 断言 13 固定行全有值
  - 喂空数组 → 断言 13 行全 null（不塌 0）
  - 手工优先：已有值的格子不被覆盖
  - 国企版测试 computeN2SoeEnd 行内公式
  - _Requirements: 4.1~4.6_

- [x] 4.4 全量回归
  - `composables/__tests__` + `n2` 全量 vitest
  - 后端 `backend/tests/` N2 相关全量 pytest
  - 改动文件 `get_diagnostics` 零诊断 + Vite transform 200
  - _Requirements: all_

## 5. 浏览器实测与公式预设核查（wave 5）

- [x] 5.1 浏览器实测端到端链路
  - ✅ 国企 / 上市披露表 13 行 + 合计渲染，逐字对齐源模板 R8~R20
  - ✅ N2-1 审定表四表预填生效（项目 `14fb8c10`：增值税 20,583.99 / 城建税 1,440.88 /
        教育费附加 1,029.20 / 代扣代缴个人所得税 55.78 / 印花税 期初 18.80）
  - ✅ 披露表从四表种子带入（上市合计 **23,109.85 == tb_balance 科目 2221 期末**，逐分勾稽）
  - ✅ 点「同步到附注」→ `八、41` 落库 16 行（13 固定 + 增行「其他」「印花税」+ 合计），
        `_sub_table_columns` 5 列与附注模板逐字一致，`last_sync_at` 已写入
  - ✅ 上市版推送被平台 `detect_standard_conflict` 正确拦下（国企项目 → 409 STANDARD_MISMATCH）
  - 🔴 见 wave 6：实测过程挖出**四层**串联阻塞，全部修复后链路才通
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 5.2 公式预设核查
  - 比对 `prefill_formula_mapping.json` N2 块与 Python 实现：TB('2221','期末余额') ↔ `_fetch_tb_data` 的 closing_balance
  - 如不一致则更新 JSON
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 5.3 数据复原与收尾
  - 测试数据全部复原
  - 更新 tasks.md / INDEX.md / memory.md
  - CI job 注册（如需要）
  - _Requirements: all_

## 6. 复盘补漏（wave 6，2026-08-01 复盘新增）

- [x] 6.1 🔴 P0 修 prefill 契约不匹配（四表→审定表链路唯一阻塞点）
  - **实证**：后端 `_build_adjudication_prefill` 返回 `dict[str,float]`（`{'N2-1-vat-audited': 123.45, ...}`），
    前端 `N2TabAdjudication.vue` 是 `Array.isArray(pf) ? pf : null` → **dict 传入恒得 null**
    → `useN2Adjudication14` 走 `DEFAULT_TAX_TYPES` 空行 → 审定表永远空 → 披露表 prefill 也带不出数据
  - **四层验证为何全绿**：`props.htmlData` 是 `any` 故 TS 不报错；vitest 从未喂真实 render 输出；
    浏览器实测的项目本就无 `N2-1-adjudication-rows`，空行是「预期结果」
  - 修法（倾向）：后端改返回**数组** `[{tax_type, begin_unadj, end_unadj}, ...]`
    （按 classifyKey 聚合后经 `DISCLOSURE_LABEL_BY_CLASSIFY_KEY` 转 label），
    因数组形态才带得动 taxType；dict 的 key 里嵌 label 需前端反解字符串，脆弱
  - 守卫：新增契约测试，从后端函数真实返回值断言前端 `Array.isArray` 判定为 true
  - _Requirements: 1.4, 1.5, 4.1_

- [x] 6.2 🟡 P1 双归一函数交叉守卫
  - `normalizeTaxLabel`（披露方向，输出源模板全称）与 `_normalizeTaxNameForN4`（N4 方向，输出简称）
    互为逆映射但**无守卫**：城建税↔城市维护建设税 / 车船税↔车船牌照税
  - **已知有意分叉**：`地方教育附加` 披露侧合并进「教育费附加」，N4 侧是独立税种
    （`TAX_CALC_TABLE_MAP` 有该键）→ 须显式登记为例外 + 写明源模板依据
  - 守卫：断言两函数对同一输入的输出经 `N2_TAX_LABEL_MAP` 能映射到同一披露行
  - _Requirements: 6.2, 6.3_

- [x] 6.3 补完 5.1 剩余 4 条实测（依赖 6.1 修完）
  - 实测项目 `14fb8c10-9462-45f6-8f56-d023f5b6df13`（active dataset 35 行 2221% 数据、year 2025）
  - **实测挖出四层串联阻塞，逐层修复后链路才通**：
    1. **契约层**：后端返回 `dict` / 前端要 `array` → `Array.isArray` 恒 false（Task 6.1）
    2. **取数层**：`get_active_filter(ctx.project_id)` 单参调用，真实签名是
       **async** `(db, table, project_id, year)` → `TypeError` 被 `except Exception` 吞成
       warning → TB 取数与预填恒空，**无任何报错线索**（与 memory 记的 N5 同款坑）
    3. **归类层**：`简易计税` 不含「增值税」子串 → 落 `other`，增值税少算 74%
       （15,233.31 / 20,583.99）；源模板附注提示明确要求它归增值税
    4. **传参层**：宿主 `GtN2TaxesPayable.vue` 漏传 `:html-data` 给审定表与两个披露 Tab
       → `props.htmlData` 恒 undefined（同「漏传 projectId」范式）
    另修：披露表原只读 `checklist_responses` 的审定行，而审定表种子值在用户保存前
    并不落库 → 新增 `renderPrefill` 兜底（审定数 == 未审数，无调整时成立）
  - 守卫：`test_n2_prefill_contract.py`（15）+ `n2HostPropWiring.spec.ts`（7）
  - **测试数据说明**：实测在真实项目上产生了披露表持久化行 + 附注 `八、41` 的
    `sub_table_data`，内容全部源自该项目自身 tb_balance，是用户正常操作的正确产物，
    未清理（清掉反而让附注变空表）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

## Notes

- **源模板唯一权威** = `backend/wp_templates/N/N2 应交税费.xlsx` 的两个附注 sheet + N2-1 + N2-2。
- **🟢 P2 已决策不做（记录代价）**：N2 未接入 `resolve_report_line_accounts` 四表共享件（F1/K1/K2/D1 已接）。
  判断依据：N2 只有 2221 一棵树、无跨科目备抵、`BS-049 = TB('2221','期末余额')` 四准则一致 → 硬编码
  `LIKE '2221%'` 充分。**代价**：`report_config` 的 `project:{id}` 级自定义映射对 N2 无效，
  若客户把应交税费编在非 2221 科目，N2 取不到数而 F1/K1 能取到。
- **🟢 P2 技术债**：`N2TabVatCalc.vue` 1776 行（N2 最大 Tab，四段重写产物），
  已达「Top-5 巨型 Vue」量级，可拆四个 section 子组件。
- **不改 `useN2VatEngine.ts`**（`n2-vat-calc-source-alignment` spec 约束仍有效）。
- **`_normalizeTaxNameForN4`**（`useN2CrossSheet.ts`）是 N4 联动方向的归一函数，本 spec 的 `normalizeTaxLabel` 是披露方向的，两者**输入输出域不同**（前者输出规范名供 TAX_CALC_TABLE_MAP 匹配，后者输出源模板 label 供披露表行匹配）。但底层归一逻辑须**双向一致**——同一税种在两个函数里归一结果必须映射到同一行。
- **「个人所得税」vs「代扣代缴个人所得税」**：源模板写的是「代扣代缴个人所得税」，N2-2 明细表固定行写的是「个人所得税」。归一映射表须决定是否合并。根据源模板权威原则，披露 label 用**源模板原文**「代扣代缴个人所得税」，但 `normalizeTaxLabel('个人所得税')` = `'代扣代缴个人所得税'`（合并到同一披露行）。
- **「教育费附加」vs「地方教育附加」**：源模板只有「教育费附加」一行，N2-2 明细表是分两行的。归一：两者都映射到「教育费附加」披露行（金额累加）。源模板注释「（小税（费）种可合并反映）」支持此处理。
- **`印花税`**：源模板 13 行里**没有**印花税固定行，但 N2-2 明细表有。归一映射：不为印花税建固定行 → 若项目有印花税余额且用户需要披露，走动态增行（R21~R22 预留行）。这与源模板口径一致。
- **兼容性**：已有 `N2-disclosure-listed-taxes` / `N2-disclosure-soe-taxes` 的持久化数据若 label 是旧的 5/10 种行集，`restore()` 仍能正确恢复（数组顺序保留，不因骨架扩充而丢数据）。
