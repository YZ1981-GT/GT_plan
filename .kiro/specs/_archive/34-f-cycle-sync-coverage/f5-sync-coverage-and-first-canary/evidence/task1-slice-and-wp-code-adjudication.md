# Task 1：slice 核对 + wp_code 裁决条目（F5，零载荷如实记 0）

**执行**：2026-09-26

完整实测见 `.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task1-slice-and-wp-code-adjudication.md`。
本文件只记 F5 的裁决结论与零载荷专项。

## F5 slice 逐元素（未过期）

```
wp_code_pattern              "F5C"
capability                   null
capability_verdict_stage     "pipeline_entry_pending_definition_delivery"
capability_target            "bidirectional"
capability_target_blocked_by ["BP-1","BP-2","BP-3","BP-4","BP-7"]   ← 🔴 含 BP-7，不含 BP-5
migration_state              "legacy_fake_bidirectional"
adapter_id / authority_model / definition_bundle
  / instrumentation_candidate / published_representation   全 null
template_ref                 "F/F5 营业成本.xlsx"
mount_count                  2
scenario_profile_id          "xlsx.editable.shared.single.room_service_wired.v1"
html_counterpart_verdict     "exists"
ui_toolbar_gate              "class=\"f5-cost-of-sales-toolbar\""（F 循环唯一非 v-if 门控形态）
ui_toolbar_gate_note         「本宿主的工具栏也没有 v-if 门控，模式切换器自己带 v-if="isHtmlSheet"」
```

🔴 **BP-7 的逐元素断言成立**（Task 1 明确要求）：`capability_target_blocked_by` 的第 5 个元素是 `BP-7`，
**不含 BP-5**（BP-5 是 F2 专属）。BP-7 的 `must_fix_before` 原文点名本 entry ⇒ 已在 Task 6 修完三处
（见 `evidence/task0-prerequisites.md` 补-7）。

## F5 真库实测：完全无载荷

| 项 | 实测 |
|---|---|
| `wp_index` wp_code=F5 | **5 行**，全部 `is_deleted=false`，分属 5 个项目 |
| `wp_index` wp_code=F5C | **0 行**（幻影码零命中） |
| `checklist_responses` 全部 `F5-%` 键 | 🔴 **0 行**（`length(remark) > 2` 过滤后无任何结果） |
| `_index.json` | 有 `F5`，**无** `F5C` |
| `wp_code_overrides.json` | `F5 -> f5-cost-of-sales`；`F5C` 无条目 |

对照：F3 有 1 个键有载荷（675 B）、F4 有 2 个键（3,485 + 1,211 B）
⇒ **F5 是 F 循环唯一完全无载荷的 entry**，spec 的该结论属实。

## 裁决条目（已写入，零载荷如实记 0）

```
entry_id                     xlsx/gt-f5-cost-of-sales
wp_codes                     ["F5"]
contract_id                  f5.cost_of_sales_detail
matcher_domain_conflict      null
resolvable_for_provisioning  true
store_payload_evidence
  max_payload_bytes          0            ← 🔴 需求 1.3：不得伪造非零证据
  store_item_id              "F5-8-rows"  （canary 的键，供后续 seed 定位）
  wp_code_with_payload       null
  wp_count_with_payload      0
  measured_at                "2026-09-26"
  note                       「F5 全部键真库 0 行（F 循环唯一完全无载荷的 entry）—— 如实记 0，
                              不伪造非零证据（需求 1.3）。验收前必须先 seed（裁决 F5-H7 +
                              Property 8），否则空表往返会被判 store_mirrored 假绿」
basis.wp_index_evidence      「🔴 F5 全部 store 键真库 0 行 ⇒ 无载荷可作落点证据，改以 wp_index
                              行数 + wp_code_overrides.json 的 F5 -> f5-cost-of-sales 为据」
```

🔴 落点证据的替代口径：其他 entry 用「store 载荷落在哪个 wp_code」证明真码；F5 无载荷可用，
故改用两条独立事实 —— ①`wp_index` wp_code=F5 有 5 行活跃底稿 ②`wp_code_overrides.json` 的
`F5 -> f5-cost-of-sales` 路由指向本 entry 的宿主域。两条都不依赖载荷存在。

digest 重算 `6f045230…` → `7e4c6d67ad56d034e0935cf1a1d1eb348267fa4cb3d4b330eee95c5f5f77f825`。

## F5-P2 四条子判据的取证状态

| 子判据 | 状态 |
|---|---|
| ① `_index.json` 无 `F5C` | ✅ 已取证（476 条里 F 循环只有 F0~F5） |
| ② `assert_no_implicit_template_fallback('F5C')` 通过 | 前提成立，可执行判据在 Task 3 |
| ③ provisioner JOIN `wp_index` 用真码 `["F5"]` | ✅ 裁决条目已写入 |
| ④ 裁决条目 `max_payload_bytes == 0` 且附「F5 全部键真库 0 行」原文 | ✅ 已写入 |

## 回归

128 passed / 1 skipped / 2 failed；两条 failed 均为 **E1 欠账**，与 F5 无因果（F5 尚无契约、
不在 `DELIVERED_PER_ENTRY_CONTRACTS` 内）。详见 F3 证据 §四。
