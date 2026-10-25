# Task 1：slice 核对 + wp_code 裁决条目（F4）

**执行**：2026-09-26

完整实测见 `.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task1-slice-and-wp-code-adjudication.md`
（三条 entry 在同一批查询里测完，分写会产生互相漂移的副本）。本文件只记 F4 的裁决结论与撞码专项。

## F4 slice 逐元素（未过期）

`capability=null` / `capability_verdict_stage=pipeline_entry_pending_definition_delivery` /
`capability_target=bidirectional` / `capability_target_blocked_by=["BP-1","BP-2","BP-3","BP-4"]`
（🔴 不含 BP-5/BP-7/BP-9）/ `migration_state=legacy_fake_bidirectional` /
五个供给位全 `null`（含 `published_representation`）/ `template_ref="F/F4 应付账款.xlsx"` /
`mount_count=2` / `ui_toolbar_gate='v-if="showHtmlToolbar"'`。

## F4 真库实测

| 项 | 实测 |
|---|---|
| `wp_index` wp_code=F4 | **5 行**，全部 `is_deleted=false`，分属 5 个项目 |
| `wp_index` wp_code=F4A | **0 行** |
| `F4-2-rows` | 3,485 B / **4 行** / 4 行全带 `rowId` / wp_code=F4 / wp_id `e4f00fc1…` |
| `F4-7-estimated-inbound-rows` | 1,211 B / **2 行** / 全带 `rowId` / **同一个底稿** |
| `_index.json` | 有 `F4`，**无** `F4A` |
| `wp_code_overrides.json` | `F4A -> f4-accounts-payable`；🔴 **`F4` 无 override 条目** |

## 🔴 撞码形态的精确化（修正 requirements 的表述）

requirements 写「`wp_code_overrides.json:549` 有 `"F4A": "f4-accounts-payable"`」✅ 属实。
但实测 **`F4` 本身在 overrides 里不存在** ⇒ 撞码只有「manifest 幻影码 `F4A` 与路由码 `F4A` 字面相同」
这一种形态，不是「两条 F4* 并存互相干扰」。

这让需求 1.3 的三条隔离判据前提**更强**：

| 判据 | 实测 | 结论 |
|---|---|---|
| ① `_index.json` 无 `F4A` | 476 条里 F 循环只有 F0~F5 | finder 域零命中 ✅ |
| ② `assert_no_implicit_template_fallback('F4A')` 通过 | 前提①成立 ⇒ 该守卫可过（Task 3 出可执行判据） | ✅ |
| ③ provisioner 用真码 `["F4"]` | 裁决条目 `wp_codes=["F4"]` 已写入 | ✅ |
| ④（本次补充）`wp_index` 无 `F4A` | 0 行 | 业务域亦零命中 ✅ |

⇒ 幻影码 `F4A` 只存在于**路由表**一处；finder 域与业务域都没有它 ⇒ 误把幻影码当业务码用时
不会命中任何真实对象（而是静默 0 结果）。Task 3 的变异判据须钉住「用 `F4A` 查 finder / JOIN wp_index
得到空集」这一点，而不是「抛异常」。

## 裁决条目（已写入）

`backend/data/workpaper_sync_entry_wp_code_adjudication.json`（32 → 35 条）：

```
entry_id                        xlsx/gt-f4-accounts-payable
wp_codes                        ["F4"]
contract_id                     f4.accounts_payable_detail
matcher_domain_conflict         null
resolvable_for_provisioning     true
store_payload_evidence          max_payload_bytes=3485 / store_item_id=F4-2-rows
                                / wp_code_with_payload=F4 / wp_count_with_payload=1
phantom_code_collision          phantom_code=F4A
                                collides_with=wp_code_overrides.json 的 F4A -> f4-accounts-payable
                                why_not_renamed=改 manifest 要动生成器 / 改 overrides 会断程序表路由（F4-H2）
                                isolation_evidence={index_json_has_f4a:false, index_json_has_f4:true,
                                                    wp_index_f4a_rows:0, wp_index_f4_rows:5,
                                                    provisioner_uses:["F4"]}
```

digest 重算 `6f045230…` → `7e4c6d67ad56d034e0935cf1a1d1eb348267fa4cb3d4b330eee95c5f5f77f825`。

## 回归

128 passed / 1 skipped / 2 failed；两条 failed 均为 **E1 欠账**（`xlsx/gt-e1-monetary-fund` 缺裁决条目 +
E1 契约两张 row-bearing 表未声明 `ROWS_TABLE_KEY`），与 F4 无因果 —— F4 尚无契约、不在
`DELIVERED_PER_ENTRY_CONTRACTS` 内。详见 F3 证据 §四。
