# Task 0 证据：foundation 交付门（2026-09-30 现算）

本文件只记**现算值**，不引用任何 spec 自述。

## 一、HC-x 双向覆盖

lane1 依赖 HC-2/3/4/5/6/7/8/10/11/12/13/14/16 共 13 条。现算 HC-1~HC-16 **全部 16 条**
在 foundation 的 `design.md` 有正文、在守卫有判据：

| 项 | 现算 |
|---|---|
| `design.md` 里缺的 HC 编号 | **无** |
| `test_h_foundation_hc_guards.py` 里缺的 HC 编号 | HC-11 / HC-15 |
| 上面两条的实际落点 | HC-11 / HC-15 的判据在 **`test_h9_canary_and_contract.py`**（canary 侧），不是缺失 |
| HF-P1~HF-P18 | **18/18** 在 `test_h_foundation_hc_guards.py` 有判据 |

⇒ lane1 依赖的 13 条 **全部已交付**，无一条阻塞。

## 二、foundation 套件实跑

H 循环 sync 全部测试文件（现算 **10 个**，含 3 个事实模块）：

```
test_h9_canary_and_contract.py
test_h_cycle_migration_progress_state.py
test_h_cycle_registered_defects_fixed.py
test_h_foundation_hc4_key_resolution.py
test_h_foundation_hc9_fallback_chains.py      ← 2026-09-30 从 hc_guards 抽出
test_h_foundation_hc_guards.py
test_h_frontend_managed_sheet_parity.py
test_h_lane2_seed_and_disclosure_defects.py
test_task50_h_cycle_migration.py
h_cycle_facts.py / h_declaration_surfaces.py / h_migration_progress.py（事实模块）
```

结果 **364 passed / 0 failed**。

## 三、lane1 三条 entry 的台账与接桥（现算）

| entry | 契约 | provider 模块 | import |
|---|---|---|---|
| `xlsx/gt-h3-investment-property` | `h3.investment_property_detail` | `phase5_h3_investment_property` | OK |
| `xlsx/gt-h5-oil-gas-assets` | `h5.oil_gas_assets_detail` | `phase5_h5_oil_gas_assets` | OK |
| `xlsx/gt-h7-biological-assets` | `h7.biological_assets_detail` | `phase5_h7_biological_assets` | OK |

`migrated_entry_ids()`（真源 = 前端 `H_OO_WIRED_ROWS_CODES`）现算 **9/9**，三条均在内。

## 四、🔴 仍关着的正向门（与本 spec Task 16*/17* 对应）

manifest 里三条 entry 的 `capability` 现算仍是 `single_onlyoffice`、`adapter_id=None`；
全平台 `capability=bidirectional` 现算**只有 4 条**（d2 / d4 / g7 / h1）。
这是 BP-1~BP-3 的 approved-bundle 门，按设计关着 —— `test_h_cycle_migration_progress_state`
正是在断言它关着。**不在本 spec 权限内放开**。
