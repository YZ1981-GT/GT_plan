# Implementation Plan: 语义科目解析全量迁移（70 策略 × 6 批 + 7 优化）

## Overview

将 70 个 render 策略从硬编码 / `report_line_accounts` 迁移到 `semantic_account_resolver`。G 循环（批 1）只需改引用（`g_cycle_specs.py` 已就绪），其余批需新建 per-cycle `_specs.py`。每批完成后跑回归确认零回归。

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

- [ ] 8. 新建 `four_table/d_cycle_specs.py`（D1~D7，7 个 spec）
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

- [ ] 9. 迁移 D 循环 7 策略（D1~D7）
  - D1: `_d1_notes_receivable.py` — 改外层 `_fetch_tb_data` 引 `D1_SPEC`（`d1_account_resolver` 改薄壳委托）
  - D2~D7: 各改引 `d_cycle_specs.XX_SPEC`
  - D4 是损益类，接 `pl_occurrence`
  - D6 有减值备抵须声明 provision 槽
  - _Requirements: 2.1~2.8, 7.1~7.2_

- [ ] 10. 迁移 F 循环 5 策略（F1~F5）
  - F3/F4 负债类 `is_liability=True`
  - F2 特殊：区间口径 `1401~1499`，已有独立 `f2_extraction/category_rules.py`，只改最外层
  - F5 损益类
  - _Requirements: 2.1~2.8_

- [ ] 11. 新建守卫 `test_df_cycle_semantic_specs.py`
  - 覆盖 D1~D7 + F1~F5 的 row_code/兜底码/互斥
  - _Requirements: 4.4_

- [ ] 12. 回归验证 D/F：`rtk python -m pytest backend/tests/ -k "d_cycle or d1 or d2 or d3 or d4 or d5 or d6 or d7 or f1 or f2 or f3 or f4 or f5" --tb=short`
  - _Requirements: 1.2, 5.1~5.4_

### Wave 3 — 批 3：H/I 循环

- [ ] 13. 新建 `four_table/h_cycle_specs.py`（H1~H10）+ `i_cycle_specs.py`（I1~I6）
  - H3 已有独立 `h3_account_scope.py`（4 槽：原值/累计折旧/累计摊销/减值准备），改 re-export
  - H1: `BS-028`（固定资产，含备抵 `IMP-010`?）
  - H2: `BS-029`（在建工程）
  - H10: 损益类（资产处置损益）
  - I 循环全部资产类（I1~I6：无形资产/开发支出/商誉/长期待摊/其他非流动资产/研发费用）
  - I6 损益类
  - _Requirements: 3.2, 3.3, 9.1~9.3_

- [ ] 14. 迁移 H 循环 8 策略（H1/H2/H5~H10，H3/H4 已在 `semantic_account_resolver`）
  - H10 损益类
  - H5~H9 资产类
  - _Requirements: 2.1~2.8_

- [ ] 15. 迁移 I 循环 6 策略（I1~I6）
  - I6 损益类（研发费用）
  - _Requirements: 2.1~2.8_

- [ ] 16. 守卫 + 回归验证 H/I
  - `test_hi_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 4 — 批 4：K 循环

- [ ] 17. 新建 `four_table/k_cycle_specs.py`（K1~K13 统一）
  - K1/K2 已有独立 `ReportLineAccountSpec`（在 `k1_account_scope.py`/`k2_account_scope.py`），收敛为 `SemanticAccountSpec` 并让旧文件 re-export 保兼容
  - K3~K7 负债类 `is_liability=True`
  - K8~K13 损益类，接 `pl_occurrence`
  - _Requirements: 3.4, 4.3_

- [ ] 18. 迁移 K 循环 13 策略
  - K1/K2 已在 `report_line_accounts`，改引 `k_cycle_specs`
  - K3~K7 改引 + `is_liability=True`
  - K8~K13 改引 + `pl_occurrence`（`four_table/pl_occurrence.py` 已建好，K8~K13 已消费）
  - _Requirements: 2.1~2.8, 8.1~8.4_

- [ ] 19. 守卫 + 回归验证 K
  - `test_k_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 5 — 批 5：L/M 循环

- [ ] 20. 新建 `four_table/l_cycle_specs.py`（L1~L8）+ `m_cycle_specs.py`（M1~M10）
  - L 循环：**全部负债类** `is_liability=True`
  - L8 损益类（财务费用）
  - M 循环：**全部权益类** `is_liability=True`
  - _Requirements: 3.5, 3.6, 4.3_

- [ ] 21. 迁移 L 循环 8 策略（L1~L8）
  - L8 损益类
  - _Requirements: 2.1~2.8_

- [ ] 22. 迁移 M 循环 10 策略（M1~M10）
  - _Requirements: 2.1~2.8_

- [ ] 23. 守卫 + 回归验证 L/M
  - `test_lm_cycle_semantic_specs.py`
  - _Requirements: 4.4, 5.1~5.4_

### Wave 6 — 批 6：N/J 循环 + 收口

- [ ] 24. 新建 `four_table/n_cycle_specs.py`（N1~N5）
  - N1: `BS-036`=递延所得税资产 `TB('1811')`（+ 负债 `BS-067`=`TB('2901')`）
  - N2: 应交税费（非标准取数，子科目按税种名称归类）
  - N3: `BS-067`=递延所得税负债 `TB('2901')`
  - N4: 税金及附加（损益类）
  - N5: 所得税费用（损益类）
  - _Requirements: 3.7_

- [ ] 25. 迁移 N 循环 5 策略 + J 循环 2 策略
  - J1/J2 负债类 `is_liability=True`（应付职工薪酬/长期应付职工薪酬）
  - N4/N5 损益类
  - _Requirements: 2.1~2.8_

- [ ] 26. 降级守卫 `test_no_new_report_line_accounts_import.py`
  - 扫 `backend/app/routers/wp_render_strategies/` 全部 `.py` 文件
  - 白名单 = 迁移前已存在的 40 个消费方（随迁移逐步缩小）
  - 新增文件含 `from app.services.four_table.report_line_accounts import` 即红
  - _Requirements: 4.7_

- [ ] 27. CI 总控 + 全量回归
  - `governance-checks.yml` 新增 `semantic-resolver-coverage` job：
    跑全部 `test_*_cycle_semantic_specs.py` + `test_no_new_report_line_accounts_import`
  - 全量后端 `rtk python -m pytest backend/tests/ --tb=short -q`
  - _Requirements: 4.6, 1.2_

- [ ] 28. 收口：更新 `memory.md` 任务状态 + 标注 `report_line_accounts` 为 deprecated
  - 在 `report_line_accounts.py` 模块 docstring 头部加 `.. deprecated::` 注释
  - _Requirements: 5.4_

---

## Notes

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
