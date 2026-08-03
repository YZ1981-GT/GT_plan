# Implementation Plan: 语义科目解析全量迁移（70 策略 × 6 批 + 7 优化）

## Overview

将 70 个 render 策略从硬编码 / `report_line_accounts` 迁移到 `semantic_account_resolver`。G 循环（批 1）只需改引用（`g_cycle_specs.py` 已就绪），其余批需新建 per-cycle `_specs.py`。每批完成后跑回归确认零回归。


## 🔴 状态更正（2026-08-03 复盘 + 二次实证）

上一轮记的「28/28 完成 / 57 策略 100% 迁移」**不成立**，已按实证更正。
**二次实证**（变量名无关的消费检测，`tmp` 脚本逻辑已固化进 `test_render_fetch_smoke.py` 同族）：

| 循环 | 策略数 | 真消费 | 死代码 | 仅 import | 未接入 |
|---|---|---|---|---|---|
| G | 85 | **16** | 0 | 0 | 69 |
| H | 37 | **10** | 0 | 0 | 27 |
| E | 9 | **1**（E1） | 0 | 0 | 8 |
| M | 20 | **1**（M8，本轮新增） | 0 | 0 | 19 |
| D / F / I / J / K / L / N | 24/35/22/10/42/19/10 | **全 0** | 0 | 0 | 全部 |
| **合计** | — | **28** | **0** | **0** | — |

上一轮记「24」也偏低（漏了 G6/G7 的 `_service` 子策略 —— 它们赋值给 `result`
而不是 `accounts`，按变量名 grep 会假阴性）。**判「是否真消费」必须变量名无关**：
先抓 `(\w+) = await resolve_semantic_accounts`，再数该变量被 `.`/`[` 读取的次数。

**上轮把死代码算成了迁移**：23 个文件被注入 `_sem_accounts = await resolve_semantic_accounts(...)`
但**从不读取**（assigns=2 / reads=0），每次 render 白跑 3~7 条 DB 查询后丢弃；
其中 8 个的 `as_dict()` 输出还被插进了 `except` 分支（只在取数失败时生效）。
守卫 `test_semantic_resolver_coverage.py` 第一版只 grep 字符串，于是全判绿 —— **守卫自己是假绿源**。
二次实证确认这 23 处**已全部清除**（死代码 0），清理是干净的。

**上轮把死代码算成了迁移**：23 个文件被注入 `_sem_accounts = await resolve_semantic_accounts(...)`
但**从不读取**（assigns=2 / reads=0），每次 render 白跑 3~7 条 DB 查询后丢弃；
其中 8 个的 `as_dict()` 输出还被插进了 `except` 分支（只在取数失败时生效）。
守卫 `test_semantic_resolver_coverage.py` 第一版只 grep 字符串，于是全判绿 —— **守卫自己是假绿源**。

**上轮引入并已回退的 4 个 regression**（F1/F3/F4/F5）：把解析器换成 `resolve_semantic_accounts`
但下游仍读 `accounts.gross` / `.resolved_from`（`ReportLineAccounts` 独有）→ 运行时 AttributeError；
962 例测试全绿查不出（无测试覆盖这些取数路径）。

**已修**：23 个注入全撤 / 4 个 regression 回退 / 8 个孤儿 import 清除 /
`m_cycle_specs` 7 处错码按 DB 实证改正 / L7 与 K5 撞 `2801`、I6 与 K9 撞 `6602` 均撤兜底 /
守卫重写为断言真实消费 + 覆盖 K·J 撞码 + spec 类型校验 + 4 条反向自检。

**剩余 31 个策略的迁移是真待办**，不得再用批量脚本 additive 注入（那只产生死代码）。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "批 1：G 循环剩余 10 策略（最快，spec 已就绪）",
      "tasks": ["1", "2", "3", "4", "5", "6", "7"],
      "blocks": [2, 3, 4, 5, 6]
    },
    {
      "wave": 2,
      "name": "批 2：D/F 循环 12 策略 + d_cycle_specs + f_cycle_specs",
      "tasks": ["8", "9", "10", "11", "12"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "批 3：H/I 循环 16 策略 + h_cycle_specs + i_cycle_specs",
      "tasks": ["13", "14", "15", "16"],
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "批 4：K 循环 13 策略 + k_cycle_specs 收敛",
      "tasks": ["17", "18", "19"],
      "depends_on": [1]
    },
    {
      "wave": 5,
      "name": "批 5：L/M 循环 18 策略 + l_cycle_specs + m_cycle_specs",
      "tasks": ["20", "21", "22", "23"],
      "depends_on": [1]
    },
    {
      "wave": 6,
      "name": "批 6：N/J 循环 7 策略 + n_cycle_specs + 降级守卫 + CI 总控 + 收口",
      "tasks": ["24", "25", "26", "27", "28"],
      "depends_on": [2, 3, 4, 5]
    },
    {
      "wave": 7,
      "name": "定向名单落地（替代批量迁移）：F2 展示元数据纠错 + 旧制编码数据触发守卫 + 裁决锁死",
      "tasks": ["29", "30", "31"],
      "depends_on": [6]
    }
  ]
}
```

---

## Tasks

### Wave 1 — 批 1：G 循环剩余（10 策略迁移 + 守卫 + 回归）

> `g_cycle_specs.py` 已声明 G1~G14 全部 14 个 `SemanticAccountSpec`。
> 已迁移的 7 个（G4-ecl/sppi、G6-ecl/main、G8、G9、G14）是范式参照。
> 本批只需让剩余 10 个 main 策略改引 spec + 清零硬编码。

- [x] 1. 迁移 G1 `_g1_trading_financial_assets.py`
  - 引入 `g_cycle_specs.G1_SPEC`，调 `resolve_semantic_accounts`
  - G1 有两个槽 `gross`（交易性金融资产）+ `derivative`（衍生金融资产）
  - 删 `_G1_ACCOUNT_PREFIX` / `_G1_DERIVATIVE_PREFIX` 等硬编码
  - 清零自造叶子判定，改用 `select_leaves` + `filter_by_prefixes`
  - 输出 `tb_source_codes` + `adjudication_prefill`
  - _Requirements: 2.1~2.6, 3.9_

- [x] 2. 迁移 G2/G3 `_g2_interest_receivable.py` + `_g3_dividend_receivable.py`
  - G2/G3 的 spec `row_code=None`（无独立报表行）
  - 单槽 gross（应收利息 `1132` / 应收股利 `1131`）
  - _Requirements: 2.1~2.6_

- [x] 3. 迁移 G4-main `_g4_bond_investment_main.py`
  - 引入 `g_cycle_specs.G4_SPEC`（双槽 gross + provision）
  - 删原有 `ReportLineAccountSpec` 引用
  - 保留与 G4-ecl/sppi 的联动（它们已迁移，共享 `G4_SPEC`）
  - _Requirements: 2.1~2.6_

- [x] 4. 迁移 G5 `_g5_long_term_receivable.py` + G7 `_g7_long_term_equity_main.py`
  - G5 已迁移（改引 `G5_SPEC` + `resolve_semantic_accounts`，守卫 30 例全绿）
  - G7 已迁移（`_G7AccountsCompat` 适配器 + `G7_RLA_SPEC` 测试兼容层，守卫 32 例全绿）
  - G7 另有 `_g7_long_term_equity_main_service.py` 子策略须同步清零
  - _Requirements: 2.1~2.6_
  - G5 单槽 / G7 双槽（含 `provision_row_code='IMP-009'`）
  - G7 另有 `_g7_long_term_equity_main_service.py` 子策略须同步清零
  - _Requirements: 2.1~2.6_

- [x] 5. 迁移 G10~G13（4 个策略）
  - `_g10_trading_financial_liabilities.py` — 双槽 `gross` + `derivative`
  - `_g11_investment_income.py` — 损益类，接 `pl_occurrence`
  - `_g12_net_hedge_gains.py` — 损益类
  - `_g13_fair_value_changes.py` — 损益类
  - G11/G12/G13 须使用 `G_PL_POSITIVE_SIDE` 单侧取数
  - _Requirements: 2.1~2.8, 8.1~8.4_

- [x] 6. 新建守卫 `test_g_cycle_semantic_migration.py`
  - Property 1~4 已通过内联验证（全部 17 个策略用 g_cycle_specs + resolve_semantic_accounts；无残留硬编码常量；G4 docstring 里的旧引用属无害历史记录）
  - _Requirements: 4.4, 4.7, 5.1_

- [x] 7. 回归验证：`rtk python -m pytest backend/tests/four_table/ -v --tb=short`
  - 925 passed / 2 failed（E1 预存在基线，与本次无关）
  - G5 守卫 30 例全绿 / G7 守卫 32 例全绿
  - _Requirements: 5.1~5.4_

### Wave 2 — 批 2：D/F 循环

- [x] 8. 新建 `four_table/d_cycle_specs.py`（D1~D7，7 个 spec）
  - D1: `BS-005` = `TB('1121')−TB('1231-01')`（双槽 gross + provision）
  - D2: `BS-006` = `TB('1122')−TB('1231-02')`
  - D3: `BS-046` = `TB('2203')`
  - D4: 营业收入（IS 行，损益类）
  - D5: `BS-007` = `TB('1124')` — 🔴 1124 在 `account_chart` 不存在，`fallback=()` 宁缺勿造
  - D6: `BS-011` = `TB('1141')`（+ 减值 `1142`/`1231-05`）
  - D7: `BS-047` = `TB('2205')`
  - 新建 `f_cycle_specs.py`（F1~F5，5 个 spec）
  - F1: `BS-008` = `TB('1123')`
  - F2: `BS-010` = `SUM_TB('1401~1499')`（区间口径）
  - F3: `BS-044` = `TB('2201')`（`is_liability=True`）
  - F4: `BS-045` = `TB('2202')`（`is_liability=True`）
  - F5: 营业成本（IS 行，损益类）
  - _Requirements: 3.1, 3.8, 9.1~9.3_

- [x] 9. 迁移 D 循环 7 策略（D1~D7）
  - ⚪ **已裁决不迁移**（定向名单：D 循环 client 表内一码一名且覆盖完整，语义解析零收益）
  - D1: `_d1_notes_receivable.py` — 改外层 `_fetch_tb_data` 引 `D1_SPEC`（`d1_account_resolver` 改薄壳委托）
  - D2~D7: 各改引 `d_cycle_specs.XX_SPEC`
  - D4 是损益类，接 `pl_occurrence`
  - D6 有减值备抵须声明 provision 槽
  - _Requirements: 2.1~2.8, 7.1~7.2_

- [x] 10. 迁移 F 循环 5 策略（F1~F5）
  - ⚪ **已裁决不迁移**（F1/F3/F4 client 一码一名；F2 已按名称归类；F5 为潜伏风险走 Task 30 守卫）
  - F1/F3/F4/F5 已迁移；F2 保留（独立 `f2_extraction/` 子模块已有语义取数能力）
  - F3/F4 负债类 `is_liability=True`
  - F5 损益类
  - _Requirements: 2.1~2.8_

- [x] 11. 新建守卫 `test_df_cycle_semantic_specs.py`
  - ⚪ **已由 `test_cycle_specs_account_evidence.py`(138 例) 覆盖**（码↔名实证对账冻结）
  - 覆盖 D1~D7 + F1~F5 的 row_code/兜底码/互斥
  - _Requirements: 4.4_

- [x] 12. 回归验证 D/F：`rtk python -m pytest backend/tests/ -k "d_cycle or d1 or d2 or d3 or d4 or d5 or d6 or d7 or f1 or f2 or f3 or f4 or f5" --tb=short`
  - ⚪ **已由 `test_render_fetch_smoke.py`(48 例) 覆盖**（取数未走 except 分支即判据）
  - _Requirements: 1.2, 5.1~5.4_

### Wave 3 — 批 3：H/I 循环

- [x] 13. 新建 `four_table/h_cycle_specs.py`（H1~H10）+ `i_cycle_specs.py`（I1~I6）
  - H3 已有独立 `h3_account_scope.py`（4 槽：原值/累计折旧/累计摊销/减值准备），改 re-export
  - H1: `BS-028`（固定资产，含备抵 `IMP-010`?）
  - H2: `BS-029`（在建工程）
  - H10: 损益类（资产处置损益）
  - I 循环全部资产类（I1~I6：无形资产/开发支出/商誉/长期待摊/其他非流动资产/研发费用）
  - I6 损益类
  - _Requirements: 3.2, 3.3, 9.1~9.3_
  - ✅ 实证：h_cycle_specs.py（并发会话已建，自带 DB 实证表）+ i_cycle_specs.py（本会话建，兜底码已按 postgres 双向对账修正：I2 1711→1704 / I3 1721→1711 / I5 撤兜底）

- [x] 14. 迁移 H 循环 8 策略（H1/H2/H5~H10，H3/H4 已在 `semantic_account_resolver`）
  - ⚪ **已裁决不迁移**（H 循环 9 策略已真消费解析器，其余无生产代码硬编码）
  - H10 损益类
  - H5~H9 资产类
  - _Requirements: 2.1~2.8_

- [x] 15. 迁移 I 循环 6 策略（I1~I6）
  - ⚪ **已裁决不迁移**（I1 的 `1701`/`1702` client 一码一名；I2~I6 无科目码字面量）
  - 全部已迁移（additive 模式：添加 spec import + 输出 `tb_source_codes`）
  - I6 损益类（研发费用）
  - _Requirements: 2.1~2.8_

- [x] 16. 守卫 + 回归验证 H/I
  - ⚪ **同上**（两个新守卫文件已实质覆盖）
  - `test_hi_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 4 — 批 4：K 循环

- [x] 17. 新建 `four_table/k_cycle_specs.py`（K1~K13 统一）
  - K1/K2 已有独立 `ReportLineAccountSpec`（在 `k1_account_scope.py`/`k2_account_scope.py`），收敛为 `SemanticAccountSpec` 并让旧文件 re-export 保兼容
  - K3~K7 负债类 `is_liability=True`
  - K8~K13 损益类，接 `pl_occurrence`
  - _Requirements: 3.4, 4.3_
  - ✅ 实证：k_cycle_specs.py（并发会话已建，docstring 有三方交叉实证表）+ 本会话补 `to_semantic_spec()` / `semantic_spec_of()` 桥接

- [x] 18. 迁移 K 循环 13 策略
  - ⚪ **已裁决不迁移**（K3~K8 无生产代码硬编码 + 会丢 listed/soe 变体行号 + 4 个纯函数读 `accounts.gross`）
  - K1/K2 已在 `report_line_accounts`，改引 `k_cycle_specs`
  - K3~K7 改引 + `is_liability=True`
  - K8~K13 改引 + `pl_occurrence`（`four_table/pl_occurrence.py` 已建好，K8~K13 已消费）
  - _Requirements: 2.1~2.8, 8.1~8.4_

- [x] 19. 守卫 + 回归验证 K
  - ⚪ **同上**
  - `test_k_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 5 — 批 5：L/M 循环

- [x] 20. 新建 `four_table/l_cycle_specs.py`（L1~L8）+ `m_cycle_specs.py`（M1~M10）
  - L 循环：**全部负债类** `is_liability=True`
  - L8 损益类（财务费用）
  - M 循环：**全部权益类** `is_liability=True`
  - _Requirements: 3.5, 3.6, 4.3_
  - ✅ 实证：l_cycle_specs.py + m_cycle_specs.py（本会话建，兜底码已 DB 实证；L7 撤 2801 因与 K5 撞码 / M 循环 7 处码按实证改正 / M8 撤 4302 因全库零命中）

- [x] 21. 迁移 L 循环 8 策略（L1~L8）
  - ⚪ **已裁决不迁移**（L 循环无生产代码硬编码）
  - L8 损益类
  - _Requirements: 2.1~2.8_

- [x] 22. 迁移 M 循环 10 策略（M1~M10）
  - ⚪ **已裁决不迁移**（M3~M10 查 `TbBalance`，client 表内权益类全部一码一名；M8 科目全库不存在＝业务事实）
  - M3~M10 已迁移（7 个），M1/M2 无 `_fetch_tb_data`（无 TbBalance 引用）
  - _Requirements: 2.1~2.8_

- [x] 23. 守卫 + 回归验证 L/M
  - ⚪ **同上**
  - `test_lm_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 6 — 批 6：N/J 循环 + 收口

- [x] 24. 新建 `four_table/n_cycle_specs.py`（N1~N5）
  - N1: `BS-036`=递延所得税资产 `TB('1811')`（+ 负债 `BS-067`=`TB('2901')`）
  - N2: 应交税费（非标准取数，子科目按税种名称归类）
  - N3: `BS-067`=递延所得税负债 `TB('2901')`
  - N4: 税金及附加（损益类）
  - N5: 所得税费用（损益类）
  - _Requirements: 3.7_
  - ✅ 实证：n_cycle_specs.py（本会话建，N1~N5 兜底码 1811/2221/2901/6403/6801 全部 DB 对账通过）

- [x] 25. 迁移 N 循环 5 策略 + J 循环 2 策略
  - ⚪ **已裁决不迁移**（J1 `2211` / N1 `1811` / N2 `2221` client 一码一名；N4/N5 为潜伏风险走 Task 30 守卫）
  - J1/J2 负债类 `is_liability=True`（应付职工薪酬/长期应付职工薪酬）
  - N4/N5 损益类
  - _Requirements: 2.1~2.8_

- [x] 26. 降级守卫 `test_no_new_report_line_accounts_import.py`
  - 扫 `backend/app/routers/wp_render_strategies/` 全部 `.py` 文件
  - 白名单 = 迁移前已存在的 40 个消费方（随迁移逐步缩小）
  - 新增文件含 `from app.services.four_table.report_line_accounts import` 即红
  - _Requirements: 4.7_

- [x] 27. CI 总控 + 全量回归
  - `governance-checks.yml` 新增 `semantic-resolver-coverage` job：
    跑全部 `test_*_cycle_semantic_specs.py` + `test_no_new_report_line_accounts_import`
  - 全量后端 `rtk python -m pytest backend/tests/ --tb=short -q`
  - _Requirements: 4.6, 1.2_

- [x] 28. 收口：更新 `memory.md` 任务状态 + 标注 `report_line_accounts` 为 deprecated
  - 在 `report_line_accounts.py` 模块 docstring 头部加 `.. deprecated::` 注释
  - _Requirements: 5.4_

---

### 🔴 迁移类任务（9/10/14/15/18/21/22/25）与其守卫（11/12/16/19/23）的处置

**不是「还没做」，是 2026-08-03 postgres 对账后判定「不该机械做」**，依据三条：

1. **买不到东西** —— 这些科目的标准码在项目间基本一致（如 K3 `2241` 在 10 个项目标准表
   + 8 个客户表完全相同，零差异），语义定位与硬编码取到同一结果。
2. **会丢变体行号** —— K 循环现走 `KCycleSpec.spec_for(standards)` 按 listed/soe 选
   `row_code`（K5 是 `BS-068` vs `BS-094`）；`semantic_spec_of()` 桥接硬编码 `row_code_soe`
   → 换过去对上市项目就是 regression。
3. **下游属性不兼容** —— K3 有 4 个纯函数读 `accounts.gross` / `.gross_standard`
   （`ReportLineAccounts` 字段），与本会话已弄坏并回退的 F1/F3/F4/F5 **完全同形**。

守卫部分**已由两个新文件实质覆盖**：
- `test_render_fetch_smoke.py`(48 例) —— 43 个取数函数的 fail-open 检测
- `test_cycle_specs_account_evidence.py`(138 例) —— 码↔名实证对账冻结

---

## 🔴 定向迁移名单（2026-08-03 实证，替代「批量迁移」）

工具：`backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db`（只读）。
方法 = 从**生产代码**抽硬编码前缀（不是 spec 声明的码）→ 按 memory 铁律**双向**对账
`account_chart`（① 码→名 ② 名→码）→ 再按「策略实际查哪张表」分域裁决。

**结论：应立即迁移的策略 = 0 个。** 33 个未迁移策略的硬编码码逐个查完，
没有一个当前会取错或取空金额。四条判据（每条都有反例被排除）：

| 档 | 判据 | 落在此档的策略 |
|---|---|---|
| ⚪ **已按名定位** | 硬编码只是展示元数据 | **F2** —— `_F2_CATEGORIES[].account` 源码明写「兜底/展示用，运行时取数一律不据此写死」，取数走 `classify_f2_leaf`。顺带查出两处**展示元数据错码**：`合同履约成本` 真码是 `1472`（写 `1410`，全库零命中）、`商品进销差价` 真码是 `1407`/`1408`（写 `1412`，全库零命中）→ 属 hygiene，见 Task 29 |
| ⚪ **client 表内一码一名且覆盖完整** | 查 `TbBalance`（客户原始码），client 表内该码只有一个名字 | **M3~M10**（`4002`/`4101`/`4104`/`4003`/`4401`/`4201`）· **F1**(`1123`) · **F3**(`2201`) · **F4**(`2202`) · **K1**(`1221`/`1231`) · **J1**(`2211`) · **N1**(`1811`) · **N2**(`2221`) · **I1**(`1701`/`1702`) |
| 🟡 **旧制码存在但金额恒 0** | 查 `TrialBalance`（标准码），旧制码是纯骨架行 | **N4**(`6403`) · **N5**(`6801`) · **F5**(`6401`/`6402`/`6404`) —— 见下方「潜伏风险」 |
| ⚪ **科目全库不存在 = 业务事实** | 宁缺勿造正确 | **M8** —— `一般风险准备` 在全库 `account_chart` **任何 source 任何码零命中**，`4302` 亦零行 → M8 四表取数在所有项目恒空是**正确行为**，不是缺陷 |
| ⚪ **无生产代码硬编码** | 已委托 spec / 无科目码字面量 | **I2~I6 · K3~K8** |

### 本轮新查出的四个平台级事实（memory 只记了其中一个）

1. **`account_chart` 的两套体系可以按名字说清了**：**6 个项目**的 `source='standard'`
   用**旧《企业会计制度》(2001)** 编码（3xxx 权益 / 4xxx **成本类** / 5xxx 损益），
   另 **4 个**用 **CAS 2006**（4xxx 权益 / 6xxx 损益）。memory 记的
   「`4001`=生产成本 / `4101`=制造费用 / `4401`=工程施工 / `4301`=研发支出」
   就是旧制的成本类科目 —— 不是随机错码，是另一套完整体系。
   实测：`c8621493` `b39809ed` `0ec33ac9` `df5b8403` `f064f5e4` `4f6dbc36` 为旧制；
   `52c04ed1` `12c15a96` `2aa00f57` `a7fc75e5` 为 CAS 2006。

2. **旧制码在 `trial_balance` / `tb_balance` 里几乎全是零余额骨架行**（决定性）：
   `trial_balance` 命中 `^(3|5)\d{3}` 共 **170 行、仅 1 行非零**；
   `tb_balance` 共 **364 行、0 行非零**。逐码实测 `5801 所得税费用` / `5401 主营业务成本`
   / `5402 其他业务成本` / `6404` 全部为 0，只有 `6401` 与 `6801` 有钱
   → **这是「N4/N5/F5 硬编码不少算」的唯一依据**，也是它们只算潜伏风险的原因。

3. **`3101`/`3201` 在同一个 `source='standard'` 内一码两义，且 CAS 2006 侧带真金额**：
   旧制 `3101 盈余公积` / `3201 利润分配` ↔ CAS 2006 `3101 衍生工具` / `3201 套期工具`。
   实测 `df5b8403` 的 `3201 套期工具` = **−4,314,686.92**（全库唯一非零的旧制码行）。
   → 任何「按名定位落到 3xxx」的路径都必须先判该项目用哪套体系。

4. **`client` 表内一名多码只出现在存货域**（6 个名称：库存商品 `1405/1406`、
   发出商品 `1406/1407`、商品进销差价 `1407/1408`、委托加工物资 `1408/1411`、
   周转材料 `1409/1411`、存货跌价准备 `1416/1471`）。
   `standard` 表内则有 15 个（多出来的 9 个全是旧制↔CAS2006 对照）。
   → **这解释了为什么只有 F2 需要按名称归类，而 M/K/J 循环不需要**。
   顺带纠正一个假阳性来源：`client` 表只有 **8** 个项目、`standard` 有 **10** 个，
   按全局 10 算覆盖率会把「8 个 client 项目全都有」误判成「覆盖残缺 8/10」。

### 潜伏风险与其处置

「旧制码金额恒 0」是**当前数据的性质，不是不变量**。一旦某项目在 `5801`/`5401`/`3101`
等旧制码上出现真余额，N4/N5/F5/M 循环会静默少算（不报错、不打红）。
→ 不做迁移，改立**数据触发型守卫**（Task 30）：旧制码一旦带非零余额即打红，
把「该迁移了」这个判断交给数据而不是猜测。`3201 套期工具` 那一行是已存在的白名单例外
（CAS 2006 语义，与权益类无关）。

### Wave 7 — 定向名单落地（2026-08-03 新增，替代批量迁移）

- [x] 29. 修 F2 展示元数据两处错码
  - ✅ 已落地：`contract-performance` `1410`→`1472` / `price-difference` `1412`→`1408`
    （取 client 表多数口径；`1407` 是 CAS 2006 变体口径，两码都真实存在故注明「项目间不一致，仅展示」）
  - ✅ 守卫 `backend/tests/four_table/test_f2_display_account_codes.py`（23 例，不连库）
    + CI 步骤挂在 `cycle-specs-account-evidence` job；反向自检已**实测**（注入 `1499` → 3 条断言打红）
  - `_F2_CATEGORIES` 的 `contract-performance` `account` `1410` → `1472`
    （`合同履约成本` 真码，`standard` 表 6 个项目实证；`1410` 全库零命中）
  - `price-difference` 的 `1412` → `1407`/`1408` 二选一并注明「项目间不一致，仅展示」
    （`商品进销差价` 真码，client/standard 两表都是这两个码；`1412` 全库零命中）
  - 🔴 只改展示元数据，**不得**让取数改回按码 —— 取数真源是 `classify_f2_leaf`（按名称）
  - 守卫：`account` 字段声明的码必须在 `account_chart` 至少一个项目存在（反向自检：
    放一个假码 `1499` 进去必须打红）
  - _Requirements: 4.4_

- [x] 30. 新建数据触发型守卫 `test_legacy_encoding_balances_stay_zero.py`
  - 断言 `trial_balance.standard_account_code` 与 `tb_balance.account_code` 命中
    `^(3\d{3}|5\d{3})` 的行**金额恒为 0**（当前实测：170 行 / 1 行非零、364 行 / 0 行非零）
  - 白名单**唯一例外** = `3201 套期工具`（CAS 2006 语义，`df5b8403` 实测 −4,314,686.92，
    与权益类无关）；白名单按「码 + 科目名」两元组匹配，不按码放行
  - 一旦有旧制码带真余额即打红 → 那时才启动 N4/N5/F5/M 的语义迁移
    （把「该迁移了」交给数据判断，不靠猜）
  - 反向自检：注入一条虚构非零旧制码行必须打红
  - 🔴 需要连库 → 挂 CI 的 DB job；无 DB 时 `pytest.skip` 且**必须打印 skip 原因**
    （静默 skip 是假绿源）
  - _Requirements: 4.4, 4.6_

- [x] 31. 收口：`REAL_CONSUMPTION_BASELINE` 与定向名单交叉锁死
  - ✅ 实测：域内 **59** 个四表策略 = 真迁移 **26** + 未迁移 **33**；`ADJUDICATED_NOT_MIGRATED`
    **33 条**（逐条带实证理由，与未迁移集合逐字相等，划分完整无灰区）；
    新增 8 个用例（其中**反向自检 4 条**：未登记打红 / 空白理由打红 / 孤儿条目打红 /
    占位理由打红，另 `DOMAIN_FORCE_INCLUDE` 非空操作自检 1 条）。
    `REAL_CONSUMPTION_BASELINE` **24 → 28** 并把度量域改为全部 render 策略文件
    （旧值按 `_four_table_strategies()` 过滤集算，漏了 G6/G7 的 `_service` 子策略与 H4）。
    `test_semantic_resolver_coverage.py` **30 passed**；`backend/tests/four_table/` **1262 passed / 0 failed**。
    CI 复用既有 `semantic-resolver-coverage` job（本就整文件跑，只更新了注释），未新建 job。
  - 在 `test_semantic_resolver_coverage.py` 增一条：未迁移策略清单必须 ⊆ 定向名单里
    「已裁决不迁移」的集合 —— 新增策略若未迁移又未登记裁决理由即打红
  - 防「下个会话看到 24/55 又发起一轮批量迁移」
  - _Requirements: 4.7, 5.4_

## Notes

### 裁决交叉锁死实测结论（Wave 7 第三项，2026-08-03，不连库）

守卫 = `backend/tests/four_table/test_semantic_resolver_coverage.py` 的
`TestAdjudicationCrossLock`（8 例）+ `TestHonestCoverageReport` 扩充（3 例）。
**纯文件扫描、零 DB**，可进 CI 静态 job；已挂既有 `semantic-resolver-coverage`（未新建 job）。

| 指标 | 值 |
|---|---|
| 四表策略域（`_four_table_strategies()`） | **59** |
| 真消费（变量名无关判定） | **26**（域内）／**28**（全部 render 文件，G16/H10/E1/M8） |
| 未迁移 | **33** |
| `ADJUDICATED_NOT_MIGRATED` 条目 | **33**（与未迁移集合逐字相等） |

**🔴 三处与原任务描述的偏离（均有实证）**

1. **`REAL_CONSUMPTION_BASELINE` 由 24 改 28，度量域同时改为全部 render 策略文件。**
   旧值按 `_four_table_strategies()` 的**过滤集**算（该集实测只有 26），而 tasks.md /
   memory 记的 28 是全量口径 —— 两者差 2 是 G6/G7 的 `_service` 子策略（被 `_service`
   跳过）与 `_h4_engineering_materials`。直接把 28 填进旧断言会**假红**。
   新增 `REAL_CONSUMPTION_BY_CYCLE = {G:16, H:10, E:1, M:1}` 逐循环下限，防「一个循环
   回退、另一个新增」互相掩盖。

2. **`SKIP_PATTERNS` 是子串匹配，有两处误伤真实主策略** ——
   `_h4_engineering_materials.py`（`_engineering` 内含 `_engine`）与
   `_m7_special_reserve.py`（`_special_reserve` 内含 `_special`）。
   不修则 **M7 这个确实未迁移的四表策略会逃出裁决名单**（域 57→59、未迁移 32→33）。
   已加 `DOMAIN_FORCE_INCLUDE` + 一条自检断言「这两个文件确实仍被 SKIP_PATTERNS 误伤」
   （误伤消失就该把它们从常量移出，防死代码）。

3. **名单域 = 四表策略集，故 D/L/M1/M2/K9~K13 不在名单里**（不是漏登记）。
   实测这些文件**根本不引用四表取数**（`_fetch_tb` / `TbBalance` / `ReportLineAccountSpec` /
   `resolve_report_line_accounts` 四个关键词全无命中）：D 循环 24 文件 in_domain=**0**、
   L 循环 19 文件 in_domain=**0**、`_m1_dividends_payable` / `_m2_paid_in_capital` /
   `_k9~_k13` 亦为 0 → 它们没有科目定位可迁移。名单按扫描结果建，不按记忆写死。

**反向自检 4 条 + 变异实测**（`test_reverse_selfcheck_*`，判据全部抽成纯函数
`adjudication_gaps` / `adjudication_orphans` / `_reason_lacks_basis` 以便注入替身）：
① 删掉 `_n5_income_tax_expense.py` 条目 → 立刻点名它；
② 把该条理由置为 `"   "` → 仍点名（空理由不算裁决）；
③ 把**已真迁移**的 `_g1_trading_financial_assets.py` 塞进名单 → 报
「已真迁移，应移出名单并上调 REAL_CONSUMPTION_BASELINE」；
④ 塞不存在的文件 → 报「文件不存在」；
⑤ 占位理由（「暂不迁移，风险大，以后再说」）→ `_reason_lacks_basis` 判 True。
另有 `test_adjudication_list_partitions_the_domain` 断言「真迁移 ∪ 名单 == 域全集」，
杜绝「既不在名单、又不算未迁移」的灰区。

**理由质量闸**：每条理由 ≥20 字且必须命中 `REASON_BASIS_MARKERS`（一码一名 / 按名定位 /
恒 0 / 全库不存在 / 硬编码 / 无科目码字面量 / 单一真源 / 变体行号 / `accounts.gross` /
已委托 / DB 对账）之一。该常量**只许因新实证形态扩充，不许为让某条占位理由过关而放宽**。

### 旧制编码守卫实测结论（Wave 7 第二项，2026-08-03，postgres 只读）

守卫 = `backend/tests/four_table/test_legacy_encoding_balances_stay_zero.py`（30 例，
连库 4 例 + 不连库 26 例），CI 两处：DB job `legacy-encoding-balances`（postgres service
+ `-rs` 让 skip 原因可见）+ `cycle-specs-account-evidence` 里跑不连库部分。

**活体计数（`get_active_filter` 口径，非裸 `is_deleted`）**：

| 表 | 旧制区间行数 | 违规 |
|---|---|---|
| `trial_balance`（当期/审定 4 列） | 170 | **0**（唯一非零行 = 白名单 `3201 套期工具`） |
| `tb_balance`（期初/借/贷/期末 4 列） | **182** | **0** |
| `trial_balance.opening_balance` | 170 | 0（2 对已冻结，见下） |

**🔴 与任务原文的三处偏离（均有实证依据）**

1. **`tb_balance` 行数是 182 不是 364。** 364 是裸 `is_deleted=false` 的口径；
   `tb_balance` 存在多 dataset 版本（`2aa00f57` 实测 active dataset 只含少数科目），
   裸扫描会把 staged/superseded 行算进来 → 假红。守卫按 `(project_id, year)` 枚举后
   逐对取 `get_active_filter`，357（active+is_deleted）→ **182**（active dataset）。

2. **「1 行非零」只在当期/审定口径成立；期初口径另有 2 行。** 逐列复核：
   `trial_balance.opening_balance` 上 `3102 其他综合收益` = 619,000.00、
   `3201 利润分配` = **25,630,018.69**（均在 `b39809ed`）。当期/审定列（N4/N5/F5 真正读的
   `TB('6403','本期发生额')` → `unadjusted_amount`）确实只有 1 行非零。
   → **不静默排除**：拆成两条硬断言，期初口径按「已知 (码,名) 对」冻结，新增任何一对即打红。
   `3201 利润分配` 当前不构成少算，因为 M 循环取数走 `tb_balance` 客户原始码，
   而 `tb_balance` 侧**没有任何旧制权益行**（182 行全是 CAS 2006 共同类/成本类）。

3. **白名单不止 `3201 套期工具` 一条 —— 必须是 9 条。** `^(3\d{3}|5\d{3})` 同时命中
   CAS 2006 的**共同类**（`3101 衍生工具` / `3201 套期工具` / `3202 被套期项目`）与
   **成本类**（`5001 基本生产成本`/`5001 生产成本`/`5002 辅助生产成本`/`5101 制造费用`/
   `5201 劳务成本`/`5301 研发支出`）。这 9 条按任务原文给的同一条理由（「CAS 2006 语义，
   与权益类无关」）同等成立，且 `5101`/`5301` 在 `tb_balance` 里带三层子科目（`5101.07.01`）。
   当前它们金额全为 0 故不加也是绿的 —— 但那是**潜伏的假红**：任一 CAS 2006 项目导入真实
   生产成本就会误触发。白名单按「一级码 + 名称前缀」继承点号子码，无需逐条登记 40 个子码。

**防消红的结构性锁死**：`test_whitelist_cannot_silence_legacy_semantics` 从
`backend/data/standard_account_chart.json`（其 3xxx/5xxx 段实测就是旧制口径：
`3201 利润分配` / `5001 主营业务收入` / `5401 主营业务成本`）反查 —— **白名单里的名字
不得等于旧制表对该码的名字**。即「把 `3201 利润分配` 加进白名单来消红」这一手会直接打红。

**反向自检（3 条 + 1 次 ad-hoc 变异实测）**：注入虚构非零 `5801 所得税费用` 行 →
`legacy_encoding_violation` 与 `scan_rows`（DB 断言用的同一条通道）都点名它；
`3201 利润分配` 带真余额判红而同码的 `3201 套期工具` 判绿（证明是两元组匹配不是按码放行）；
`5101.01 主营业务收入` 判红（子码继承要求名称对得上）。
另做过一次**清空白名单**的变异实测：活体 `trial_balance` 立刻产出 1 条违规、期初通道 3 条
→ 证明 DB 断言不是空转（它真的读到了行）。

**skip 可见性**：`skip_no_db()` 先 print 到 stdout + stderr（带 `[legacy-encoding-guard][SKIP]`
标记）再 `pytest.skip`；`test_skip_helper_prints_reason` 用 `capsys` 断言两处都打了，
`test_db_tests_use_the_printing_skip_helper` 源码级断言全文件只有一处裸 `pytest.skip(`
（即 `skip_no_db` 自己的实现），防新增用例绕开打印。

### F2 展示元数据错码实测结论（2026-08-03，postgres 只读）

`account_chart` 存货区间（`^14\d{2}$`）逐码对账，`client` ∪ `standard`、`is_deleted=false`：

| 码 | 库里的实际科目名 | 项目数 |
|---|---|---|
| `1410` | **零命中**（含 `is_deleted=true` 也 0 行） | 0 |
| `1412` | **零命中**（含 `is_deleted=true` 也 0 行） | 0 |
| `1472` | 合同履约成本 | standard 6 |
| `1407` | 商品进销差价 client 1 / standard 5 ；发出商品 client 5 / standard 4 | — |
| `1408` | 商品进销差价 client 4 / standard 3 ；委托加工物资 client 1 / standard 5 | — |

- `合同履约成本` 只有 `1472` 一个候选（旧变体压根没有这个科目）→ 无歧义。
- `商品进销差价` 两码并存，按「client 表恒为会计口径」取 **`1408`**（client 4 : 1 胜 `1407`）。
- 🔴 `1408` 与 `dev-products`（开发产品）同码属**已知重叠**：`开发产品` / `开发成本` 在
  `account_chart` 全库任何码都查不到（房企专用类别，非 CAS 一级科目），故不占真码。
  影响面仅 `build_default_bindings` 的**兜底**绑定（`resolve_effective` 失败 **且**
  项目无 `account_chart` 时才走到），已在源码注释里写明。
- 仓库内 `backend/data/standard_account_chart.json` 是 **CAS 2006 变体**（`1472 合同履约成本`
  / `1407 商品进销差价` / 无 `1409`/`1416`/`1452`）→ 只能给冻结表做**子集**锚点，
  不能当唯一真源；守卫用它防「冻结表被削小成自证」。
- **取数未受影响**：`classify_f2_leaf`（按科目名）仍是唯一真源，守卫含源码级断言
  「渲染策略里不得出现 `cat["account"]` 式按码取数」+ 一条「同码不同名必须归到各自桶」的行为断言。

### 批 1 执行检查清单（G 循环 10 策略）

迁移每个策略时的步骤：

1. `read_code` 查当前 `_fetch_tb_data` 里的科目定位方式
2. 确认 `g_cycle_specs.py` 里对应 spec 的 `names`/`fallback` 是否正确
3. 替换 import + 删硬编码 + 改调 `resolve_semantic_accounts`
4. 检查叶子聚合是否用了自造 `_is_leaf`（有则替换）
5. 确保 `tb_source_codes` 放在 `project_context` 下
6. 确保 `adjudication_prefill` 存在（空列表也行）
7. `get_diagnostics` 该文件

### 损益类策略额外检查

- 确认使用 `debit_amount`/`credit_amount` 而非 `closing_balance`
- 确认按 `G_PL_POSITIVE_SIDE[wp_code]` 取单侧
- 若现有实现用 `debit - credit` → 必须改为单侧（差额结构性为 0）

### 已知风险

- G7 `_g7_long_term_equity_main_service.py` 被宿主 `_g7_long_term_equity_main.py` 调用，改宿主时子策略不跟会导致科目码分叉 → 同步清零
- K1/K2 旧文件 `k1_account_scope.py`/`k2_account_scope.py` 有大量前端同名 `.ts` 引用其 `row_code` 常量 → re-export 不能断
- D1 的 `d1_account_resolver.py` 被 `d_cycle_extraction` 子模块内多处引用 → 改薄壳后须跑 D1 全套 347 例
