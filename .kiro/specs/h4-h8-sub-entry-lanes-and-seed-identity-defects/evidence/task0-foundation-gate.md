# Task 0 证据：foundation 交付门（2026-09-30 现算）

只记现算值，不引用 spec 自述。

## 一、HC-x 覆盖

lane2 依赖 HC-1/2/3/5/6/7/8/11/12/13/14/15/16 共 13 条。现算 HC-1~HC-16 **16/16** 在
foundation `design.md` 有正文；守卫侧 14 条在 `test_h_foundation_hc_guards.py`，
**HC-11 / HC-15 的判据在 `test_h9_canary_and_contract.py`**（canary 侧，不是缺失）。
HF-P1~HF-P18 **18/18** 有判据。⇒ lane2 依赖项**无一阻塞**。

## 二、套件实跑

H 循环 sync 测试文件现算 **11 个**（含 3 个事实模块 + 本轮新增 2 个 lane 守卫），
全量 **388 passed / 0 failed**。

## 三、lane2 两条 entry 的台账（现算）

| entry | 契约 | provider | import |
|---|---|---|---|
| `xlsx/gt-h4-engineering-materials` | `h4.engineering_materials_detail` | `phase5_h4_engineering_materials` | OK |
| `xlsx/gt-h8-right-of-use-assets` | `h8.right_of_use_assets_detail` | `phase5_h8_right_of_use_assets` | OK |

两条均在 `migrated_entry_ids()`（9/9）内。

## 四、5 条 parent_duplicate 子入口（现算，含补齐的 monthly）

```
xlsx/h4/impairment/h4-tab-impairment
xlsx/h4/impairment/h4-tab-recoverable
xlsx/h8/impairment/h8-tab-recoverable
xlsx/h8/measurement/h8-tab-measurement-annual
xlsx/h8/measurement/h8-tab-measurement-monthly
```

五条 `migration_state` 全为 `parent_duplicate`、`capability` 全为 `single_onlyoffice`、
`adapter_id` 全为 `None`；对应 Tab 文件**全部存在**。

## 五、🔴 仍关着的正向门（对应 Task 16*/17*）

两条 entry 的 `capability` 现算仍是 `single_onlyoffice`；全平台 `bidirectional` 只有
**4 条**（d2 / d4 / g7 / h1）。BP-1~BP-3 的 approved-bundle 门按设计关着。
