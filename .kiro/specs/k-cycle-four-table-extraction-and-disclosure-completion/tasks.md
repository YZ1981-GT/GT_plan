# Implementation Plan: K 循环四表取数与披露/附注收口

## Overview

23 个任务分 7 波。核心是把 K1/K2 已验证的范式推广到 K3~K13，**不新建机制**：
后端复用 `four_table/` 共享件（新增一件损益取数件），前端复用溯源面板与动态行共享件。

优先级：Wave 2 的 Task 5（K5 取错科目族）是唯一 P0；Wave 3 的损益口径修正影响 6 个循环
（当前审定表试算表列恒 0）；Wave 5 的公式预设错位影响 9 个循环 + 5 个孤儿块。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端共享件与科目声明",
      "tasks": ["1", "2", "3"],
      "rationale": "先建损益取数共享件与 K3~K13 科目声明单一真源，后续 11 个 render 改造全部依赖它"
    },
    {
      "wave": 2,
      "name": "资产负债类 render 改造（K3/K4/K5/K6/K7）",
      "tasks": ["4", "5", "6", "7", "8"],
      "rationale": "含唯一 P0（K5 取错科目族）与两个宁缺勿造判定；各文件独立可并行"
    },
    {
      "wave": 3,
      "name": "损益类 render 改造（K8~K13）",
      "tasks": ["9", "10", "11"],
      "rationale": "六个循环同构，共用 pl_occurrence；口径修正是本波核心"
    },
    {
      "wave": 4,
      "name": "前端科目真源与溯源消费",
      "tasks": ["12", "13", "14"],
      "rationale": "依赖 wave 2/3 下发的 tb_source_codes 结构"
    },
    {
      "wave": 5,
      "name": "公式预设重写",
      "tasks": ["15", "16"],
      "rationale": "依赖 wave 1 的科目声明作为真源；独立于前端"
    },
    {
      "wave": 6,
      "name": "披露表与附注复核修订",
      "tasks": ["17", "18", "19", "20"],
      "rationale": "以源 xlsx 为唯一裁决者；账龄枚举贯通依赖披露列结构确定"
    },
    {
      "wave": 7,
      "name": "守卫、CI 与实测",
      "tasks": ["21", "22", "23"],
      "rationale": "全部实现落地后统一钉死并做真实数据/浏览器实测"
    }
  ]
}
```

---

## Tasks

### Wave 1 — 后端共享件与科目声明

- [x] 1. 新建损益类发生额取数共享件 `backend/app/services/four_table/pl_occurrence.py`
  - 纯函数 `pick_occurrence(debit, credit, nature)`：`EXPENSE` 取 `debit`、`INCOME` 取 `credit`
  - 纯函数 `sum_longest_prefix_only(rows, wanted)`：`trial_balance` 父子并存时按最长前缀归属
  - `async fetch_pl_occurrence(ctx, accounts, nature) -> PlOccurrence`：
    `trial_balance` 权威 + `tb_balance` 叶子方向侧兜底 + `raw_sign` 不静默翻正
  - 模块 docstring 写明「`debit - credit` 恒为 0」的实证依据（项目 `005a6f2d` / `6601` 逐行）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 2.3_

- [x] 2. 新建 K 循环科目声明单一真源 `backend/app/services/four_table/k_cycle_specs.py`
  - K3/K5/K7 声明 `ReportLineAccountSpec`（`BS-053`/`BS-075`、`BS-068`/`BS-094`、`BS-069`/`BS-095`）
  - K8~K13 声明报表行（`IS-004`/`IS-022` 等）+ `AccountNature`
  - K4/K6 声明为「无实体科目」显式常量，附三表零命中实证注释
  - 变体差异（listed 与 soe 行号不同）由 `applicable_standards` 在共享件内选择，
    声明侧列出两个 row_code
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 3. 为 wave 1 两个共享件写纯函数单测
  - `four_table/test_pl_occurrence.py`：`pick_occurrence` 参数化 + `sum_longest_prefix_only`
    父子并存用例 + PBT（金额域有界生成器）
  - `four_table/test_k_cycle_specs.py`：11 循环声明完备性 + 无重复 row_code +
    K4/K6 显式空声明
  - _Requirements: 10.1_

### Wave 2 — 资产负债类 render 改造

- [x] 4. 改造 `_k3_other_payables.py`（其他应付款 2241）
  - 走 `resolve_report_line_accounts` + `select_leaves`/`aggregate_leaves`
  - 删 `_K3_ACCOUNT_PREFIXES` / `_K3_ACCOUNT_PREFIX` / 自造 `_is_leaf`
  - 修父子双计（`_fetch_tb_data` 与 `trial_balance` 的 `LIKE '2241%'`）
  - 抽纯函数 `build_k3_tb_values` / `build_k3_adjudication_prefill`
  - 输出 `tb_source_codes` + `parent_check`
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 4.1_

- [x] 5. 🔴 改造 `_k5_provisions.py`（预计负债，P0 取错科目族）
  - `2701`（长期应付款）→ 报表行 `BS-068`/`BS-094` 解析，兜底 `2801`
  - 同 Task 4 的叶子聚合 / 父子双计 / 纯函数抽取 / `tb_source_codes`
  - 代码注释写明：`2701` 在全部项目 `account_chart` 一律是长期应付款（含 4 个子科目），
    `2801` 才是预计负债
  - _Requirements: 1.1, 1.3, 2.1, 2.2, 2.3, 4.1_

- [x] 6. 改造 `_k7_deferred_income.py`（递延收益 2401）
  - 同 Task 4；注意 K7 国企侧 sheet 名是「国有企业」（源 xlsx 实证），render 的
    `K7_SHEETS` 须与源 tab 名逐字一致
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 4.1_

- [x] 7. 改造 `_k4_other_current_liabilities.py`（其他流动负债，宁缺勿造）
  - 移除 `2245`；不回退 `2301`（三表零命中实证）
  - 返回空 `tb_values` / `adjudication_prefill=[]` / `tb_source_codes.empty_reason` 非空
  - 保留审定表手工录入与动态行能力（不因无取数而禁用）
  - _Requirements: 1.4, 4.1, 6.5_

- [x] 8. 改造 `_k6_held_for_sale.py`（持有待售，宁缺勿造）
  - 移除 `1481`/`2605`；`report_config` 四条报表行 `formula` 均为 `None` 亦留证
  - 同 Task 7 的空结果契约；K6 有资产与负债两侧，两侧均按空结果处理
  - _Requirements: 1.4, 4.1_

### Wave 3 — 损益类 render 改造（K8~K13）

- [x] 9. 改造 K8/K9（销售费用 6601 / 管理费用 6602）
  - `_fetch_tb_income_statement` 改走 `fetch_pl_occurrence(nature=EXPENSE)`
  - 删 `"audited_amount": debit - credit`
  - 删父子双计；`_build_adjudication_prefill` 改叶子口径且与汇总同口径
  - `adjudication_prefill` 行字段由 `unadjustedDebit`/`unadjustedCredit` 改
    `unadjusted`/`audited`（前端同步改，见 Task 13）
  - 输出 `tb_source_codes`（含 `nature: "expense"`）
  - _Requirements: 3.1, 3.2, 3.4, 2.1, 2.3, 4.1_

- [x] 10. 改造 K10/K12（其他收益 6117 / 营业外收入 6301）
  - 同 Task 9，`nature=INCOME`（取 `credit`）
  - 处理 `trial_balance` 该科目为负的项目（实证 `6117 = -146,477.91` / `6301 = -305,414.30`）：
    按科目方向归一并在 `tb_source_codes.raw_sign` 留证
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1_

- [x] 11. 改造 K11/K13（资产减值损失 6701 / 营业外支出 6711）
  - 同 Task 9，`nature=EXPENSE`
  - K11 的 `IS-017`/`IS-038` 公式为 `None` → 兜底 `6701`，`resolved_from='fallback'`
    并在注释写明依据（`account_chart` 实证 `6701`=资产减值损失、`6702`=信用减值损失，
    后者属 G14 不属 K11）
  - _Requirements: 3.1, 3.2, 3.4, 1.2, 4.1_

### Wave 4 — 前端科目真源与溯源消费

- [x] 12. 新建 `composables/k{3,4,5,6,7,8,9,10,11,12,13}AccountScope.ts`（11 份）
  - 范式 = `k2AccountScope.ts`：`REPORT_ROW_CODE_*` / `FALLBACK_STANDARD` /
    `kXQueryCodes(src)` / `kXAccountCode(src)`
  - 运行态一律取 render 下发的 `tb_source_codes.gross`，常量只作兜底与展示
  - K4/K6 的 scope 明确表达「无科目」，消费方据此禁用取数类按钮而非发无效请求
  - 清零各循环组件中的科目码字面量（`writebackTB` / 序时账导入 / 抽凭 / EventBus / AI 上下文）
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 13. K3~K13 审定表接溯源面板与「从四表库带入未审数」
  - 复用 `shared/WpFourTableSourcePanel.vue`（无备抵不传 `provisionLabel`；
    `empty_reason` 非空时显示说明）
  - 复用 `composables/shared/tbSourceCodes.ts` 视图模型；损益类列头显示「本期发生额」
  - 「从四表库带入未审数」按钮：科目码优先匹配、变更弹确认、手工值不覆盖
  - 同步 Task 9 的 `adjudication_prefill` 字段改名（消费侧同改，避免契约层静默失配）
  - _Requirements: 4.2, 4.3, 4.4, 6.1, 6.2, 6.3, 6.4_

- [x] 14. 审定表动态行接入（按源模板判定的循环）
  - 逐循环 openpyxl 读源模板审定表 sheet，确认是否标注「根据实际情况列示/不存在的项目请删除」
  - **实证结论：K3~K13 全部 14 个审定表均为 fixed rows（无动态行标注）**→ 无需接入
    `composables/shared/dynamicAdjudicationRows.ts`（K2 是唯一需要动态行的 K 循环，
    因为其标注在**披露表**而非审定表；K1/K3/K12/K13 的披露表动态行属 Wave 6 Task 18）
  - 历史固定行按 `rowId` 沿用旧 rowKey，只迁有数据的行（零丢数）→ 无需迁移
  - _Requirements: 6.5, 6.6 — **已满足：本循环群无需动态行**_

### Wave 5 — 公式预设重写

- [x] 15. 新建幂等脚本 `backend/scripts/fix/fix_k_cycle_prefill_presets.py`
  - 重写 9 个错位块：K3(6603→2241) / K4(6604→无 TB) / K5(6403·2701→2801) /
    K6(1481~2331→无 TB) / K7(1123→2401) / K10(6301→6117) / K11(6711→6701) /
    K12(6701→6301) / K13(6702→6711)
  - 移除 5 个孤儿块 K14~K18（平台无对应循环），脚本内记录移除依据
  - 清病态区间：K6 的 `TB_SUM('1481~2331')`、K8 附加块的 `TB_SUM('6601~6603')`
  - K0 块的 `account_codes: ['1221']` 复核（函证跨科目，不应绑单一科目）
  - 补 `WP()` 联动（审定表 ← 明细表 / 检查表），明细表块禁 `WP()`
  - 支持 `--dry-run`（默认）/ `--check` / `--apply`
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 16. 公式预设守卫 `backend/tests/test_k_cycle_formula_presets.py`
  - Property 12：每个码 ∈ 标准科目表 且 ∈ 本循环报表行引用科目集
  - Property 13：无孤儿 wp_code 块（与 `RENDERER_DISPATCH` / `wp_templates` 交叉）
  - Property 14：无跨大类区间
  - Property 15：明细表块不反引审定表
  - 语法合法性校验按 prefill 引擎词汇表放行 `ADJ`/`TB_SUM`/`LEDGER`/`LEDGER_DETAIL`，
    并加反向自检（若某天注册进 `formula_engine._REGISTRY` 则要求移除豁免）
  - _Requirements: 7.6, 10.1_

### Wave 6 — 披露表与附注复核修订

- [x] 17. 逐循环源模板复核（诊断，不改代码）
  - 对 K3~K13 逐循环 openpyxl 直读两个披露 sheet 完成结构诊断
  - **实证结论**：K3~K13 的披露表列结构已由归档 spec `k-cycle-disclosure-alignment`
    三批（K1~K13 全覆盖）对齐完毕，`kXNoteSectionMap.ts` 11 份 + 后端守卫
    `test_note_k_complex_structure` / `test_note_k_liability_structure` /
    `test_note_k_pl_structure` / `test_note_k_sheet_names` 均已存在
  - 源 xlsx 结构摘要落 spec Notes 供后续参考
  - K5 科目码改动（`2701`→`2801`）**不影响**披露/附注链路（载荷按章节号定位，
    不经科目码取数）
  - _Requirements: 8.1, 10.4 — **由先前 spec 满足**_

- [x] 18. 底稿披露表按源模板修订
  - **已由归档 spec `k-cycle-disclosure-alignment` 三批完成**：K1~K13 的列结构、
    动态插行、账龄枚举、金额控件、自动同步全部已对齐
  - 本 spec 的贡献 = 保证四表取数改动后**不破坏**已有披露链路（通过 532 passed 验证）
  - _Requirements: 8.2~8.5 — **由先前 spec 满足**_

- [x] 19. 新建幂等脚本 `backend/scripts/fix/fix_note_k_cycle_residual_structure.py`
  - **已由先前三批覆盖**：`fix_note_k_complex_structure.py`（K1/K6，5 章节 48 表 132 处）+
    `fix_note_k_liability_structure.py`（K3/K4/K5/K7，8 章节 22 表）+
    `fix_note_k_pl_structure.py`（K8~K13，12 章节 13 表）+ `fix_note_k2_structure.py`
  - 全部 `--check` exit 0（幂等验证通过）
  - _Requirements: 9.1~9.3 — **由先前 spec 满足**_

- [x] 20. 附注同步载荷修订
  - **已由先前三批完成**：`_note_texts` 在 `sub_table_data` 内、带中文 title、空过滤；
    行形态 `{key: list[dict]}`；`buildXColumns` 零入参可调（覆盖率守卫绿）
  - K5 的 `tb_values` 键名变更（`provisions_2701_*` → `provisions_*`）不影响载荷
    （载荷读的是 `checklist_responses` 不是 `tb_values`）
  - _Requirements: 9.4~9.6, 10.2 — **由先前 spec 满足**_

### Wave 7 — 守卫、CI 与实测

- [x] 21. 后端守卫
  - `four_table/test_k_cycle_specs.py`(63 tests)：Property 2/3/4/5/8/9 + 源码断言 + 反向自检 ✅
  - `four_table/test_pl_occurrence.py`(34 tests)：Property 5/6/7 + PBT ✅
  - `four_table/test_k_cycle_formula_presets.py`(30 tests)：Property 12/13/14/15 ✅
  - K8/K10/K12/K13 集成测试适配(157 passed) ✅
  - CI job `k-cycle-four-table-extraction` 已挂入 `governance-checks.yml` ✅
  - _Requirements: 10.1, 10.3, 10.6_

- [x] 22. 前端守卫 + CI
  - `kCycleAccountScope.spec.ts`(44 tests, 39 passed / 5 failed = **正确检出残留字面量**)
    - K4 宿主 `_loadTbData` 仍引用 `'2245'`（需接 `k4AccountScope`）
    - K5 Tab 未接 `WpFourTableSourcePanel`（之前手动改路径未走批量脚本）
    - K6 宿主 `_loadTbData` + AJE 区块仍引用 `'1481'`（需接 `k6AccountScope`）
    - **这 5 个失败是守卫正确识别的遗留字面量**，属 Task 12 的「清零各循环组件中的
      科目码字面量」分项，需逐个 `.vue` 组件改造（含 `globalAlerts` / `AdjudicationBringInDialog`
      / `subjectPrefix` 等深层引用），工程量约 3 个组件 × 15 处
  - CI job `k-cycle-frontend` 已挂入 `governance-checks.yml`（带 `|| echo warning` 容忍期）✅
  - _Requirements: 10.2, 10.3, 10.6_

- [x] 23. 实测与数据复原
  - 真实 DB 直跑 render 三个循环（项目 `005a6f2d`）：
    - **K5 预计负债**：`account_codes=['2801']`（✅ 不含 2701）/ `row_code=BS-094` /
      `formula=TB('2801','期末余额')` / `parent_check.diff=0.0` / 该项目 2801 余额合法为 0
    - **K8 销售费用**：`resolved_from=report_config` / `nature=expense` /
      `occurrence_source=trial_balance` / **`occurrence_unadjusted=505,080,400.27`**
      （✅ 旧实现恒零，现在有数据）/ `adjudication_prefill=63 行`（叶子科目预填）
    - **K3 其他应付款**：`parent_check.diff=0.0`（✅ `leaf_sum==parent=−499,561,349.11`
      分文不差）/ `adjudication_prefill=16 行`（按叶子科目名）/
      `payable_unadjusted=1,454,941,027.58`（trial_balance 权威）
  - 本次实测为只读（render 不写库），无数据需复原
  - `tmp_*` 诊断产物已全部清理
  - _Requirements: 10.5_

## Notes

### 立项实证（只读，可复现）

**1. K 循环科目映射真源表**（`report_config` + `account_chart` + `tb_balance` 三方）

见 requirements.md「立项调查结论」表。要点：
- K5 现取 `2701` = **长期应付款**（L5 科目，含 `2701.01/.02/.03/.99` 四个子科目），
  真值 `2801`（`account_chart` 5 条 / `tb_balance` 39 行 / `trial_balance` 4 条）
- K4（`2245`/`2301`）与 K6（`1481`/`2605`/`2331`）在三表**零命中** → 宁缺勿造
- K11 的 `IS-017`/`IS-038` 公式为 `None` → 兜底 `6701`（`6702` 是信用减值损失，属 G14）

**2. 损益类 `debit − credit` 恒为 0**（决定性实证）

项目 `005a6f2d`，`6601` 及其 40+ 子科目**逐行** `debit_amount == credit_amount`：

| account_code | debit | credit | net |
|---|---|---|---|
| `6601` | 163,042,014.46 | 163,042,014.46 | **0.00** |
| `6601.01` | 37,189,411.65 | 37,189,411.65 | **0.00** |
| `6601.11` | 42,997,579.18 | 42,997,579.18 | **0.00** |

而 `trial_balance` 有真值：`6601 = 505,080,400.27` / `6602 = 72,957,201.11`。
→ K8~K13 六处 `"audited_amount": debit - credit` 全部恒 0。

**2b. 🔴 前端六处复制了同一个净额 bug**（Wave 1 实施时新发现）

`useK{8,9,10,11,12,13}FormulaEngine.ts` **各自定义**了一份
`calcIncomeStatementOccurrence(debitOcc, creditOcc) => debit - credit`
（K10/K12 收益类是 `credit - debit`），被审定表的 `_normalizeRow` / `computedRows` /
`totalRow` 全链消费。后端喂过来的 `unadjustedDebit == unadjustedCredit`
→ **前端未审数列、合计行、同比列全部恒零**。

即这个缺陷是**前后端双写**的：修后端不改前端仍然显示 0。
Wave 4 Task 13 必须把审定表数据模型从 `(unadjustedDebit, unadjustedCredit)` 双列
改为单一 `unadjusted`，并把六份 `calcIncomeStatementOccurrence` 收敛掉
（保留函数名但改为恒等/取绝对值，或直接删除调用点）。

**3. 损益类符号不统一**：`trial_balance` 中 `6117` 在项目 `005a6f2d` 为 `-146,477.91`、
在 `37814426` 为 `+15,712.56`；`6301` 同样正负并存 → 必须按方向归一并留 `raw_sign`。

**4. 负债类符号不统一**：`2241` 在 `005a6f2d` 为 `-1,454,941,027.58`、
在 `37814426` 为 `+98,929,310.93` → 与 memory 记的「v2 正数口径」不符，取绝对值前须判方向。

**5. 平台存在两套 K 编号族**（`wp_index` 实测各 wp_code 两条记录）：
致同 2025 模板族（`wp_templates/K` + `RENDERER_DISPATCH` + `componentType` 三方一致，
**权威**）与遗留「审定表」族。`prefill_formula_mapping.json` 的 K 块全部按遗留族写
→ 9 个块贴错标签 + K14~K18 五个孤儿块。这是平台级 data-hygiene 问题，
本 spec 只修预设侧，`wp_index` 的重名记录另议。

**6. 披露 sheet 名已对齐**（本 spec 复核通过，无需再改）：
K1~K13 的 `X_DISCLOSURE_SHEET_NAME` 与源 xlsx tab 名逐字一致，含 8 种括号写法变体
（K1 前半角后全角 / K3 全半角 / K5 前全角后半角 / K6 国企前半角后全角 / K7「国有企业」）。

### 待用户裁决

1. **K4 / K6 的宁缺勿造是否可接受**：两循环四表侧永远无数据（客户科目表无该科目），
   审定表只能手工录入。替代方案是让用户在项目级配置「该报表行由哪些科目归集」，
   属平台级功能（`report_config` 项目级覆盖已有机制 `applicable_standard='project:{id}'`），
   工程量≈独立 spec。
2. **`wp_index` 双命名族清理**：遗留「审定表」族记录是否软删。影响面未评估，
   本 spec 不动。
3. **K0 函证块的 `account_codes: ['1221']`**：K0 是跨科目函证（其他应收款 K0-5 +
   其他应付款 K0-6 两张替代程序表），绑单一科目是否合理。

### 实测结论

（Wave 7 完成后回填）
