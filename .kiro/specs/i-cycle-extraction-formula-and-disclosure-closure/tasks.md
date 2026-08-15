# Implementation Plan: I 循环取数、公式预设与披露附注收口

## Overview

24 个任务 / 7 波，收口 I1~I6 六循环的「四表入库 → 底稿取数 → 披露表 → 附注模块」全链。

**不重建既有骨架** —— `four_table/i_cycle_{accounts,extraction,prefill}.py` 与 6 份
`iXNoteSectionMap.ts` 已在位且机制正确（真实库 8 项目 `parent_check` 全部 `diff=0.0`）。
本 spec 只修实证查出的缺陷 + 补缺口。

**核心工作量分布**：Wave 2（row_code 双真源收敛，已完成 A/B 对照证明实质差异 0 处）
体量最小但风险最高，必须先有 Wave 1 的守卫打红；Wave 4/5（附注列元数据 + 披露结构 +
动态插行）是主要工作量；Wave 7 的变异检验与真实库验收是交付闸门。

**先做什么** —— Task 1（row_code 守卫先打红，6/6 失败）。它同时是 Wave 2 的验收判据。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（守卫必须先对当前状态打红）", "tasks": [1, 2, 3] },
    { "wave": 2, "name": "取数层收敛（row_code + 错基线改写 + I5 三态）", "tasks": [4, "4b", 5, 6] },
    { "wave": 3, "name": "公式预设纠错与补齐", "tasks": [7, 8, 9] },
    { "wave": 4, "name": "附注模板列元数据与表名", "tasks": [10, 11] },
    { "wave": 5, "name": "披露表结构与动态插行", "tasks": [12, 13, 14, 15] },
    { "wave": 6, "name": "前端消费与溯源接线", "tasks": [16, 17, 18] },
    { "wave": 7, "name": "守卫收口、CI、变异与验收", "tasks": [19, 20, 21, 22, 23, 24] }
  ]
}
```

Wave 1 是全部后续的前提（先打红才能区分「守卫有效」与「空转」）。Wave 2 是 Wave 6 的前提
（取数错则溯源面板显示的一切不可信）。Wave 3 与 Wave 4/5 无文件重叠，可并行。

---

## Wave 1 — 判据先行

- [x] 1. 新建 row_code 对账守卫（先打红 11/12）
  - 新建 `backend/tests/four_table/test_i_cycle_row_code_evidence.py`
  - **类 A（应全绿）**：连库自行查 `report_config` 得 `(row_code, applicable_standard) → (row_name, formula)` 全表；断言 `BS-032/033/034/035/037` + `IS-006` 的 row_name 分别为「无形资产/开发支出/商誉/长期待摊费用/其他非流动资产/研发费用」；断言这 6 个码在四个 `applicable_standard` 下 row_name 与 formula 均相同
  - **类 B（应全红）**：按 **12 个 `(循环, 准则)` 二元组**逐条断言 `resolve_row_code(wp, [f'{ent}_standalone'])` 的 row_name 命中 `I_CYCLE_EXPECTED_NAMES`；失败消息写明「尚未收敛（Wave 2 Task 4）」+ 实际命中的 row_name
  - 🔴 **必须按二元组逐条断言、不能只按循环** —— 磁盘实证 listed 与 soe 各是一套**不同的**错值，只查 soe 会漏掉 listed 侧 5 处错（详见 Notes 实证表）
  - 反向自检：构造错行名替身，`row_name_matches` 必须返 False
  - 禁在模块顶层 import 生产模块（collection error 会让「全红」不可判读）
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 11.1, 11.2_

- [x] 2. 新建预设纠错守卫（先打红 2 处）
  - ✅ **已交付**：`backend/tests/test_i_cycle_formula_presets.py`（21776 B）
    八个判据点逐条实证齐备 —— openpyxl 直读源 workbook · 块 `sheet` ∈ tab 名集合 ·
    `审定表I1` 无 `-1` 这一源模板事实已登记 · **stale 检测**（错名重现即红）·
    `account_codes` ⊇ 公式引用码集 · 区间端点不算引用（`SUM_TB`/`TB_SUM` 先整体消费）·
    区间端点排除的反向自检 · 禁用码残留（1712/1717/1911）
  - 🔴 该文件在 Task 9 又扩了 Property 10~14，当前 **97 passed / 0 skipped**
  - 新建 `backend/tests/test_i_cycle_formula_presets.py`
  - **类 A**：openpyxl 直读 6 个源 workbook 得真实 tab 名集合（冻结为基线常量，含 I1 的 `审定表I1` 无 `-1` 这一事实）
  - **类 B**：断言每个 I 类预设块 `sheet` ∈ 该 workbook tab 名集合（`审定表I1-1` 应红）；断言 `account_codes` ⊇ 公式引用码集（I2 明细表块的 `6602` 应红）
  - 区间 `a~b` 端点不算引用码（`SUM_TB`/`TB_SUM` 先整体消费再抽单码）
  - 反向自检：区间端点确实被排除（构造 `TB_SUM('1601~1604')` 断言 `1604` 不算引用）
  - _Requirements: 3.1, 3.3, 3.4, 3.6, 11.1_

- [x] 3. 新建附注结构守卫（先打红 4 表 + 2 处泄漏）
  - ✅ **已交付并实测全绿（2026-08-12 复核）**：`backend/tests/test_note_i_cycle_structure.py`（22778 B）
    四条缺口逐条落在**既有文件内**（未另建同域守卫文件），实测 `370 passed`：
    ①`test_source_dynamic_mark_count`（12 参数化）+ `_SRC_DYNAMIC_MARK_COUNT` 逐格冻结基线
    ②`startswith("[") or startswith("［")` 泄漏检测 + `_TABLE_NAME_MAX_LEN=30`
    ③`_COLS0_TARGETS`（4 条元组）+ `test_cols0_target_has_columns` / `test_cols0_target_group_or_flat` 逐张点名
    ④`("I3","listed","商誉减值测试关键假设")` 已在 `_COLS0_TARGETS` 内 ⇒ 被 ③ 的两条参数化覆盖
    另有 `test_cols0_targets_cover_all_known_gaps` 做反向自检（4 处齐备 + 不与 `_VERIFIED_TABLES` 重叠）
  - 🔴 **动态插行标记数基线修正**（文件内注释标「2026-08-09 openpyxl 逐格实测冻结」+ 逐格坐标，
    比本 tasks.md 原写的更准）：I1 listed **3**(A18/A29/A40) · I1 soe **4**(A20/A33/A46/A59) ·
    I2 listed **2**(A15+A27) · I2 soe **1**(A13) · I3 **0/0** · I4 **0/0** ·
    **I5 listed 1(A18) / I5 soe 1(A17)**（原写「I3~I6 各 0」漏了 I5 两处真实可扩位）· I6 **0/0**
  - 🔴 **修掉整组 collection error**（修前 `1 error during collection` ⇒ 220 collected 但全组 `Interrupted`，
    拿不到任何基线）：`_load_fix()` 动态加载 `fix_note_i_cycle_structure.py` 时未注册 `sys.modules`，
    而该脚本内有 `@dataclass` → `dataclasses` 取 `sys.modules.get(cls.__module__).__dict__` 得 `None`
    → `AttributeError`。修法 = 顶部补 `import sys` + `exec_module` 前插 `sys.modules[spec.name] = mod`
    （平台已记铁律；未改被测脚本设计，也未用 `importorskip` 掩盖成假绿）
  - ⇒ 本任务改为**在既有文件内补这 4 条**（禁另建同域守卫文件），补完先确认它们对当前状态打红
  - 新建 `backend/tests/test_note_i_cycle_structure.py`
  - **类 A**：openpyxl 直读 12 张披露 sheet 的列头与行标签，冻结为源事实基线；断言动态标记数 = I1 上市 3 / I1 国企 4 / I2 上市 1 / I3~I6 各 0
  - **类 B**：断言 listed `五、26` 的 `无形资产情况`·`确认为无形资产的数据资源`、soe `八、27` 的 `确认为无形资产的数据资源`、listed `五、28` 的 `商誉减值测试关键假设` 四张表 `columns` 长度 > 0（应红）；断言无表名以 `[` 开头（listed `五、31` / soe `八、32` 应红）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.1, 7.2, 7.3, 11.1_

## Wave 2 — 取数层收敛

- [x] 4. `I_CYCLE_ROW_CODES` 收敛为实证正确值
  - 改 `backend/app/services/four_table/i_cycle_accounts.py`：**12 个取值**（6 循环 × 2 准则）
    改为 `BS-032/033/034/035/037` + `IS-006`，listed 与 soe 同码
  - 🔴 现状 listed 与 soe 是**两套不同的错值**，共 11 处错（仅 `I6.listed` 已正确）
  - 保留 `dict[str, dict[str, str]]` 结构（不塌成单值）；把现有行内注释
    「报表行编码：**按准则不同**（实证同一 row_code 跨准则 row_name 都可能不同）」
    改为「I 类实证四准则同码同名同公式；保留双键结构因平台其它循环（J/K/L）确实按准则不同」
  - 保留 `row_name_matches` 校验闸（转为防回退）
  - docstring 附 A/B 对照结论（8 项目 × 6 循环实质差异 0，仅 `resolved_from` 变化）
  - 跑 Task 1 守卫，类 B 12/12 应转绿
  - _Requirements: 1.1, 1.2, 1.6, 1.7_

- [x] 4b. 改写 `test_i_cycle_accounts.py` 的错基线（**先于 Task 4 落地前跑一次确认它当前是绿的**）
  - 🔴🔴 实证：`TestResolveRowCode` 的 12 个参数化用例**逐条断言旧错码**
    （`("I1", ["listed_standalone"], "BS-033")` … `("I6", ["soe_standalone"], "IS-024")`），
    `test_empty_standards_returns_listed` 亦断言 `BS-033`
    ⇒ **既有守卫正把 11 个错值当基线钉死**，这是错码长期存活的直接原因
  - 12 个期望值全部改为实证正确值（六循环两准则同码）；`test_empty_standards_returns_listed` 改 `BS-032`
  - 保留 `test_unknown_wp_code_returns_empty`（该行为不变）
  - 用**诚实改写**而非删除：在类 docstring 写明「2026-08-09 按 `report_config` 实证修正，
    旧期望值 11/12 为错码（listed 与 soe 各一套），修正依据见 Task 1 守卫的类 A 断言」
  - Task 1 守卫加 Property 42 交叉锁死：把任一期望值改回旧错码时 Property 1 必须打红
  - _Requirements: 1.8_

- [x] 5. 消除 `i_cycle_specs.py` 双真源
  - 先 grep 确认 `I_PL_CYCLES` / `I_PL_POSITIVE_SIDE` / `spec_of` / `I1_SPEC`~`I6_SPEC` /
    `I_CYCLE_SPECS` 的全部消费方（**含 `backend/tests/**` 与 `four_table/__init__.py`**）
  - 🔴 该文件的 row_code 其实**全部正确**（`BS-032/033/034/035/037`+`IS-006`），
    且 docstring 已逐条记载两次修正依据（I5 `BS-039`→`BS-037`、I6 `IS-007`→`IS-006`）
    ⇒ 删除前把这两段实证理由**迁进 `i_cycle_accounts` 的 docstring**，别连证据一起删
  - 🔴 该文件 docstring 顶部那段科目映射表**本身有 4 处错**
    （写 I2=`TB('1711')` 实为商誉、I3=`TB('1721')` 全库不存在、I1 备抵写 `IMP-011`
    实际是 `IMP-016`、I3 备抵写 `IMP-012` 实际是 `IMP-017`）⇒ 迁移时按 Notes 实证表改正，不照抄
  - `I6_SPEC` 的 `trust_report_config=False` 与「6604 在 1 个项目 client 侧叫勘探费用」
    这条实证**必须保留**（迁进 `I_CYCLE_SEGMENTS['I6']` 的行内注释）
  - 无消费方的直接删除；有消费方的先迁常量再删；同步清 `four_table/__init__.py` re-export
  - Task 1 守卫加 Property 4：`SemanticAccountSpec(row_code=...)` 形态的 I 类声明数必须为 0
    + 反向自检（删除前该断言必须打红）
  - _Requirements: 1.3_

- [x] 6. I5 三态与零回归验证
  - 确认 I5 `cost` 段 `fallback=()`（宁缺勿造），`found=False` 时 `standard`/`original` 均空列表
  - 新建 `backend/tests/four_table/test_i5_absent_account.py`：三态可分（无此科目 / 余额为 0 / 有数据）+ 反向自检（构造含 `1911` 或名为「其他非流动资产」的科目表替身，解析必须命中）
  - 新建 `backend/scripts/diagnose/diagnose_i_cycle_rowcode.py`（只读）：row_code ↔ `report_config` 对账 + A/B 金额对照复算，输出到 `.txt`（不 print 中文/emoji，一律 `write_text(encoding='utf-8')`）
  - 用该脚本对 8 项目 × 6 循环跑一次，断言实质差异 0 处、`resolved_from` 变化 34 处
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 1.4, 1.5_

## Wave 3 — 公式预设

- [x] 7. 核实既有预设脚本 + 重放落地（**不新建**）
  - ✅ **已交付（2026-08-09）**：在既有 `fix_i_cycle_prefill_presets.py` 内补齐 3 处修法
    + 2 处 `--check` 判据，`--apply` 落地，数据侧逐项实证
  - 🔴🔴 **`--check` rc=0 而数据侧仍是旧值 —— 根因是脚本只改公式实参、从不改块自己的
    `sheet` 字段**：它把错名 `审定表I1-1` 当 `_find_block` 的查找键，于是「块指向源模板
    不存在的 tab」这一真缺陷既没被改、也没被 `--check` 判出来
    ⇒ **`--check` 归零不能当「已落地」的证据，必须独立查数据**（本轮已下沉进 memory 铁律）
  - 落地三处：`sheet: 审定表I1-1 → 审定表I1`（改名做成**新旧两键都能找到块**的幂等形态，
    否则首次 apply 找不到旧键 = 改名永不执行、二次 apply 找不到新键 = 幂等断裂）
    · I2 明细块 `TB('6602') → TB('6604')` · `account_codes → ['1704','6604']`
  - 🔴 **推翻脚本里一条写错的注释** —— I2 明细块的 `TB('6602')` 原注释写「保留（用于与 I6
    勾稽），不改」，而 `6602` 是**管理费用**（归 K9）、研发费用真源是 `6604`；同一脚本在 I6
    两处都把 6602→6604 改了 ⇒ **同一勾稽的两端取了不同科目**，注释本身是错的
  - 🔴 **顺带消除一个双写者**：第 7 节旧逻辑写 `['1704','5301']`、下方新逻辑又改成
    `['1704','6604']` —— 顺序让最终值正确，但二次 apply 会输出两条相反的变更记录
    ⇒ 收敛为唯一写者（memory 已记的 `row_type` 多写者事故同族）
  - 验证：幂等六项 ALL PASS（`--check` rc=0 / 二次 apply rc=0 且输出「无需修改」/
    stderr 无 traceback / md5 逐字节不变 / round-trip 复现原文 / **数据侧独立查询三处实证**）
  - **禁**新建第二个同域幂等脚本（会造双写者）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 8. 披露 sheet 预设登记（12 张）
  - ✅ **已交付（2026-08-09）**：在既有脚本内新增 `DISCLOSURE_NO_PRESET_REGISTRY`（12 条，
    每条带实测格数与源模板依据）+ `DISCLOSURE_SHEETS`（**由登记表派生，不另写清单**）
    + `_DISCLOSURE_SHEET_COUNT=12` 独立锚点交叉锁死 + `check_registry_consistency()`
    三条自检（覆盖完备 / 无冗余 / 理由 ≥30 字且含实证标记）
  - 🔴🔴 **R4.2 的假设被实证推翻，本任务按「宁缺勿造」偏离 spec 落地**：
    openpyxl 逐格直读 6 份源 workbook 实测 —— 12 张披露 sheet 共 **663 格跨 sheet 引用、
    全部指向本 workbook 内的 `明细表IX-2`**，「从试算表取数」的格 **= 0**
    （另 87 格引用 `底稿目录` 取表头身份、417 格是 `SUM`/算术派生）。
    逐张分布：I1 上市 110 / I1 国企 108 / I2 各 54 / I3 上市 72·国企 63 /
    I4 各 30 / I5 上市 55·国企 33 / I6 各 27。实证见 `_wip_i_t8p3.txt`
  - ⇒ R4.2 原写「I1 三段期初/期末、I3 商誉原值与减值、I4 期初/本期摊销/期末必须给出
    `TB()` 公式」**照做会造成双真源**：预设从 `trial_balance` 取数、底稿披露 Tab 又从
    `明细表IX-2` 推送同一格，两条链在「明细表未编制」与「试算表已有余额」之间打架，
    而审计师看不出哪个在生效。平台既有范式是**披露表由底稿推送**
    （`iXNoteSectionMap.ts` + `useDisclosureAutoSync`），预设层不介入
  - 🔴 该判据**当场抓出我自己写的 3 条空话理由**（I3/I4/I6 国企侧各 26 字「结构同上市版」）
    → 已按各自实测数据补全（这正是「理由质量闸」要防的形态）
  - 验证：`--check` rc=0 · 幂等六项 ALL PASS · 守卫 **203 passed / 0 failed**
    （`test_i_cycle_formula_presets` + row_code_evidence + accounts + i5_absent）
  - 🔴 **未用 `PLACEHOLDER`** ⇒ 三处白名单（`preset_acnr_migration.PENDING_FUNCTION_ALLOWLIST`
    / `test_h_prefill_extension.VALID_FORMULA_TYPES` / 各 preset purity 守卫）**无需改动**
    —— 本任务的结论是「不建披露块」而非「建了但公式表达不出」
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 9. 预设守卫收口 + 防成环
  - ✅ **已交付（2026-08-09）**：`test_i_cycle_formula_presets.py` 由 71 passed + 1 skipped
    → **97 passed / 0 skipped**（在该文件内扩充，未新建同域守卫文件）
  - **移除一个已过期的逃逸阀** —— 改造前有 `_KNOWN_SHEET_LABEL_ISSUES` 把
    `("I1","审定表I1-1")` 列白名单并 `pytest.skip`，而 Task 7 已把该块 `sheet` 改成
    源模板真实 tab `审定表I1` ⇒ 它**放行的是一个不再存在的状态**，长期 `1 skipped`。
    换成 `_HISTORICAL_SHEET_LABEL_FIXES` 历史台账 + `test_no_stale_sheet_label_whitelist`
    stale 检测（错名一旦在数据里重现即打红，而不是被 skip）
  - Property 10 幂等（`--check` rc=0 / 二次 apply md5 不变 / **stderr 无 traceback** /
    输出「无需修改」/ round-trip 逐字节复现）· Property 11 PREV 实参同步（块 `sheet` 字段
    与公式实参双向）· Property 12 披露登记完备（覆盖 / 真实 tab / 条目数锚点 / 理由质量）·
    Property 13 禁硬编码客户码 · Property 14 明细表禁反引本循环审定表（由既有
    `test_no_self_referencing_cycles` 覆盖）
  - 🔴🔴 **变异检验挖出一个真守卫缺口，已补 Property 14 第二判据** ——
    把 I2 明细表 `TB('6604')` 回退成 `TB('6602')` 时**7 条既有断言一条都不红**：
    `6602 管理费用` 确实存在于 `standard_account_chart.json`（K9 的科目），
    故「科目存在性」判据（本文件第 2 组）与 `test_no_forbidden_code_residue`
    （只禁 1712/1717/1911）**双双放行** ⇒「用了别的循环的科目」这类错完全逃过检查。
    新增 `TestProperty14CrossCycleAccountOwnership`：判据 = 每块的 `formula` 抽出码
    ∪ `account_codes` 必须 ⊆ 本循环 `I_CYCLE_SEGMENTS` 各段 `fallback` 的一级码集合，
    唯一例外是 `_CROSS_CYCLE_TIE_OUTS` 显式登记的跨循环勾稽
    （实测全库仅 1 条：`I2/明细表I2-2` 的 `6604` 与 I6 研发费用勾稽），
    登记项配三向自检（归属真属那个 I 循环 / 理由 ≥20 字 / **stale 检测**）
    + 两条反向自检（区间端点 `SUM_TB('1401~1499')` 不算引用 / 判据确实能识别 6602）
  - **变异检验 7/7 全 RED**（`GREEN=0 / ANCHOR-MISS=0 / WRONG-TEST=0`，还原逐字节一致）：
    M1 stale 台账→`test_no_stale_sheet_label_whitelist` · M2 登记表 key 改名→
    `test_every_disclosure_sheet_has_disposition` · M3 注入非幂等写入→
    `test_second_apply_is_byte_identical` · M4 PREV 实参回退→
    `test_formula_sheet_args_are_real_tabs` · M5 理由改空话→
    `test_registry_reasons_have_evidence` · M6 研发费用回退 6602→
    `test_all_referenced_codes_belong_to_own_cycle` · M7 脚本不再写 6604→
    `test_second_apply_is_byte_identical`
  - 🔴 **变异脚本本身踩了三个坑，已写进 memory 铁律**（下轮做变异检验直接复用
    `_wip_i_t9mut.py` 的形态）：①**守卫里有会写盘的测试** —— `Property 10` 真跑
    `--apply`，会把数据侧变异**自动修好**，于是 M4/M6 打红的是 apply 类测试而非目标判据
    ⇒ 数据侧变异必须只跑**纯读判据子集**（`--deselect` 掉 apply 类）②`finally` 里的
    `assert md5 == before` 抛出后**后续变异不再执行且污染留在盘上**（本轮实测 4 处残留：
    `I6_MUT` 登记 key / `_mutation_marker` 写进 1 MB 数据文件 / 两处假阳性）
    ⇒ 还原改为「先写回 → 再核验 → 失败只记录不抛」，并在收尾统一报告 ③无效变异 ——
    只改 `doc` 不 append 到 `changes` 时 `--apply` 根本不写盘（脚本仅在 `changes`
    非空时落盘），变异等于没施加
  - 🔴 **残留扫描的判据要精确到「本循环块内」** —— 我第一版按全文 `TB('6602')` /
    `!= ["1704"]` 扫，得 4 处 DIRTY 里 **2 处是假阳性**（`6602` 在 K9 管理费用块里合法、
    `["1704"]` 在 I2 审定表等 4 个块里合法）⇒ 判据须按 `wp_code` 过滤到 I 类块再比
  - 验证：本 spec 四个守卫合跑 **220 passed / 0 failed**；`--check` rc=0
  - _Requirements: 3.5, 4.1, 4.3, 4.4_

## Wave 4 — 附注模板

- [x] 10. 核实既有附注结构脚本 + 数据侧重放（**不新建**）
  - 🔴 **实证：`backend/scripts/fix/fix_note_i_cycle_structure.py` 已存在**（27981 字符 / 893 行 / git tracked），
    `--check` **rc=0，12 章节全部「已对齐（幂等空操作）」**
  - 🔴 `'确认为无形资产的数据资源'` 命中 **6** 次、`'商誉减值测试关键假设'` 命中 **2** 次
    ⇒ Task 10 原计划的补 columns **该脚本已实现**
  - 🔴 **但我实测 DB 里那 4 张表仍 `cols=0`**（listed `五、26` 两张 + soe `八、27` 一张 + listed `五、28` 一张）
    —— 脚本对齐目标是**模板 JSON**，而 `cols=0` 是**既有项目 `disclosure_notes` 的生成时快照**，两者不是同一层
    （memory 已记「改模板 JSON 对既有项目一律不生效，只对新建项目/重新生成附注生效」）
  - 本任务改为四步：①`--check` 复跑确认 12 章节 0 欠账 ②比对模板 JSON 里那 4 张表是否确有 `columns`
    ③若模板已有而 DB 无 ⇒ **属既有项目快照问题，登记进 Notes 不在本 spec 修**（存量回填属 legacy 迁移域）
    ④若模板也无 ⇒ `--apply` 重放
  - 🔴 `'披露与合同取得成本'` 命中 **0** 次 ⇒ **2 处段落泄漏表名是真缺口**，在既有脚本内补
    （按源模板判定：I5 源 sheet 无该表 ⇒ 整段移入 `text_sections`，不造表）
  - **禁**新建第二个同域幂等脚本
  - ✅ **四步全部达成（2026-08-12 实证 `_wip_i_task10.py` / `_wip_i_task10b.py`，未新建脚本）**：
    - ① `--check` **rc=0，12 章节全部「已对齐（幂等空操作）」，0 项欠账**
    - ② 模板 JSON 里那 4 张目标表**全部已有 columns**：
      `I1/listed/无形资产情况` 13 列（项目 + 11 类 + 合计）·
      `I1/listed/确认为无形资产的数据资源` 5 列 · `I1/soe/同表` 5 列 ·
      `I3/listed/商誉减值测试关键假设` 4 列（资产组/业务 · 毛利率 · 增长率 · 折现率）；
      四张均 `cols[0].is_label=true` + `flat` 表态
    - ③ **模板 JSON 26 张表里 cols=0 为 0 张** ⇒ 模板侧零欠账。tasks.md 记的「DB 里那 4 张仍
      cols=0」是**既有项目 `disclosure_notes` 的生成时快照**，与模板 JSON 不是同一层
      （memory 已记「改模板 JSON 对既有项目不生效，只对新建/重新生成生效」）⇒
      **存量回填属 legacy 迁移域，按本任务 ③ 的约定登记而不在本 spec 修**
    - ④ **2 处段落泄漏表名已修**（tasks.md 记「`披露与合同取得成本` 命中 0 次」已过期，
      实测脚本内命中 **3 次**）。处置方式 = **正名 + 指引移入 guidance + 保留表**：
      · 泄漏名 `[披露与合同取得成本有关的资产相关的信息，…例如：`（90 字符）→ 正名 `合同取得成本`
      · 该 90 字符段落剥掉 `[` 与尾部「例如：」后进 `guidance`（79 字符，两版一致）
      · 列 `['项目','cat_1','合计']` —— **英文 key**（中文 label 作 key 会撞键），
        label 保留源占位 `[佣金支出]` 供审计师识别要替换什么
      · 实测 **该泄漏文本作 `table.name` 出现 0 处**（listed / soe 两版都是）
  - 🔴 **修正 tasks.md 的错误判断**：原文写「按源模板判定：I5 源 sheet 无该表 ⇒ 整段移入
    `text_sections`，不造表」。openpyxl 实测 I5 源模板的 `审定表I5-1` / `附注披露（上市公司）` /
    `附注披露（国有企业）` / `明细表I5-2` **都有「合同取得成本」内容**（明细表还写明
    「相关内容索引至 M12 合同取得成本及减值准备」）⇒ 它是**真表**，只是表名被 docx 指引段落污染。
    脚本选的「正名 + guidance」才是对的；若照 tasks.md 删表会丢掉真实披露项。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 11. 修 `_aligned_by` 跨 spec 假红 + 守卫收口
  - 🔴🔴 **实证 4 条假红**：`test_note_i_cycle_structure.py::test_aligned_by_marker` 在
    `[I1_listed]` / `[I1_soe]` / `[I3_listed]` / `[I6_listed]` 失败，
    期望 `i-cycle-four-table-extraction-and-disclosure-alignment`，
    实际 **`note-template-columns-and-legacy-snapshot-closure`**（C spec 补 columns 时正当覆盖）
  - 🔴 **根因 = 判据把「归属关系」当成了不变量**，而 `_aligned_by` 是**最后一个对齐者的签名**，
    会被后续 spec 正当改写（同 memory 已记的「A spec 补列打红 D spec 守卫」范式）
  - 修法：判据由「`== 本 spec 名`」改为「`∈ ALIGNED_BY_ALLOWED`」+ 逐条登记覆盖者与理由
    （`note-template-columns-and-legacy-snapshot-closure` = C spec 补 columns，正当）
    + **stale 检测**（登记项若已不再出现于任何章节即打红提醒移除）
    + 反向自检（`_aligned_by` 完全缺失或为未登记值时必须打红）
  - Task 3 守卫补：Property 16 源 xlsx ↔ 模板 headers ↔ 同步 columns 三向一致（去空白归一）、Property 17 flat 两处都加、Property 15 无段落泄漏
  - `headers` 禁含 HTML（`<br/>` 等）
  - 收尾：`test_note_i_cycle_structure.py` 必须 **112 passed / 0 failed**（当前 108 passed / 4 failed）
  - ✅ **已交付（2026-08-12 实证）**：
    - `_ALIGNED_BY_ALLOWED` 允许集（2 条登记：本 spec 签名 + C spec `note-template-columns-and-legacy-snapshot-closure`
      并写明「覆盖的是章节签名、缺口仍在，故两者不冲突」）
    - `test_aligned_by_marker` 判据 = `marker in _ALIGNED_BY_ALLOWED`（不再 `== ALIGNED_BY`）
    - `test_aligned_by_allowlist_no_stale_entries`（stale 检测）
      + `test_aligned_by_rejects_unregistered_value`（反向自检：未登记值 / 空值 / None 均须被拒）
    - Property 15/16/17 逐条核实到断言体：段落泄漏 `startswith("[")` + 全角 `［` + 表名长度上限 ✓ /
      三向一致（openpyxl 读源 + 模板 headers + 同步 columns，`_norm` 去空白归一）✓ / `flat` 与 `group` 表态 ✓
    - 🔴 **本轮补齐最后一条缺口 `headers` 禁含 HTML**（原 16 条判据核实中唯一 MISS）：
      新增 `_HTML_PATTERN` + `test_headers_and_labels_no_html`（12 章节 × headers/columns.label/columns.group）
      + `test_headers_present_and_nonempty`（反向自检 A：断言扫到 ≥26 张表且每张 headers 非空 list）
      + `test_html_pattern_actually_matches`（反向自检 B：5 个 HTML 样本必命中、7 个纯文本样本必不命中）
    - 🔴 **修 collection error**（原先让整组 pytest `Interrupted`、220 collected 但 1 error 即中断，拿不到任何基线）：
      `_load_fix()` 动态加载 `fix_note_i_cycle_structure.py` 时未注册 `sys.modules[spec.name]`，
      而该脚本内用 `@dataclass` ⇒ `dataclasses` 取 `sys.modules.get(cls.__module__).__dict__` 得 `None`
      → `AttributeError: 'NoneType' object has no attribute '__dict__'`。补 `import sys` + 注册后解除。
    - **变异检验 5/5 全 RED**（`_wip_i_mutate_be.py`，恢复后复跑 0 failed 无残留）：
      正则改命中纯中文 / 正则改永不命中 / 反向自检 A 扫空气 / HTML 判据跳过整表 / 列文案取值路径跳过。
      🔴 其中「HTML 判据跳过整表」首轮判 **GREEN（守卫缺陷）** —— 因数据本来干净，把
      `isinstance(headers, list)` 改成 `if False:` 后 offenders 仍为空、不打红 ⇒ 守卫无法自证扫过 headers。
      已改为**自证扫描量**（统计 `scanned_headers` / `scanned_cols` 并断言下限）后转 RED。
    - 实测 `test_note_i_cycle_structure.py` **164 passed / 0 failed**（远超原定 112，Task 3 判据补齐后总数增长）
  - _Requirements: 5.5, 5.6, 5.7_

## Wave 5 — 披露表与动态行

- [x] 12. I1 上市披露主表列集对齐源模板
  - 逐字核 `附注披露信息（上市公司）!B10:M10` 的 13 列（10 类别 + 数据资源 + 其他 + 合计）与现有 `i1NoteSectionMap.ts` 的 `movement` 表列定义
  - 若为动态列形态则改 `buildI1ListedColumns(categories)`，稳定 key `{slot}_{seq}`，**禁用中文 label 作 key**
  - 类别真源派生自 `i1_asset_categories.py`（该文件类别声明补 `source_ref` 指向 `底稿目录!A9:A19`）
  - 守卫：Property 18/19/20
  - ✅ **已交付（2026-08-12 逐点实证 `_wip_i_wave5b.py`，缺口 0）**：
    - `buildI1ListedColumns({ categories })` 在 `i1DisclosureSyncPayload.ts`（动态列，非写死 13 列）
    - 稳定 key = `i1CategoryScope.i1CategoryColumnKey()` → `` `${slot.key}_${slot.seq}` ``
      （**无中文 label 参与拼接**，守卫抽函数体后逐字核）
    - `i1_asset_categories.py` 每个类别带 `source_ref`（18 处），指向 `底稿目录!A9`~`A19`
      与 `附注披露信息（国有企业）!A9`~`A19`，「数据资源」另带 `附注披露信息（上市公司）!K10`
      （源模板 `K10` 是写死值、非 `=底稿目录!A18` 公式，故单独登记）
    - 🔴 **本轮补齐 Property 18/19 守卫**（原为唯一缺口：`iCycleDynamicRows.spec.ts` 只覆盖 20~25）。
      因需 openpyxl 直读源 xlsx，按平台范式落在**后端** `test_note_i_cycle_structure.py`
      （既有 openpyxl 基础设施，禁另建同域守卫文件），共 10 条断言：
      · Property 19 = 锚点有效性自检（`A8` 标题 + `A20` 扩位仍在原处，防行区间漂移）/
        类别 label 按 `seq` 排序逐字等于 `底稿目录!A9:A19` / `seq` 为 1..N 连续无空洞 /
        `source_ref` stale 检测（逐格 openpyxl 直读，源模板一改即红）/
        `category_defs_payload()` 与声明同序同值（无第二份真源）/「其他」为末位宽兜底
      · Property 18 = `A10:M10` 13 列非空且 N10 为空（反向自检防基线过期）/
        `B10:L10` 逐格等于类别声明、`A10`=「项目」`M10`=「合计」/
        **表头无合并单元格 ⇒ 单级 flat**（改成两级会打红提醒同步改前端表态与 `_column_groups`）/
        四层标题与三处扩位的相对位置（扩位必在层内，第四层「账面价值」是派生层无扩位）
  - 🔴🔴 **修正 design.md 的错误基线**：Property 19 原文写「`底稿目录!A9:A19`（12 类）」——
    openpyxl 逐格实测是 **11 个类别**（A9:A19 只有 11 个单元格），`I1_ASSET_CATEGORIES`
    也是 11 条、`category_defs_payload()` 返回 11 项。守卫按**实测 11** 写断言并在注释里
    标明与 spec 文本的差异，避免把错值当基线锁死。
  - **变异检验 11/11 全 RED**（`_wip_i_mutate_p1819.py`，恢复后 0 failed）：
    label 改错字 / seq 打乱 / `source_ref` 指向错单元格 / 「其他」不再最低优先级 /
    守卫锚点行区间漂移 / 合计列号写错 / 表头行号写错 / 按声明顺序而非 seq 比对 /
    payload 改走声明顺序 / payload 丢 seq / seq 出现空洞
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 13. I1 两版动态可扩类别行（上市 3 处 + 国企 4 处）
  - 上市：账面原值/累计摊销/减值准备三层末尾 `……`（源 `A18`/`A29`/`A40`）实现为可扩行
  - 国企：原价/累计摊销/减值/账面价值四层末尾 `……`（源 `A20`/`A33`/`A46`/`A59`）实现为可扩行
  - 新增类别需 `ElMessageBox.prompt` 输入名称再建行；seq 走持久化单调计数器（`max(现有最大, 已存计数器)+1`，不复用已删序号）
  - 骨架行数 `max(seed 行数, 1)`，禁 `blankRows(p, <字面量>)`
  - ✅ **已交付（2026-08-12 实证，缺口 0）**：
    - 上市：`i1CategoryScope.ts` 的 `addI1Category` / `removeI1Category` / `renameI1Category`
      + 稳定 key `${key}_${seq}`；源模板扩位 **A18 / A29 / A40** 逐格实测确认（三层各一处）
    - 国企：`i1SoeDisclosureModel.ts` 的 `I1SoeLayer = 'cost' | 'amort' | 'impair' | 'carrying'`
      四层齐备，标题逐字 = 「一、原价合计 / 二、累计摊销合计 / 三、无形资产减值准备合计 / 四、账面价值合计」；
      `addI1SoeCategory` / `removeI1SoeCategory` / `nextI1SoeCustomKey` / `maxI1SoeCustomSeq`
      （单调计数器，不复用已删序号）；源模板扩位 **A20 / A33 / A46 / A59** 逐格实测确认
    - 🔴 **国企 4 处 vs 上市 3 处的原因**：上市第四层「四、账面价值」是**派生层**
      （原值−摊销−减值，`I1_SOE_LAYER_META.carrying.movementNa=true`），源模板未给扩位；
      国企四层都给了扩位。后端守卫 `test_i1_listed_layer_titles_and_expand_marks_align`
      把「第四层不得有扩位」写成断言
    - 两个 SFC 新增类别均走 `ElMessageBox.prompt`（先命名再建行）✓
    - 两个 SFC **无 `blankRows(p, <字面量>)`**（骨架行数不写死）✓
    - 守卫 `iCycleDynamicRows.spec.ts` **25 passed**（Property 21 四层同步 / 22 撞名拒绝 /
      23 自定义 key 单调不复用已删序号）
  - _Requirements: 7.1, 7.4, 7.5, 7.6_

- [x] 14. I2 上市「研发支出」按费用性质可扩行
  - 源 `附注披露（上市公司）!A9:A15` 六类（人工费/材料费/水电燃气费/折旧费/无形资产摊销/外购在研项目）+ `A15` 可扩位
  - 实现为可扩行；两级表头 `本期发生额{费用化,资本化}` / `上期发生额{费用化,资本化}` 保持 `group`
  - I3/I4/I5/I6 断言 0 处可扩位（不得凭空加）
  - ✅ **已交付（2026-08-12 实证，缺口 0）**：
    - `i2DisclosureModel.ts` 的 `I2_NATURE_DEFAULT_NAMES` 六类逐字齐备
      （人工费 / 材料费 / 水电燃气费 / 折旧费 / 无形资产摊销 / 外购在研项目）
      + `addI2NatureRow` / `removeI2NatureRow` / `isI2NatureDefaultRow`
    - `i2DisclosureSyncPayload.ts` 保 `group` 两级表头（`本期发生额` / `上期发生额`
      × 费用化 / 资本化，另有 `本期增加` / `本期减少` 两组）
    - 守卫 Property 24（按性质可扩行）+ Property 25（列结构与附注模板同构）在
      `iCycleDynamicRows.spec.ts`；`buildI2ListedNatureSubTable` / `buildI2ListedSyncPayloads` 被消费
    - 🔴 **「I3~I6 断言 0 处可扩位」改由后端 `_SRC_DYNAMIC_MARK_COUNT` 承担**（更准）：
      该常量按 openpyxl 逐格实测冻结 12 个 (循环,变体) 的扩位数，
      实测 **I3 0/0 · I4 0/0 · I6 0/0，但 I5 listed 1(A18) / I5 soe 1(A17)** ——
      本 tasks.md 原写「I3/I4/I5/I6 断言 0 处」把 I5 的两处真实可扩位判成 0，已按实测修正
  - _Requirements: 7.2, 7.3, 7.4_

- [x] 15. 披露载荷同构与自动同步核查
  - 六循环 `iXNoteSectionMap.ts` 的 `columns` 补 `flat`/`group` 表态使与模板同构
  - 逐字核 `X_{LISTED,SOE}_SUBTABLE` 每个值 == 模板 `tables[].name`
  - `_note_texts` 每条带非空中文 `title` + 空文本过滤（全空时不产生该键）
  - 核 12 个披露 Tab 是否已接 `useDisclosureAutoSync`，且 `scheduleAutoSync` **不在**同步函数内
  - 核六个宿主是否向披露 Tab 传 `:project-id`
  - 新建 `frontend/…/__tests__/iCycleNoteSubtableContract.spec.ts`（复用 `_disclosureSubtableContract.helper`）
  - ✅ **已交付（2026-08-12 逐点实证，缺口 0）**：
    - 六个 `iXDisclosureSyncPayload.ts` 都带 `flat`/`group` 表态（I1 30 处 / I2 28 / I3 21 /
      I4 9 / I5 9 / I6 3）。🔴 注意 **columns 不在 `iXNoteSectionMap.ts`**（那里只有章节号+
      表名+准则判定，本 tasks.md 原文的位置描述有误），而在各 `iXDisclosureSyncPayload.ts`
    - `X_{LISTED,SOE}_SUBTABLE` **12 组全部 ⊆ 模板 `tables[].name`**（逐组比对
      `note_template_{listed,soe}.json` 的对应 section）：I1 4+2 / I2 5+1 / I3 4+2 /
      I4 1+1 / I5 1+1 / I6 1+1 键全命中
    - **12 个披露 Tab 齐备且全部已接 `useDisclosureAutoSync`**（缺 0）
    - **`scheduleAutoSync` 不在任何同步函数体内**（守卫按花括号配对抽函数体后判，违规 0）
    - **六个宿主全部向披露 Tab 传 `:project-id`**（缺 0）
    - `iCycleNoteSubtableContract.spec.ts` **143 passed**；`iDisclosureColumns.spec.ts`
      逐张核 I1/I4/I5/I6 的列 label 与 `group`（I4 listed「本期减少」两列同组、
      I5 listed「期末数/上年年末数」两组、I6 两版同构三列）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

## Wave 6 — 前端消费与溯源

- [x] 16. 新建 `iCycleAccountScope.ts` 科目视图单一真源
  - 复用 `composables/shared/cycleAccountScope.ts` 工厂；运行态取 render 下发的 `tb_source_codes`，常量只作兜底 + 展示
  - `isAccountAbsent()` 区分「本项目无此科目」（`found=false`）与「余额为 0」；render 未下发 ≠ 无此科目（返 false）
  - 无兜底码声明的槽 `queryCodes` 返空，绝不凭空造前缀
  - 新建 `frontend/…/__tests__/iCycleAccountScope.spec.ts`：`fs.readFileSync` 读后端 `i_cycle_accounts.py` 交叉锁死槽键 / row_code / 兜底码；`REPO_ROOT` 用双哨兵文件向上查找（禁写死回退级数）
  - ✅ **已交付（2026-08-12 实测）**：`iCycleAccountScope.ts`（14479 B）+ `iCycleAccountScope.spec.ts`
    **64 passed**（Property 26/27/28/29 + Property 2 + 严格点号边界 + 后端源码解析反向自检）
  - 🔴 **有意偏离本任务原描述**：**未**复用 `composables/shared/cycleAccountScope.ts` 工厂。
    实证根因（已写入模块头注释）：该工厂读 `semantic_account_resolver` 的 **`slots`** 形态
    （`slots[key].standard_codes` / `.codes` / `.found`，G/K 类在用），而 I 类六循环走
    **`segments`** 形态（`segments[].standard` / `.original`）—— 字段名与结构都不同，且
    工厂的二分 `gross`/`provision` **装不下 I1 的三段**（`1702 累计摊销` 名称不含「减值准备」，
    `split_gross_provision` 会判成 gross ⇒ 原值口径变净额）。硬套工厂会读到 `undefined`
    而**静默退化到兜底码**（四层检查全绿、只有浏览器暴露）。故自建段化视图，但同样
    「只写声明不写逻辑」：循环差异全由 `I_CYCLE_ACCOUNT_SPECS` 表达，六循环共用同一套取值函数
  - _Requirements: 9.1, 2.3_

- [x] 17. 六个审定表挂溯源面板 + 「从四表库带入未审数」
  - 复用 `shared/WpSemanticAccountSourcePanel.vue`；I1 三段（原值/累计摊销/减值准备）、I3 两段、I2/I4/I5 单段、I6 单段（标注本期发生额口径）
  - 传入属性必须全在被调组件 `defineProps` 键集内（守卫从 SFC 动态抽合法 prop 名比对，转 kebab-case）
  - 「带入」走 `composables/shared/adjudicationPrefillPlan.ts`：手工优先 / 幂等 / 「无此科目≠为 0」/ 预览确认
  - 宿主向审定表 Tab 传 `:html-data`（漏传 = 面板恒不渲染）
  - 面板与 sheet 内容一起包在 `<template v-else-if="currentSheet === 'IX-1'">` 内，**禁裸 `v-if` 插进分发链**
  - 📊 **2026-08-12 逐点实测（`_wip_i_task17.py`）—— 前半已交付、后半未接**：
    - ✅ 六个审定表**全部**已挂溯源面板（用 `WpFourTableSourcePanel.vue` 而非本任务原写的
      `WpSemanticAccountSourcePanel.vue`，两者都存在；I 类走 `segments` 形态、四表面板才是对的宿主）
    - ✅ 六个都有 `htmlData` prop + `extractTbSourceCodes(props.htmlData)`
    - ✅ 六个宿主（`GtI1IntangibleAssets` ~ `GtI6ResearchDevelopmentExpense`）**全部**传 `:html-data`
    - ✅ 传入 prop **零非法项**：实际传 `source-codes`/`gross-label`/`provision-label`/
      `fallback-row-code`/`hints` 五个，全在 `WpFourTableSourcePanel` 的 15 键 `defineProps` 集内
    - 🔴 **`fallbackRowCode` 是第三份行编码副本且 6 个里 5 个错位**（已在本轮修复，见下）
    - 🔴🔴 **「从四表库带入未审数」六个循环全部未接**（`prefillPlan=False` × 6）⇒
      后端 `i_cycle_prefill.build_adjudication_prefill()` 每次 render 都在算并由六个 render 策略
      `payload["adjudication_prefill"] = ...` 下发，而**前端六个宿主零消费方**
      （实测 `GtI1..GtI6` 全 MISS）—— 与 H 循环踩过的 **dead output** 完全同型
  - ✅ **本轮已交付（Task 17 前半 + 一处真 bug）**：
    - `useICycleFourTableSource.ts` 的 `fallbackRowCode` **改为由 `iCycleRowCode()` 派生**，
      删掉 6 条字面量（原值 I1 `BS-033`/I2 `BS-035`/I3 `BS-037`/I4 `BS-038`/I5 `BS-040` **全是错位旧值**，
      仅 I6 `IS-006` 正确）。该值直接渲染进面板「报表行 X」tag（`src.row_code || fallbackRowCode`）
      ⇒ render 未下发 row_code 时审计人员看到的报表行溯源是错的
    - 文案与行编码收敛为**同一 effective key** 派生（未知 wp_code 不再出现「I4 文案 + 别循环行码」）
    - 守卫：`iCycleAccountScope.spec.ts` 追加 6 条（禁 `BS-/IS-` 字面量 / 必须 import `iCycleRowCode` /
      逐项等于真源 / 未知 key 同源 / 形如 `BS-xxx` 非空 / 反向自检文件存在），**64 passed**
    - **变异检验 8/8 全 RED**（`_wip_i_mutate.py`，恢复后 0 failed）：字面量复活 / 派生值改错码 /
      断开 import / key 分裂 / 派生成空串 / I2·I5·I6 硬编码复活
  - ✅ **Task 17 后半已交付（2026-08-12）—— 消灭 `adjudication_prefill` dead output**：
    - 新建 `composables/iCycleAdjudicationSeed.ts`（纯函数，零 Vue 依赖）：后端载荷契约类型 +
      六循环 `I_CYCLE_SEED_SPECS` 声明（`labelField` + 段→列字段）+ `buildICycleSeedCells()`
    - 新建 `composables/useICycleAdjudicationSeeding.ts`（交互装配）：plan → 冲突确认框 → 逐格写入，
      **六个审定表各接 ~6 行**，不再像 G 循环那样 8 处各抄一份 70 行流程
    - 六个 SFC 全部接通 + 工具栏加「从四表库带入未审数」按钮（含 `data-testid`，六个互不相同）
    - 🔴 **段键翻译**：后端 `amortization` ↔ 前端 `I1BlockType='amort'`，不翻译则 I1 累计摊销段
      整段静默丢失（TS 拦不住，`block` 运行时只是字符串比较）
    - 🔴 **I1 是唯一三段循环**：三段的 `rowKey + field` 完全相同（都是 `unadjusted`），
      只有 `block` 能区分 ⇒ `applyCell` 必须用四参 `updateCell(block, …)`，
      且 block 反查失败时**拒绝写入**（不猜段）
    - 四条口径逐条落实：手工优先（冲突进确认框，默认「仅补空值」）/ 幂等（值相同不写）/
      「本项目无此科目 ≠ 为 0」（`absentSlots` 进 tooltip，**不填 0**）/ 未命中不兜底
      （`unclassified` 交审计师显式归入，`defaults` 恒为空数组且被守卫正向断言）
    - 守卫 `__tests__/iCycleAdjudicationSeed.spec.ts` **90 passed**：段键与后端 py 交叉锁死 /
      列字段名与各 composable 行模型交叉锁死 / 行为级三态 / 六 SFC 接线锁死（防 dead output 复发）
    - **变异检验 23/23 全 RED**（纯函数层 10 + 六 SFC 接线 13，恢复后均 0 failed）
  - 🔴🔴 **本轮抓出的真缺陷（若无变异检验会全部成为假绿）**：
    1. **I3 的行标签是 `investee` 不是 `projectName`** —— 首版声明写错。而首版守卫（「字段名在
       行模型里存在」）**放过了它**：`projectName` 确实出现在 `normalizeI3AdjudicationRow` 的
       **读取兼容别名** `raw?.investee || raw?.projectName` 里。归一后的行上只有 `investee`
       ⇒ 全部行标签取空串 ⇒ 每行都匹配不上 ⇒ **整循环带入静默失效**。
       修法：判据升级为「labelField == 该 SFC 既有 `bringInRows` 的 `name: r.X`」（生产已验证的字段）
    2. **变异 W6 判 GREEN**：`updateCell(block` 的全文 grep 被 I1 里另一处 `onCellChange`
       内的同名调用满足 ⇒ 把 `applyCell` 的 block 换成写死 `'cost'`（三段全落原值段）照样绿。
       修法：括号配对抽 `applyCell` 体后再判 + 拒绝 block 字面量 + 反向自检（体长上下界）
    3. **变异 W10/W2 判 GREEN**：SFC 可绕过声明层自己写死 `labelField`；`wpCode: 'I5'` 的全文
       grep 被同文件 `useAdjudicationBringIn({ wpCode: 'I5' })` 满足。
       修法：两者都限定在 `useICycleAdjudicationSeeding({…})` **调用体内**判，并要求
       labelField 必须取自 `iCycleSeedSpec()` 且真的用于读行标签
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 18. 金额控件与展示格式收口
  - 六循环披露与审定表金额列换 `WpAmountInput`；比率/使用年限/摊销月份/占比列保持 `el-input-number`（反向边界断言）
  - 只读金额一律走 `displayPrefs.fmtAmount()`（setup 顶层 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`）
  - 🔴 `DisplayPrefs_Key` 从 `components/workpaper/composables/displayPrefsKey.ts` 引入，**不是** `stores/displayPrefs`
  - ✅ **已交付（2026-08-12，改动 23 个 SFC）**：
    - **金额控件侧本来就已合规**：`el-input-number :formatter`（平台实证的空操作）在 I 循环
      **命中 0 处**；`WpAmountInput` 已覆盖 **18 个文件 / 112 处**（6 个审定表 + 12 个披露 Tab）
    - 🔴🔴 **真缺口在只读金额侧：16 个 SFC 各写了 7 种不同的本地 `fmtAmount`**，
      全部 `toLocaleString('zh-CN', {min/maxFractionDigits:2})` 硬编码「2 位小数 + 千分符」
      ⇒ **取不到用户的单位偏好（元/万元）与 `showZero`**，且零值返 `-` 还是 `—` 七种实现里
      全半角混用不一致。另 1 个（`I3TabDetail.vue`）直接 import `@/utils/formatters` 的
      底层 `fmtAmount`（同样不读偏好）
    - 收敛：17 个文件（16 本地定义 + 1 formatters import）改为
      setup **顶层** `const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`
      + 函数体 `return displayPrefs.fmtAmount(v)`。**保持函数签名与模板零改动**（模板 100+ 处调用不动）
    - 另补 6 个披露 Tab（I3/I5/I6 两版）：它们已用 `displayPrefs.fmtAmount` 但只写了
      `useDisplayPrefsStore()`、**缺 inject 分支** ⇒ 宿主 provide 的偏好拿不到，已补齐
    - 改造脚本 `_wip_i_task18_apply.py` / `_wip_i_task18_inject.py` **幂等**
      （复跑 `--check` = 0 改动 / 23 跳过），会话结束随 `_wip_*` 一并清理
    - 反向边界实测 **0 违规**：比率/利率/汇率/占比/年限/月份/笔数/折现率/增长率/毛利率
      等非金额列未被误换成 `WpAmountInput`（首版探针报 22 处，逐标签复核发现全是
      `style="width:100%"` 的 `%` 落进 400 字符窗口 —— 探针误报，非真违规）
    - 守卫：`iDisclosureColumns.spec.ts` 新增 **Property 30** 7 条
      （禁 `:formatter` / 禁本地 `toLocaleString` / 必须顶层 `inject ?? store` /
      `DisplayPrefs_Key` 来源单一 / 反向边界 / 两条反向自检：扫到 ≥70 个 SFC、≥20 个真消费方）
    - 平台级守卫 `displayPrefsKeyImportSource.spec.ts` **7 passed**（未引入崩页风险）
    - **变异检验 5/5 全 RED**（`_wip_i_mutate_t18.py`，恢复后 0 failed）：
      本地 `toLocaleString` 复活 / `inject` 退化为纯 store / `DisplayPrefs_Key` 从 store 引 /
      `:formatter` 复活 / 非金额列误用 `WpAmountInput`
  - _Requirements: 9.5_

## Wave 7 — 收口与验收

- [x] 19. 源模板缺陷登记表
  - 新建 `I_CYCLE_SOURCE_DEFECTS` 登记（放守卫文件或独立数据文件），覆盖 6 处：I1 审定表 tab 名缺 `-1`、I2 上市 `=#REF!` 15 格（`A35:D39`）、I1 上市 `D20:L20` 把「处置」写成「购置」、I6 目录第 7~14 项指向 I2 底稿（**有意跨 workbook 非笔误**）、I5 目录 `B4` 序号缺失、I3 hidden sheet
  - 每条带 `source_ref` + 处置方式（按意图实现 / 原样保留 / skip）
  - 确认 `市场平均收益率2017` 与 `GT_Custom` 在 `wp_code_overrides.json` 按**完整 sheet 名**标 `skip`（按尾码会误杀）
  - 断言不修改 `backend/wp_templates/I/**` 任何 xlsx（md5 冻结）
  - ✅ **已交付（2026-08-12）**：
    - 新建 `backend/app/services/four_table/i_cycle_source_defects.py`（声明式登记，
      范式对齐 `i1_asset_categories.py`）：`ICycleSourceDefect` dataclass 带
      `defect_id` / `cycle` / `title` / `source_ref` / `evidence`（逐格实测证据）/
      `disposition` / `rationale` / `expect_token`（stale 检测用），
      `I_CYCLE_SOURCE_DEFECTS` **6 条**一一对应 AC 10.1~10.6，另有
      `defects_of()` / `defect_by_id()` / `defects_payload()` 三个取值函数
    - 处置分布：`keep_as_is` 3 条（AC1 tab 名 / AC4 跨 workbook / AC5 序号缺失）·
      `implement_intent` 2 条（AC2 `#REF!` 续表 / AC3 处置笔误）· `skip` 1 条（AC6 hidden sheet）
    - **hidden sheet 按完整名 skip 已核**：I 循环 hidden 集合实测 = `{GT_Custom, 市场平均收益率2017}`，
      两者在 overrides 里都是**整串键** → `skip`；守卫另断言「必须是整串键」防有人改成尾码规则
    - **md5 冻结已落**：六份源 xlsx 逐字节冻结（I1 `329be34a…` / I2 `c656c764…` /
      I3 `937daf9c…` / I4 `471cc8cd…` / I5 `c88837d8…` / I6 `ba378383…`）
      + 反向自检「基线必须覆盖全部六份」
    - 守卫 15 条（加进既有 `test_note_i_cycle_structure.py`，**未另建同域文件**），
      该文件 **189 passed**；后端全域 **2429 passed / 0 failed**
    - **变异检验 12/12 全 RED**（`_wip_i_mutate_t19.py`，恢复后 0 failed）：漏登一条 /
      defect_id 改名 / source_ref 指向不存在 sheet / expect_token 写错 /
      处置从 skip 改 keep_as_is / overrides 撤 skip（两处）/ 投影外泄 evidence /
      非法 disposition / evidence 置空 / md5 基线改错 / md5 基线漏一份。
      **只变异登记模块与 overrides，不碰源 xlsx（AC 10.7）**
  - 🔴🔴 **AC6 是真缺口，已修**：`市场平均收益率2017` 原先**未在 `wp_code_overrides.json` 登记**。
    库侧实测它**已被分类进 `workpaper_sheet_classification`**
    （`sheet_name='市场平均收益率2017'` / `wp_code='I3'` / `class_code='H-辅助说明'`）——
    因为分类链路**不读 `sheet_state`**（`GT_Custom` 是 `wp_classification_service` 里的
    硬编码特例），hidden 不会自动过滤，只认 `_WP_CODE_OVERRIDE.get(sheet_name)=="skip"`。
    已补 `"市场平均收益率2017": "skip"`（loader 复验 1526 键、取值 `skip`），
    并加守卫「登记为 skip 的必须在 overrides 里真有 skip」防纯注释承诺。
    🔴 注意 `wp_code_overrides.json` 真实路径是 **`backend/app/data/`**（非 `backend/data/`）。
  - 🔴 **两处 spec 计数与源模板不符，守卫按实测冻结**：
    1. **AC 10.2 与本条正文都写「15 格」，实测 20 格**（A~D 列 × 35~39 行）。上下文锚点
       A33='续：' / A34='项目' / A40='合计' / A41=资本化说明 ⇒ 「资本化情况续表」意图成立
    2. **AC 10.3 的笔误范围需精确到列**：row20（A20='（1）处置'，隶属 A19='3.本期减少金额'）里
       **B20/C20 正确用「处置」、D20:L20 共 9 格误写「购置」**，
       是从 row14（A14='（1）购置'，隶属 A13='2.本期增加金额'）横向复制后
       「前两格改了、后九格漏改」。而 row14 的 B14:L14 全用「购置」是**正确的**——
       守卫专门钉死这 11 格不得被一起「修正」
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 20. 变异检验
  - 新建 `backend/scripts/diagnose/mutate_i_cycle_guards.py`
  - ≥12 个变异，逐个覆盖 Property 1/2/3/6/8/9/15/16/17/18/21/23
  - 三态区分（RED / GREEN / ANCHOR-MISS）；锚点行级定位且命中数必须为 1；备份落 `.bak` + `--restore` 字节级还原 + md5 核验
  - 按「失败测试名集合差集」判定，不看退出码（Wave 1 守卫基线本就有红）
  - subprocess 传 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，参数用列表不经 shell
  - ✅ **已交付（2026-08-12）**：`backend/scripts/diagnose/mutate_i_cycle_guards.py`
    **14 个变异，覆盖 P1/P2/P3/P6/P8/P9/P15/P16/P17/P18/P21/P23 全 12 个 Property**
    （P21/P23 各 2 个），**14/14 全 RED，两侧恢复后零残留污染**
  - 实现要点逐条落实：
    - **四态判定**（比要求的三态多一个）：`RED` / `GREEN`（守卫缺陷）/
      `ANCHOR-MISS`（脚本缺陷）/ `WRONG-TEST`（打红但非预期项）——
      只看退出码会把后三态误判成 RED
    - **锚点命中数必须为 1**；个别「文件里出现任意一处即该打红」类判据用
      `allow_first=True` 显式放宽（P17/P21 两条），其余一律唯一定位
    - **备份 `.mutbak` + finally 必还原 + md5 字节级核验**；`--restore` 可在
      Ctrl+C 中断后手工还原；**启动前检测残留备份**，有则拒绝执行（exit=1）
      —— 三条机制均已实测（无残留时正确空转 / 有残留时拒绝启动 / 还原后字节一致）
    - **按失败测试名集合差集判定**，不看退出码（`baseline_failed` → `mutated_failed`，
      判据 = `expect_test ∈ 差集`）
    - subprocess 传 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，参数用列表不经 shell
    - `--only P1,P6` 可单跑、`--list` 只列清单
    - **只变异生产文件，不变异测试文件本身**（改判据不算变异被测对象，前几轮踩过：
      把 `== expected` 改成 `!= None` 属削弱判据，必然仍绿）
    - **不变异源 xlsx**（二进制 + 运行时权威模板，Requirement 10.7 明令不得反改）
  - 🔴🔴 **本任务又抓出 2 个真守卫缺陷（首轮 P3/P15 判 GREEN），已补判据后转 RED**：
    1. **P3：I 循环纯函数层完全裸奔**。把 `i_cycle_prefill.build_leaf_project_rows` 的
       `sign = abs if seg.absolute else ...` 改成恒等（备抵段不再取绝对值 ⇒ 累计摊销/
       减值准备全变负数），**全库无一条测试打红**。实测全库确实**没有任何守卫测**
       `build_leaf_project_rows` / `segment_amounts` / `build_i1_category_rows` ——
       其余循环（D6/F2/K1/K2/N1~N5）都测了自己的 `build_adjudication_prefill`，只有 I 循环没有。
       Property 3 原本只靠「落地前连库 A/B 对照」，那是一次性的、不进 CI、拦不住回退。
       已补 `test_i5_absent_account.py::TestProperty3LeafAggregationPurity` **8 条常驻判据**
       （备抵取绝对值 / 反向边界非备抵段不得取绝对值 / `credit_is_increase` 增减互换 /
       空前缀段返空不造零行 / 未命中不兜底 / 同名叶子合并但保留全部溯源码 /
       `segment_amounts` 与逐行求和一致 / 反向自检 `absolute` 开关结果必须不同）
    2. **P15：自洽性判据的固有盲区**。把 `fix_note_i_cycle_structure._I5_TABLE2_NAME`
       改回 90 字符泄漏名，既有守卫全绿 —— 因为①「表名不得以 `[` 开头/超长」读的是
       **模板 JSON**，改脚本常量不重跑脚本 JSON 不变；②`--check` 比对的两侧
       **都由同一常量推导**，改了常量两边一起变、仍自洽。
       **自洽性判据只能保证两侧一致，不能保证两侧都对。**
       已补 3 条直接对**脚本常量**断言形态的判据（长度/前缀/句读符号 + 泄漏名只能作
       alias + 脚本常量与模板 JSON 双向一致），两条路都堵死
  - 🔴 **另修 2 个变异脚本自身缺陷**（不是守卫问题）：P6 锚点漏了 `name_keywords` 行
    导致 `fallback=()` 命中 2 次（I3.impairment 与 I5.cost 都有）；
    P15 的替换文本原写 `_I5_TABLE2_NAME = _I5_TABLE2_LEAKED_NAME`，而后者**定义在前者之后**
    ⇒ `NameError` 让整模块导入失败、测试全部 error 而非「打红预期那条」，差集里找不到
    `expect_test` 被误判成 GREEN。改为直接写泄漏名字面量
  - 零回归：后端 **2443 passed / 0 failed**
  - _Requirements: 11.3_

- [x] 21. CI job
  - `.github/workflows/governance-checks.yml` 新增 `i-cycle-extraction-closure`（后端）与 `i-cycle-frontend`（前端）两个 job
  - 逐个 `Path.exists()` 断言引用文件存在；`yaml.safe_load` 验证可解析且无重名 job
  - 后端 job 含：4 个守卫文件 + 2 个幂等脚本 `--check`
  - ✅ **已交付（2026-08-12）**：
    - **新增后端 job `i-cycle-extraction-closure`**：4 个守卫
      （`test_i_cycle_row_code_evidence` / `test_i_cycle_accounts` /
      `test_i5_absent_account` / `test_i_cycle_formula_presets`）
      + `test_note_i_cycle_structure`（源模板缺陷登记 + md5 冻结）
      + **2 个幂等脚本 `--check`**（`fix_note_i_cycle_structure` / `fix_i_cycle_prefill_presets`）
    - **扩充既有 `i-cycle-frontend`**（加 `iCycleDynamicRows` + `iCycleAdjudicationSeed`
      两组原先不在 CI 内的守卫）
    - 无 DB 依赖已实测：4 个守卫 + 2 个 `--check` 全部 rc=0 / 0 skipped
      （读快照与源 xlsx，不连库）；两个 job 的完整命令本机实跑 **228 / 65 passed**
    - 新建守卫 `backend/tests/test_i_cycle_ci_wiring.py` **22 passed**（范式对齐
      既有 `test_k_cycle_ci_wiring.py`）：`yaml.safe_load` 可解析 + job 数下界 /
      四个 I job 存在 / **原始文本查重名** / 新 job 有 checkout+setup-python+openpyxl /
      后端引用路径与脚本逐个 `Path.exists()` / **前端 spec 逐个 exists** /
      5 个后端守卫与 6 个前端守卫的覆盖面 / 2 个脚本必须带 `--check` /
      禁 `|| echo "::warning::"` 与 `continue-on-error` / 3 条反向自检
    - **变异检验 9/9 全 RED**（`_wip_i_mutate_t21.py`，恢复后 yml md5 一致）：
      幽灵过滤器 / 后端引用不存在的守卫 / 撤 `--check` / job 改名 / 造重名 job /
      warning 兜底 / 依赖漏 openpyxl / 前端漏 spec / `continue-on-error`
  - 🔴🔴 **守卫首跑即抓出既有 CI 的真缺陷**：`i-cycle-extraction` job（前一个 spec 建的）
    引用了**两个不存在的测试文件** —— `test_i1_asset_categories.py` **从未存在**
    （其判据并入了 `test_i_cycle_accounts.py`）、`test_i_cycle_leaf_aggregation.py`
    实名是 `test_leaf_aggregation.py`。pytest 遇到不存在的路径会整 job 红
    ⇒ 该 job **自建起就没真跑过**（或长期红着没人管）。已修正引用。
  - 🔴 **有意偏离 tasks.md 原文**：原文写「新增 `i-cycle-frontend`」，但该 job
    **前一个 spec 已建**。照抄会造成重名 —— `yaml.safe_load` 对重复 key **静默保留
    最后一个**，前一个 job 连同它的 5 个前端守卫整段消失且零报错。
    故实际处置 = 新增 `i-cycle-extraction-closure` + **扩充**既有 `i-cycle-frontend`，
    并把「原始文本查重名」写成守卫钉死。
  - 零回归：后端 **2465 passed / 0 failed**
  - _Requirements: 11.4_

- [x] 22. 零回归
  - **前后对照**（禁 `git stash` / HEAD-swap）：施加改动前跑一次收集失败集合 → 施加改动 → 再跑一次求差集，新增必须为 0
  - 后端范围 `backend/tests/four_table/` + `-k "i_cycle or i1 or i2 or i3 or i4 or i5 or i6 or note_i"`（参数用列表传，不经 shell）
  - 前端范围 `npx vitest run i1 i2 i3 i4 i5 i6 iCycle --reporter=json --outputFile=<abs>`
  - 逐个 `Path.exists()` + Vite transform 200 核改动文件
  - ✅ **已交付（2026-08-12）**：`backend/scripts/diagnose/verify_i_cycle_zero_regression.py`
    （只读、可复跑、`--skip-vite` / `--files-only` 两个快捷模式）
  - **实测结论：✅ 零回归成立**
    - 后端 **2465 passed / 0 failed**（`four_table/` 全量 + 3 个 I 循环守卫文件）
    - 前端 **1488 tests / 0 failed / 0 files failed**（vitest 子串过滤
      `iCycle` + `iDisclosureColumns` + `i1`~`i6`）
    - 改动文件 **37 个（后端 8 / 前端 29）逐个 `Path.exists()` 全部存在**
    - Vite transform：**本 spec 的 29 个前端改动文件零崩溃**
  - 🔴 **判据设计上有意偏离原文，理由如下**：原文要求「施加改动前跑一次 → 施加改动 →
    再跑一次求差集」，但**本 spec 的改动已施加完，"改动前"那一次跑不回来了**；
    而原文同时禁用 `git stash` / HEAD-swap（memory 已记：会卷走并发会话的未提交改动、
    且 `.pyc` / vite 缓存不同步会造假绿）。用 stash 造出来的「改动前」也不是真的改动前
    —— 工作树里还有 3 个并发会话的改动。故改为**可复跑的常驻判据**（比一次性对照更有长期价值）：
    1. **改动域判据（硬性）**：I 循环域失败必须为 0 ← 这是「本 spec 是否引入回归」的直接判据
    2. **改动域外判据（软性，只报告）**：其余失败须 ⊆ 登记的 `KNOWN_FOREIGN_FAILURES`
       （12 条，K13/K10/K12/L2L4/H-G/F3/F5/g7 等并发会话域，**只登记文件名不登记条数**
       —— 对方进度会让条数浮动）。登记外的新失败会列出来供人工判断但**不判失败**，
       因为无法区分「本 spec 引入」与「并发会话刚写坏」，**谎称能自动区分才是假绿**
    3. 改动文件存在性 + Vite transform（调平台既有 `vite_transform_smoke.mjs`，
       全树扫描、改动文件是其子集）
  - 📋 **顺带发现别人域的缺陷（不在本 spec 边界，仅登记）**：Vite 全树 transform 报
    **35 个文件崩溃，全在 M8/M9 域**，根因是它们 import 了 `@/utils/request` ——
    该模块**全库不存在**（正确的是 `@/utils/http`）。这些文件在浏览器里会直接白屏。
    平台的 `vite-transform-smoke` job 是 `continue-on-error: true`，所以 CI 不会拦住它。
    建议 M 循环的 spec 修正该 import 并考虑把该 job 改为 blocking。
  - _Requirements: 11.5_

- [x] 23. 真实库验收
  - ✅ **已交付**：`backend/scripts/diagnose/verify_i_cycle_live.py`（只读，无 `--apply`，
    不写库不经 HTTP；`--json` 可导出完整报告）
  - **实跑结果：`VERDICT: 通过` —— 项目 8 个 × 6 循环 = 48 格，异常 0 格，硬性判据失败 0 条**
  - 项目数实证：`projects` 表 32 个未删项目中,含 I 循环数据（17xx/18xx/66xx）的**恰好 8 个**，
    与 tasks 原文「8 项目」吻合。🔴 其中**只有 1 个 `template_type=listed`**
    （重药控股安徽有限公司_2025），旧临时探针 `_wip_i_live.py` 的 `LIMIT 6` 恰好把它漏掉
    ⇒ 验收脚本不设 LIMIT，否则上市分支零覆盖
  - 六态输出齐备：`resolved_from`（顶层 + 段级）/ `standard`+`original` 码集 /
    `parent_check.diff` / `tb_values` 非零键数 / `prefill` 段数 / `unmapped` 数
  - 🔴🔴 **判据偏离原文（连库实证后两次改判，脚本 docstring 内留全证）**：
    - 原文「`resolved_from` 全为 `report_config`（I5 除外）」**实测不成立，且不成立的原因是
      正常业务形态**：`BS-032 = TB('1701')-TB('1702')` 公式**本就不含 `1703`**（无形资产
      减值准备）⇒ I1 的 `impairment` 段永远认领不到、必然 `fallback`（靠段声明的兜底码）；
      同理 I3 的 `impairment`（`BS-034` 只有 `1711`）。照原文判会把对值当错值
    - **第一版改判也是错的**（留证防重犯）：写成「`set(seg.standard) ∩ formula_codes ≠ ∅`
      ⇒ 必须 `report_config`」，实跑打红 6 条全是 I2 的 `cost` 段 —— 但代码是对的。
      错因：`resolve_i_cycle_accounts` 在认领失败时把 `std` **覆盖为 `spec.fallback`**，
      而 I2 的兜底码**恰好也是 `1704`** ⇒「码集与公式有交集」推不出「被公式认领」，
      巧合被当成了因果
    - **现行判据 D4**：脚本**独立重算**一遍 `claim_segments(...)` 再比对最终产物
      （`resolved_from` + `standard` 码集）双向自洽。防自证边界已在 docstring 写明：
      重算的是中间量、比对的是最终产物，能抓「赋值逻辑写错」，抓不到 `claim_segments`
      自身错（后者由 `test_i_cycle_accounts.py::test_i2_1703_unclaimed` 等单元守卫覆盖）
  - 判据清单：D1 `row_code` 对账 / D2 无 `row_name_mismatch`（行名闸未触发）/
    D3 `parent_check` 全部 |diff|<=0.01 / D4 段级溯源双向自洽 / D5 I5 `standard==[]`
    宁缺勿造 / D6 `unmapped`+未认领码如实列出（软）/ D7 认领失败但客户科目表有该码
    → 提示可做科目映射（软）
  - 🔴 **「无法验收」分支做了变异检验**（否则这条要求是假绿）：把候选项目 SQL 加
    `AND false` 造「无候选项目」⇒ 实测 **rc=2 + 打印 `VERDICT: 无法验收` + 不含
    `VERDICT: 通过`**，判定 RED。变异后已核验无残留（`AND false` 0 处、锚点原文 1 处、
    往返字节无损、重跑仍 `VERDICT: 通过`）
  - 连库实证的因果链（供后来者复核，不必重跑）：
    `claim_segments` 明确「名称取不到的码不认领，绝不按码序猜段」，`name_lookup` 只取
    `account_chart` 的 **standard 源**。`code='1704'` 在 standard 源仅 **2/8** 个项目存在
    （重药控股安徽_2025、陕西华氏医药_2025）→ 这 2 个 I2 `cost` = `report_config`，
    其余 6 个走 fallback（正确）。`1911` 全库两个 source **零命中** → I5 `standard=[]` ✓。
    「宜宾医药新健康大药房临港店_2025」`client` 源**有** `1704` 但 standard 源没有
    ⇒ 反证认领只看 standard 源
  - 📌 **D7 实测抓出 4 处改进机会**（非缺陷，已在报告输出）：3 个项目的 `1703`
    + 1 个项目的 `1704` 在**客户科目表有、标准科目表无** ⇒ 做一次科目映射即可把溯源
    从「兜底科目」恢复成「报表规则映射」
  - 📌 **另发现一处隐患已登记**：`6604` 在 `client` 源里有 1 个项目名为**「勘探费用」**
    而非「研发费用」。当前 I6 用 standard 源故未受影响，但若后续改为 client 优先会静默取错
  - _Requirements: 11.6_

- [x] 24. 浏览器实测 + 数据复原 + 临时产物清理

  ### 🔴🔴 实测抓出并修复的两个「四层守卫全绿、只有浏览器暴露」缺陷（本任务最大价值）

  **① `checklist-responses` 缺 `/api` 前缀 ⇒ I1~I6 全部录入静默丢失**
  - 发现：装 XHR 拦截器抓到 `PUT /workpapers/{uuid}/checklist-responses → 404` × 210
  - 三重实证：`utils/http.ts` 的 `baseURL: '/'`；同文件的附注同步却写 `/api/projects/…`；
    全库其余 40+ 处一律 `api.put('/api/workpapers/…')`
  - 影响 9 处 / 8 文件（I 循环 7 处：`GtI1`/`GtI2`/`GtI3`/`GtI4`/`useI5FormData`/`GtI6`(×2)；
    H3 跨域 2 处：`h3MortgageReconcile`/`h3TransferReconcile`）。调用点全包在
    `catch { /* silent */ }` ⇒ 审计师填完点保存无报错、**数据从未落库**
  - 修复脚本 `backend/scripts/fix/fix_checklist_responses_api_prefix.py`（幂等 + `--check`
    + 反向自检；正则只匹配模板插值故不误伤测试里的字面量断言）
  - 实测验证：`PUT /api/workpapers/{uuid}/checklist-responses → 200` × 140，库里真实新增
    **15 行**（含 `I1-listed-categories` 的 11 个类别、`movement`、`amort-alloc`、
    `data-resource`、6 段 note 文本）⇒ 丢的不只是审计说明，是**披露表全部录入**

  **② `maxI1SoeCustomSeq` 缺 import ⇒ 国企版披露 tab 挂载即崩**
  - 现象：点「附注披露信息（国有企业）」→ `页面渲染出错: maxI1SoeCustomSeq is not defined`
  - 根因：`useI1Disclosure.ts` 第 487/546 行使用它，但 import 块从
    `i1SoeDisclosureModel` 只导了 8 个符号、漏了这一个
  - 🔴 **四层守卫全绿**：vitest（`iCycleDynamicRows.spec.ts` 测的是 model 层、自己 import 了）
    / vite transform（单文件编译不解析跨模块符号）/ `get_diagnostics`（实测 **No diagnostics found**）
    / `AutoImport` 也只配了 `['vue','vue-router','pinia']` 不含项目符号
  - ⇒ **Task 13 标「已交付」时未做浏览器实测，国企版披露 tab 一直不可用**。修复后四层结构
    实测可见（`一、原价合计`/`二、累计摊销合计`/`三、无形资产减值准备合计`/`四、账面价值合计`）

  ### ✅ AC 8.6 完整兑现（soe 版 `八、27`，宜宾临港店_2025）

  | 项 | 基线 | 推送后 |
  |---|---|---|
  | `last_sync_at` | **NULL** | **`2026-08-15 03:16:32`** ← 前移 |
  | `last_sync_source` | — | `workpaper` |
  | `last_sync_wp_id` | NULL | `77168d01…`（= I1 底稿 wp_id） |
  | `sub_table_data` 表数 | 0 | **1**（`无形资产情况`，52 行） |
  | `_sub_table_columns` 表数 | — | 2 |
  | `td_len` | 28887 | **35650** |

  - `current_standard=soe_standalone` / `_last_sync_sheet=附注披露信息（国有企业）` 均正确
  - 📌 `col_meta(2) > sub_tables(1)` **不是缺陷**：`I1_SOE_COLUMNS` 源码注释已声明
    「载荷当前不推该表（`buildI1SoeSubTableData` 只产 movement），但列头声明保留与模板同构」，
    且 `note_template_soe.json` 的「八、27」确实有「确认为无形资产的数据资源」表
    （底稿 xlsx 不采集 / 附注 docx 要披露，正常结构差）。源模板实测：soe sheet 的「数据资源」
    只在 `A18/A31/A44/A57` 作四层类别行出现，无独立表

  ### ✅ 其他已实测项

  - **隔离上下文**：`new_page` 传 `isolatedContext='i-cycle-t24'`
  - **基线**：`_wip_i_t24_baseline.py`（capture/diff/restore 三合一），抓 `parsed_data` 全文
    + md5 + `jsonb_typeof` + `checklist_responses` 逐行 + `disclosure_notes` 全文/子表数/`last_sync_at`
  - **I1-1 审定表溯源面板**：`四表库取数口径` → `报表行 BS-032`（Task 4 row_code 收敛实测印证）
    → `无形资产原值（1701） 报表规则映射` / `累计摊销（1702）+ 减值准备（1703） 兜底科目`；
    三段结构 + 净值段 + 11 类别行（含「矿产权」，印证 P16 锚点）；「从四表库带入未审数」按钮在位
  - **I1 上市披露**：13 列（11 类别 + 合计，含「探矿权/采矿权」）· `+ 增加资产类别列` ·
    源模板「……」可扩位 **4 处**（原值 1 + 累计摊销 1 + **减值准备 2**，tasks 原文写「三层」需复核）
    · `Note:五、26` chip · 6 段文字说明 · 摊销归属(I1-9) · 数据资源子表
  - **金额格式**：输 `1234567.5` → 失焦显示 **`1,234,567.50`**（千分符 + 2 位小数），
    控件是 `el-input__inner` 而非 `el-input-number`（Task 18 收口有效）；该页 `el-input-number` 计数 **0**
  - **守卫「拒绝时零写入」（Property 6）**：listed 版推送被 `STANDARD_MISMATCH` 409 拦下
    （重药控股安徽 `template_type=listed` 但 `entity_type=soe`，项目自身配置矛盾），
    随后 `disclosure_notes` 零漂移
  - **数据复原**：两轮实测共复原 15 + 13 行，`--diff` 均「无漂移（与基线逐字一致）」，
    并用 postgres MCP 独立通道交叉核实（`t24_marks=0` / `i1_rows_left=0` /
    `八、27` 回到 `last_sync_at=NULL, td_len=28887, sub_tables=0`）
  - **零回归**：后端 2486 passed / 0 failed；前端 1488 tests / 0 failed；
    vite transform 4067/4067 / **0 崩溃**

  ### ✅ 用户要求「逐一补充」后的补测（5 项，逐项落实）

  #### 补测 1/5 ✅ 另 5 个审定表（I2-1~I6-1）溯源面板逐个点开

  - **4 个通过**：I2-1（`BS-034` / 开发支出 `1704` 兜底）· I3-1（`BS-035` / 商誉 `1711`
    报表规则映射）· I4-1（`BS-036` / 长期待摊 `1801`）· I6-1（`IS-006` / 研发费用 `6604`
    + 本期发生额口径标注）
  - 🔴 **I5-1 面板整块未渲染**（组件已挂载）：根因 `1911` 全库不存在 → `tbSourceCodes` 空 →
    面板按「禁空洞卡片」自我隐藏，**与 Task 17 的 `isAccountAbsent()` 显式提示要求相悖**。
    已在 `hiExtractionSegments.ts` 注释登记，见补测 5/5

  #### 补测 2/5 ✅ 「从四表库带入未审数」实点 —— 抓出平台级共享件缺陷

  原判「测试项目取数为 0，点了无判据价值」**是错的**：正因为是 0，才暴露了缺陷。

  - **实点结果（I1-1 / 宜宾临港店 soe）**：toast 报 `补填 18 格`，但表内 210 个 input
    **全为空/0**；同时 7 个 `PUT /api/workpapers/{id}/checklist-responses` 全 200
    （修复 A 的 `/api` 前缀在此得到二次印证）
  - **根因（抓 render-config 实证）**：`html_data.adjudication_prefill` 如实下发
    3 段 × 6 类别 = 18 行，每行 `opening/closing/increase/decrease` **全为 0**
    （该项目 `tb_balance` 无 17xx 余额）
  - **对照组证明后端无误**：和平药房_2024 同一 I1 底稿 `cost` 3 行期末合计
    **5,445,065.12** / `amortization` 3 行 **2,870,275.43**；I4 leaf 模式 **6,382,978.23**
    ⇒ 缺陷只在前端写入判定
  - 🔴 **缺陷性质 = 模块自己立的口径漏了一个入口**：`shared/adjudicationPrefillPlan.ts`
    模块头第 3 条早已写明「本项目无此科目 ≠ 该科目为 0，不写 0」（E1「存放财务公司款项」实证：
    写 0 会把「不适用」伪装成「已核实为零」），但旧实现只堵了**入口 A「槽未命中」**
    → `absentSlots`，漏了**入口 B「槽命中但金额为 0」**。后果三条：
    ① 审计师看到「补填 18 格」以为带入了真实数据，实际把「无余额」记成「已核实为零」；
    ② 白写 18 格刷新 `updated_at`、触发附注同步链路；
    ③ **UI 上写 0 与留空都渲染「-」**（`fmtAmount` 平台口径）⇒ 缺陷在界面上完全不可见
  - **修复**：`AdjPrefillPlan` 新增 `zeroSkipped` 桶；「当前格为空 + 四表金额 ≤ 容差」
    进该桶不写入；`describeAdjPrefillPlan` 如实提示「N 格四表余额为 0，未写入（本项目该科目
    无余额；如需记录「已核实为零」请手工填 0）」，并**不再谎称「一致 / 无需带入」**
  - **影响面**：平台级共享件，11 个审定表 Tab 受益（G1/G2/G4/G6/G8/G9/G10/G11/H2/H4
    + I 循环 6 个经 `useICycleAdjudicationSeeding`）
  - **守卫** `composables/__tests__/adjudicationPrefillZeroSkip.spec.ts`（13 tests）：
    含 4 条「不得侵蚀既有三条口径」回归项（四表 0 + 已有非零 → 仍进 `conflicts`；
    四表 0 + 已有 0 → `identical` 幂等；非数值内容仍优先保护；负数余额不被误跳）
    + 实测真实形态回归（18 格全 0 → 0 写入）
  - **变异检验 = RED**：把 `Math.abs(cell.amount) <= PREFILL_TOLERANCE` 改为
    `false && ...` → **6 failed / 7 passed**，打红的正是 6 条新行为断言，
    7 条 passed 全是回归保护项（旧行为下本就应绿）⇒ 非 GREEN / 非 ANCHOR-MISS / 非 WRONG-TEST
  - **浏览器复验修复后**：toast = `18 格四表余额为 0，未写入（本项目该科目无余额；
    如需记录「已核实为零」请手工填 0）`，且 `--diff` **无漂移**（零库变更，
    「不写入」得到数据层印证，不只看 toast）
  - **辐射面零回归**：`vitest run Adjudication Prefill` → **53 files / 804 tests passed / 0 failed**

  #### 补测 3/5 ✅ 动态类别行增删改名 + I2 上市可扩行 —— 抓出两个缺陷（含整页崩溃）

  | 缺陷 | 用户可见表现 | 根因 | 修复 |
  |---|---|---|---|
  | I1 soe「+ 增加资产类别」 | 点确认后**无提示 / 无新行 / 无库写入 / 控制台无 error**（四重静默） | `addI1SoeCategory` 返回 `{layers,key,seq}` **对象**被当数组用 → `maxI1SoeCustomSeq(next)` 里 `for...of` 抛 `TypeError: layers is not iterable`，再被组件裸 `catch { /* cancelled */ }` 吞掉 | `next.seq` / `next.layers`；catch 区分 `'cancel'`/`'close'` 与实现异常 |
  | I2 上市「删除费用性质」 | **整页「页面渲染出错」白屏**；且崩溃**打断 debounce 保存** ⇒ 刷新后刚新增的行整行丢失 | `useI2Disclosure` 写了 `removeNatureRow` 完整实现却**漏在 return 清单** ⇒ 组件解构到 `undefined` | 补进 return |

  顺带修两处：
  - I1 listed `addCategory` 的 `label.trim() || '其他'` —— 空名/纯空白**兜底成「其他」**，
    而「其他」是源模板固定类别 ⇒ 静默造重复列（label 是推附注与交叉核对的匹配键）；
    且无撞名检测。改为与 soe 版同构的「空名/撞名一律返回 false」
  - `autoFillFromSources` 声明返回 `{ok,message}` 但实际多返回 `unmatched`/`fuzzyMatched`
    ⇒ TS2353 且**消费方类型上拿不到未匹配清单**（只能从 message 读文本）。补全签名

  **浏览器复验（全通过）**
  - I1 soe：4 表同步 13 → **14**（新行带「删」）→ 删除后回 13；附注同步提示
    「已同步至附注 八、27（56 行 → 52 行）」= 14/13 × 4 层；撞名弹「类别「X」已存在，未新增」
  - 库层印证：`I1-soe-layers` 3460B（含 `碳排放权TEST` + `soe_custom_1`）→ 删后 3116B；
    🔴 **`I1-soe-cat-seq` 删后仍为 `1`**（单调计数器不回退，Property 23 在 composable 层成立）
  - I2 listed：6 → **7** 行（金额归零）→ 删除后回 6，`crashed: false`；
    归一化撞名实证 —— 输「 人 工 费 」（含内部空白）仍被判撞固定类别「人工费」；
    固定 6 类**无删除按钮**（UI 层已挡）；soe 项目下正确提示「当前不适用上市附注同步」

  **守卫（两个新文件，共 22 tests）**
  - `i1DisclosureAddCategory.spec.ts`（9 tests）：**补上缺失的 composable 层**
    —— `iCycleDynamicRows.spec.ts` 早已把 model 层测足且用法全对（`res!.layers` / `a.seq`），
    但 composable 层零测试，这正是假绿根因
  - `iCycleComposableExports.spec.ts`（9 tests）：**导出完整性**判据 ——
    从 SFC 源码抽 `= disc` / `= useXxx(...)` 的**真实解构键集合**（括号配对扫描 + `stripComments`），
    再真实调用 composable 取 return 键集合做包含断言 ⇒ 「新增解构却忘了导出」立刻打红，
    且不依赖手工维护键名表。含抽取器**反向自检**（注释里的解构不得被误当消费 / 真实 SFC 上零产出即判缺陷）
  - **变异检验双 RED**：
    ① 还原 `maxI1SoeCustomSeq(next as any)` → 4 failed / 5 passed，
       且复现出**精确异常字符串** `TypeError: layers is not iterable`（与浏览器推断一致）
    ② 从 return 删 `removeNatureRow` → 2 failed / 7 passed，
       断言消息精确点出缺失成员名；「国企版」正确**不红**（soe 变体不消费该成员）

  **🔴 工具链两条硬实证（改进建议的依据）**
  - `get_diagnostics` 对**类型不匹配漏报**（本轮两次：TS2345 × 2 / TS2353 × 1 全报
    「No diagnostics found」）；`tsc --noEmit` 精确报出行号，修完全量 **2059 → 2056**
  - `tsc` **不解析 `.vue`**（本仓 805 个 TS2307 即此因）⇒ 「SFC 解构 composable 未导出成员」
    这类**整页崩溃**它也检不出，只有 `vue-tsc` 或运行时守卫能拦
    ⇒ 故本轮把判据做成**运行时守卫**而非依赖类型检查

  #### 补测 4/5 ✅ 比率列反向边界（I1-10 摊销测算表实测）

  I1-1 审定表确实无比率/年限列（`el-input-number` 计数 0），已改到 I1-10 验。
  新增 1 行后填 原值 `1234567.5` / 残值 `50000` / 使用期限 `10` 年：

  | 类别 | 列 | 实际显示 | 判定 |
  |---|---|---|---|
  | 可编辑 `el-input-number` | 原值 | `1234567.50` | ❌ 金额**无千分符** |
  | 可编辑 `el-input-number` | 残值 | `50000.00` | ❌ 同上 |
  | 可编辑 `el-input-number` | 使用期限(年) | `1000.00` / `10.00` | ✓ 不带千分符（但 `:precision="2"` 让年限显示两位小数） |
  | 只读派生 `fmtAmount` | 期初净值F | `1,184,567.50` | ✓ |
  | 只读派生 `fmtAmount` | 月摊销额K | `9,871.40` | ✓ |
  | 只读非金额 | 摊销期限(月) / 剩余月数J | `120` / `120` | ✓ 正确不带 |

  - **公式三级派生全部正确**：F = 原值 − 残值、摊销月数 = 年 × 12、K = F ÷ 月数
  - 🔴 **实测到的真问题**：同一行内 `50000.00`（可编辑）与 `9,871.40`（只读）**并排显示两种格式**，
    比单纯没千分符更容易误读
  - **定性修正**：源码核实 I1-10（`I1TabAmortizationNoImpair.vue`）/ I1-11
    （`I1TabAmortizationWithImpair.vue`）用 `el-input-number` + `:precision="2"`、
    **并无 `:formatter`** ⇒ 不属于 memory 记的「40+ 处 `el-input-number :formatter` 空操作」名单，
    而是**可编辑金额列从未接入平台金额格式单一真源 `WpAmountInput`**
  - 🔴 **「比率/年限列不带千分符」这条是碰巧成立**：成因是 `el-input-number` 对所有列
    都不做千分符，而非正确区分了列类型 ⇒ 一旦按平台铁律换成 `WpAmountInput`，
    **必须同时显式排除年限/月数/比率列**，否则「使用期限 1000 年」会变成 `1,000.00`
  - 按 memory「存量 `el-input-number` 替换待单独 spec 收口」，本轮**不做替换**，如实登记；
    `使用期限(年)` 的 `:precision="2"`（显示 `10.00`）**未改** —— 源模板是否允许小数年限
    需业务确认，改 `:precision="0"` 会禁掉 2.5 年这类录入

  #### 补测 5/5 ✅ I5「本项目无此科目」显式提示（两个面板都修）

  补测 1/5 登记的遗留项在此收口。I5-1 实测发现**两个溯源面板都是空的**：

  | 面板 | 旧表现 | 根因 |
  |---|---|---|
  | `WpFourTableSourcePanel` | 整块 `v-if` 隐藏，**一片空白** | `visible = hasTbSourceCodes \|\| hasExtraSlotCodes`，而 absent 态四个码列表全空 |
  | `HiFourTableSourcePanel` | 只剩 Element Plus 默认英文 **「No Data」** + 一个点了没意义的「🔄 刷新取数」 | `segments` 为 `[]`（真源 `I_CYCLE_ACCOUNT_SPECS.I5.fallback` 为空，宁缺勿造） |

  **render-config 实测载荷（逐字）**
  ```json
  { "wp_code": "I5", "row_code": "BS-037", "row_name": "其他非流动资产",
    "formula": "TB('1911','期末余额')", "resolved_from": "fallback",
    "signed_codes": [["1911", 1]],
    "segments": [{ "segment": "cost", "standard": [], "original": [] }],
    "diagnostics": [{ "kind": "unclaimed", "code": "1911", "chart_name": "" }],
    "gross": [], "gross_standard": [], "provision": [], "provision_standard": [] }
  ```

  🔴 **判据设计上的两个坑**
  1. `resolved_from` 是 **`'fallback'` 而不是 `'none'`** —— 类型注释里 `'none'` 的存在
     很容易误导人只判它，那样会**漏掉这个真实形态**（变异检验第一条就打在这里）
  2. 「后端算过但本项目没这科目」与「后端根本没下发」必须分开：
     前者要显式说明（审计师需知道本该从哪个报表行取、为何没取到），后者才该隐藏

  **新增平台级纯函数**（`composables/shared/tbSourceCodes.ts`）
  - `isTbSourceAbsent(src)`：`src` 非空 + 四个码列表/所有 `segments`/所有 `slots` 全空
    + 有实质元信息（`row_code` / `formula` / `signed_codes`）⇒ true
  - `tbAbsentCodesText(src)`：取 `signed_codes` 标准码 ∪ `diagnostics[kind='unclaimed'].code`

  三态收敛为一张表：
  | 态 | 判据 | 界面 |
  |---|---|---|
  | 已取数 | `hasTbSourceCodes()` | 正常展示科目链路 |
  | **本项目无此科目** | `isTbSourceAbsent()` | 显式说明 + **仍给报表行与公式**（可追溯） |
  | 后端未下发 | `src == null` | 整块隐藏（保留「禁空洞卡片」口径） |

  **改动**
  - `WpFourTableSourcePanel`：`visible` 加 `|| isAbsent`；absent 态**不渲染**
    「原值 兜底科目」这类标签（一个码都没取到时说「兜底科目」会让人以为已按兜底码取了数）
    与「展开明细」按钮；新增 `el-alert` 给三条信息（报表行+行名 / 公式引用了哪些码 /
    「未取数（不是余额为 0）」+ 请勿填 0 + 下一步查科目表映射）
  - `HiFourTableSourcePanel`：`el-table` 加 `:empty-text`（中文说明为什么没有段，
    替掉英文「No Data」，对齐「UI 全中文化」）；`hasSegments` 为假时隐藏「🔄 刷新取数」

  **浏览器复验**
  - I5-1：`四表库取数口径 [报表行 BS-037] [本项目无此科目]` +
    「本项目科目表中没有其他非流动资产对应科目 —— 未取数（不是余额为 0）…公式引用 1911…
    请勿填 0」+ `报表公式：TB('1911','期末余额')`；Hi 面板「No Data」已消失、刷新按钮已隐藏
  - 🔴 **反向回归**：I1-1（有码）两个面板**完全正常** —— Hi 面板 3 段
    （1701/1702/1703）+「🔄 刷新取数」在位；Wp 面板「报表行 BS-032」「无形资产原值（1701）
    报表规则映射」「累计摊销（1702）+ 减值准备（1703） 兜底科目」+「展开明细」在位，
    且 `wpHasAbsentTag === false`（**没被误判成 absent**）

  **守卫** `composables/shared/__tests__/tbSourceAbsent.spec.ts`（25 tests）：
  含 I5-1 / I1-1 两份**实测真实载荷**逐字固化、8 种「任一层级有码即不算 absent」参数化、
  三种元信息任一存在即判 absent、`tbAbsentCodesText` 的 unclaimed 过滤、
  以及与面板 `visible` 同构的三态合成断言。
  **变异检验 = RED**：把判据换成「只判 `resolved_from === 'none'`」→ **6 failed / 19 passed**，
  首条精确打在 I5-1 真实载荷上。

  ### 🔴 本轮零回归结论（含一条方法论纠正）

  - **辐射面串行跑**（`Disclosure i1 i2 Adjudication Prefill tbSource SourcePanel ComposableExports`
    + `--no-file-parallelism`）：**230 files / 224 passed / 5 failed**
  - 5 个 failed **经实证与本轮改动无关**，是并发会话所致：
    | 失败 spec | 失败断言形态 | 归因证据 |
    |---|---|---|
    | `disclosureSharedTableRowScope` | 共享表清单 `{listed:24,soe:8}` vs 期望 `{listed:23,soe:6}`；受影响段数 18 vs 15 | 真源 `note_template_listed.json` / `note_template_soe.json` 均为 `M` 状态（**非本轮改动**） |
    | `disclosureColumnsCoverage` | flat 三态语义 / 路由登记 | 同上两个 JSON |
    | `disclosureAutoSyncCoverage` | MISSING_SYNC_PATH 清单 | **该 spec 文件自身是 `M`**（并发会话正在改这个守卫） |
    涉及的表全属其它循环（BS-063/021/064/027/050/009/029），与 I1(BS-032)/I2(BS-034) 无关
  - 🔴 **印证 memory 铁律**：这 3 个 spec 用的是**全局等值型判据**（「清单必须是 29 张」），
    多 spec 共享文件下必假红 —— 应改**归因型判据**（只断言落在本 spec 字节区间内的变动）
  - 🔴 **方法论纠正（我本轮犯的错）**：一度跑了**前端全量**（1999 files / 483s）得到
    「73 files failed」，虚惊一场 —— 抽样单独复跑（`useAiChat` / `useDashboardData` /
    `OnlyOfficeEditor` / `useProcedureTrimming`）只剩 **1 failed / 3 passed**，
    失败原因是 mock 的 `Error: HTTP 500`/`Network error`
    ⇒ **绝大多数是 4-worker 并发资源竞争的 flaky**（environment 耗时 811s > 总时长，
    同时还开着浏览器 + dev server + 后端）。唯一稳定红的 `OnlyOfficeEditor.spec.ts`
    也与本轮无关。**结论：memory「别跑全量、按引用关系反查辐射面」这条必须遵守，
    全量既慢又制造假红噪音**

  ### ℹ️ 实测环境说明（非待办）

  **并发会话干扰**：实测期间有并发进程重建该项目 `disclosure_notes`（首版全表基线 5 分钟内
  29 处漂移、11 处物理删除、一行 `updated_at` 从 8/14 回退到 7/27）⇒ 基线已收窄到
  I 循环 6 章节，复原半径 = 改动半径，避免误伤他人数据。
  本轮 4 次 `--restore` + `--diff` **全部「无漂移」**（每次实测写库后逐项复原，
  含 I1-1 的 7 键 / I1-soe 的 12 键 / I2 的 11 键 / I1-10 的 2 键）。

  ### ✅ 5 项补测全部完成 —— 净产出

  | # | 补测项 | 结果 |
  |---|---|---|
  | 1 | 另 5 个审定表溯源面板 | 4 通过 + I5-1 缺陷（→ 补测 5/5 修复） |
  | 2 | 「从四表库带入未审数」实点 | 抓出平台级缺陷（全 0 谎报「补填 18 格」并白写 18 个 0） |
  | 3 | 动态类别行增删改名 + I2 可扩行 | 抓出 2 个缺陷（四重静默 / **整页白屏**）+ 2 处顺带修 |
  | 4 | 比率列反向边界 | 判据修正：「不带千分符」是碰巧成立，换 `WpAmountInput` 时必须显式排除年限列 |
  | 5 | I5「本项目无此科目」提示 | 两个面板都修 + 新增平台级三态判据 |

  **共修 6 个缺陷**（3 个用户可见：整页白屏 / 四重静默 / 面板空白；
  3 个数据正确性：写 0 伪装成已核实、空名兜底造重复列、返回类型漏字段），
  **新增 4 个守卫文件 / 72 tests**，每个都做过变异检验且均为 RED：

  | 守卫 | tests | 变异 |
  |---|---|---|
  | `adjudicationPrefillZeroSkip.spec.ts` | 13 | 6 failed / 7 passed |
  | `i1DisclosureAddCategory.spec.ts` | 9 | 4 failed / 5 passed（复现 `layers is not iterable`） |
  | `iCycleComposableExports.spec.ts` | 9 | 2 failed / 7 passed（精确点出缺失成员名） |
  | `tbSourceAbsent.spec.ts` | 25 | 6 failed / 19 passed |

  ### 🔴 实测踩到的两个坑（已写进脚本注释）

  - **复原前必须先关浏览器页面**：第一次 restore 后 `--diff` 又冒出 15 行**新 id** ——
    页面还开着，前端 debounce 把数据又 PUT 回来了
  - **`_snapshot(db)` 后不能再 `async with db.begin()`**：查询已让 Session 隐式开启事务，
    再 begin 抛 `InvalidRequestError: A transaction is already begun`（复原一次都没执行）；
    改为末尾单次 `commit()` + 异常 `rollback()`，单事务语义不变

  <details><summary>原任务描述</summary>
  - chrome-devtools 隔离上下文（`new_page` 传 `isolatedContext`）；实测前抓基线（`parsed_data` 全文 + md5 + `jsonb_typeof` + `checklist_responses` 行数）
  - 逐项：六个审定表溯源面板渲染 + 「带入」出数 → I1 两版披露动态类别行增删改名 → I2 上市可扩行 → 「同步到附注」→ postgres 查 `disclosure_notes.table_data` 子表数/列元数据/`last_sync_at` 前移
  - 金额控件验：输 `1234567.5` → 显示 `1,234,567.50`；比率列不带千分符
  - 🔴 AC 8.6 在此兑现：推送后 `disclosure_notes.last_sync_at` 必须由 NULL/旧值**前移**，
    且 `sub_table_data` 的表数与本次推送表数一致（源码级核查做不到这条，只能运行态验）
  - 数据逐项复原（原子事务；JSONB 赋 dict 不赋 `json.dumps` 字符串）+ 独立只读查询交叉核实
  - 清 `backend/scripts/diagnose/_wip_i_*`（本 spec 自己的产物，不动他人的 `_wip_*`）
  </details>

  - _Requirements: 8.6, 11.6, 11.7_

---

## Notes

### 🔴🔴 立项后二次核实推翻的 4 处（2026-08-09，开工前必读，勿照初稿实现）

初稿 Wave 3/4 按「新建幂等脚本」写，实跑核实后**四个任务的性质全变**：

| 任务 | 初稿 | 实证 | 改判 |
|---|---|---|---|
| Task 7 | 新建 `fix_i_cycle_prefill_presets.py`，修 `审定表I1-1` | 脚本**已存在**（16501 字符 / git tracked）；`'审定表I1'` 命中 14 次；`--check` **rc=0 / 0 错误** | 已交付 → 改「核实 + 防回退」 |
| Task 8 | 修 I2 的 `TB('6602')` | 同脚本 `'6604'` 命中 **20** 次；`--check` 归零 | 已交付 → 改「核实 + 防回退」 |
| Task 10 | 新建 `fix_note_i_cycle_structure.py`，补 4 张表 columns | 脚本**已存在**（27981 字符 / 893 行）；`--check` **12 章节全部幂等空操作** | 已交付 → 改「核实 + 判定 DB/模板哪一层缺」 |
| Task 11 | 补三向比对守卫 | `test_note_i_cycle_structure.py` **108 passed / 4 failed**，失败全是 `_aligned_by` 跨 spec 假红 | 新增「修假红」为首要子项 |

**我在报告里看到的 `审定表I1-1` / `6602` 是脚本内作为「要修的错误形态」留证的常量**，不是残留缺陷；
`prefill_formula_mapping.json` 读到的旧值是**该文件被并发会话回退过**（memory 已记它是「D/G/H/K/L/N 多 spec 共享的回退高发文件」）。
⇒ **判「某任务是否真交付」必须实跑 `--check` + 守卫，不能只读数据文件当前值**（数据可能被回退，脚本才是意图真源）。

**Task 10 的一条新认识**：脚本 `--check` 归零 ≠ DB 里数据已对齐 —— 脚本对齐目标是**模板 JSON**，
而我实测的 `cols=0` 是**既有项目 `disclosure_notes` 的生成时快照**。两者是两层，
存量回填属 legacy 迁移域，不在本 spec（已在 Task 10 写明四步判定）。

### 🔴🔴 二次核实推翻的第 5 处：row_code 是 **11/12 错**不是 6/6（2026-08-09 磁盘 + 连库双证）

初稿只记了 soe 一半。磁盘实证 `I_CYCLE_ROW_CODES` 是 `dict[wp][entity]` 双键结构，
**listed 与 soe 各是一套不同的错值**：

| 循环 | 正确码 | 现状 listed | listed 实际行名 | 现状 soe | soe 实际行名 |
|---|---|---|---|---|---|
| I1 无形资产 | `BS-032` | `BS-033` | 开发支出（= I2 的正确码） | `BS-045` | 应付账款 |
| I2 开发支出 | `BS-033` | `BS-035` | 长期待摊费用（= I4 的正确码） | `BS-046` | 预收款项 |
| I3 商誉 | `BS-034` | `BS-037` | 其他非流动资产（= I5 的正确码） | `BS-047` | 合同负债 |
| I4 长期待摊 | `BS-035` | `BS-038` | 非流动资产合计（**ROW 派生行**） | `BS-048` | 应付职工薪酬 |
| I5 其他非流动 | `BS-037` | `BS-040` | 流动负债：（**节标题，formula NULL**） | `BS-050` | 其他应付款 |
| I6 研发费用 | `IS-006` | `IS-006` | ✅ 研发费用（**唯一正确**） | `IS-024` | 四、净利润 |

**listed 侧是「整体偏移一个循环」**（I1→I2 码、I2→I4 码、I3→I5 码），与 memory 已记的
「L 循环公式预设连续 5 个审定表整体偏移一个循环」同型；soe 侧则整段错到负债类。

**两处附带实证**：`IMP-016 十五、无形资产减值准备` 只有 `soe_standalone` 有公式
（`TB('1703')`，`soe_consolidated` 为 NULL、listed 两条**无该行**）；
`IMP-017 十六、商誉减值准备` 四准则 formula **全 NULL** ⇒ I3 减值段空兜底是正确的。

**`BS-038`/`BS-040` 这两个现状值最危险** —— 前者是 `ROW()` 派生行（`extract_signed_codes`
抽不出 `TB()` ⇒ codes 空 ⇒ 静默退兜底）、后者 formula 为 NULL（同样静默退兜底），
两者都属 memory 已记的「错 row_code + 取不出码 = 稳定的假正确」，一旦别人把它们
"顺手改成有公式的邻近行"就会立刻暴雷。

### 已实证事实（开工前必读，勿重复调查）

**取数层**
- `report_config` 实测：`BS-032 无形资产=TB('1701')-TB('1702')` / `BS-033 开发支出=TB('1704')` / `BS-034 商誉=TB('1711')` / `BS-035 长期待摊费用=TB('1801')` / `BS-037 其他非流动资产=TB('1911')` / `IS-006 研发费用=TB('6604','本期发生额')`，**四准则全部同码同名同公式**
- 现状错值逐条见上表（11/12 错，仅 `I6.listed` 正确）
- 🔴🔴 **`test_i_cycle_accounts.py::TestResolveRowCode` 的 12 个参数化用例正逐条断言这 11 个错值**
  ⇒ 守卫在保护错的那一侧，这是错码能长期存活且「测试全绿」的直接原因（归 Task 4b 诚实改写）
- A/B 对照（8 项目 × 6 循环）：**实质差异 0 处**，仅 `resolved_from` 变化 34 处（`fallback`→`report_config`）
- `parent_check.diff` 真实库全部 0.0（叶子聚合已正确，父子双算已解决）
- `1911` 全库两张科目表都不存在 ⇒ I5 恒 `found=False` 是**正确行为**（宁缺勿造）
- I1/I4 有真实数据（`2aa00f57`：无形资产原值 10,890,130.24 / 累计摊销 6,052,945.16 / 长期待摊 6,047,002.84）；I2/I3/I6 恒空是数据事实
- 灰度开关 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 已为 **True**

**源模板（`backend/wp_templates/I/`，运行时权威）**
- 披露 sheet 名两种写法并存且**都是源模板事实**：I1 = `附注披露信息（上市公司）`/`（国有企业）`；I2~I6 = `附注披露（上市公司）`/`（国有企业）`（无「信息」二字）。六份全部全角括号 + 「国有企业」
- I1 审定表 tab 名 = **`审定表I1`（缺 `-1`）**，其余 I2~I6 均为 `审定表IX-1`
- 索引号不在 tab 名尾部 2 处：`摊销测算表（不含减值）I1-10（剩余年限法）`、`摊销测算表I4-7（工作量法）`
- 动态标记：I1 上市 3 处 / I1 国企 4 处 / I2 上市 1 处 / I3~I6 各 **0** 处
- I1 类别真源 = `底稿目录!A9:A19`（土地使用权/住房使用权/专利权/非专利技术/商标权/著作权/特许经营权/软件/矿产权/数据资源/其他，12 行）+ `A20` = `……`
- I4 类别真源 = `底稿目录!A9:A12`（类别A/B/C + `……`）
- I3 有 2 张 hidden：`市场平均收益率2017` + `GT_Custom`；另有 **visible** 的 `参考－商誉减值测试示例`（会进渲染面）
- I6 sheet 顺序异常：两张披露 sheet 排在 `审定表I6-1` **之前**
- I6 目录第 7~14 项索引号指向 **I2** 底稿（`D10=I2-4`…`D17=I2-11`），`E10` 有原文说明 ⇒ **有意跨 workbook 引用非笔误**

**预设**
- I 类共 16 块；`审定表I1-1` 在源模板不存在（唯一 sheet 名错）
- I2 明细表块 `'研发费用_期末' <- TB('6602','期末余额')` —— `6602` 是管理费用（归 K9），研发费用是 `6604`；同块 `account_codes=['1704','5301']` 与公式自相矛盾
- 覆盖面：I1 4/18、I2 3/21、I3 2/15、I4 4/12、I5 1/9、I6 2/11；**12 张披露 sheet 零预设**
- I5 只有一个 `PREV` 块且 `account_codes=[]`

**附注**
- 落点全部存在：listed `五、26/27/28/29/31/66`、soe `八、27/28/29/30/32/67`
- `cols=0` 4 张：listed `五、26` 的 `无形资产情况`(38 行)·`确认为无形资产的数据资源`(27 行)、soe `八、27` 的 `确认为无形资产的数据资源`、listed `五、28` 的 `商誉减值测试关键假设`
- 段落泄漏成表名 2 处：listed `五、31` / soe `八、32` 的 `[披露与合同取得成本有关的资产…例如：`
- 六份 `iXNoteSectionMap.ts` 齐全，披露 sheet 名与源模板逐字一致

### 边界（不做）

- **不改 `report_config`**（其 `BS-037=TB('1911')` 指向全库不存在的码是既有状态，本 spec 只诊断进 `chart_conflict`）
- **不改 `backend/wp_templates/I/**` 任何 xlsx**（源模板只读）
- **不动共享件语义**（`leaf_aggregation` / `report_line_accounts` / `_note_structure_kit` / `adjudicationPrefillPlan` 只调用不改）
- 不做 I3 DCF 引擎与商誉减值测试逻辑（归已归档的 `i3-goodwill` spec）
- 不做 I2 研发项目资本化时点判断逻辑（归 `i2-development-expenditure`）
- 不清理他人的 `_wip_*` 临时产物

### 与并发 spec 的边界

- `e-cycle-…`（17/24 在跑）：无文件重叠；但两者都可能碰 `prefill_formula_mapping.json` ⇒ **本 spec 的幂等脚本必须带 round-trip 自检**，且 Wave 3 落地前先 `--check` 一次确认对方未留欠账
- `note-template-columns-…`（已归档 23/23）：其 `columns` 补齐成果覆盖 I 类部分表（listed `五、26`/`五、28`/`五、66` 与 soe `八、27` 的 `_aligned_by` 标记为它）⇒ 本 spec 补的 4 张是它**未覆盖**的缺口，不得反改它已补的表
- `g7-column-alignment-…`（3/24 在跑）：同样在治「seed ↔ 运行时列对齐」，判据可参考但**不共用文件**

### 已知风险

- Task 4 改 row_code 后 `resolved_from` 转 `report_config`，若某项目客户科目表用非标准码，报表行解析路径首次真正生效 —— A/B 对照已覆盖当前 8 个项目，但新项目仍需靠 `parent_check` + 溯源面板兜住
- Task 5 删文件前必须确认零消费方（`I_CYCLE_SPECS` 实测只被自己引用，但 `I_PL_CYCLES`/`I_PL_POSITIVE_SIDE` 需单独 grep）
- Task 10 改 `note_template_*.json` 是回退高发文件（多 spec 共享）⇒ 幂等脚本 + `--check` 是唯一可靠恢复手段
