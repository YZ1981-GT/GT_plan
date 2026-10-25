# Task 1 证据：slice 复核 + 17 条 entry 事实比对 + wp_code 裁决条目

**执行时间**：2026-09-27　**slice 冻结**：`Task 49（2026-08-31）`

## 一、17 条 entry 逐字段复核：slice 与现 manifest 的差异全部是「slice 是重裁、manifest 是组件级默认」

逐条比对 `capability` / `capability_target` / `capability_verdict_stage` / `migration_state` /
`adapter_id` / `template_ref` / `mount_count` / `wp_code_pattern` / `html_store`，17 条结果完全同型：

| 字段 | slice | manifest | 性质 |
|---|---|---|---|
| `capability` | `null`（17/17） | `'single_onlyoffice'`（17/17） | 🔴 **BP-6 / FC-12**：manifest 值来自 overlay `defaults_by_component.GtOnlyOfficeSheet` 的**组件级默认**，不是逐 entry 裁决 |
| `html_store` | 字段不存在（slice 用 `html_counterpart_verdict='exists'` 表达） | `'unresolved'`（17/17） | 同上，同一处默认值 |
| `migration_state` | `legacy_fake_bidirectional` | `legacy_fake_bidirectional` | ✅ 一致（默认值恰好等于重裁值） |
| `adapter_id` | `null` | `null` | ✅ 一致 |
| `capability_target` / `capability_verdict_stage` / `template_ref` / `mount_count` / `wp_code_pattern` | 有值 | **字段不存在** | slice 的富化字段；manifest 的对应事实在别处：`wp_match.wp_code_patterns`（复数 list）/ `scenario_profile.mount_count` / `profile_source.inbound_reference_count` |

⇒ **无漂移**。所有差异都在 BP-6 已登记的范围内，且 overlay 的 `defaults_by_component.GtOnlyOfficeSheet`
逐字实测为 `{"html_store":"unresolved", …, "capability":"single_onlyoffice", "migration_state":"legacy_fake_bidirectional", …}`
—— 与 BP-6 正文「全 186 条里 180 条 html_store 都是 'unresolved'、capability 都是 'single_onlyoffice'」同源。
本 spec **不改** overlay / manifest 去对齐（FC-12 / 需求 2.5）。

manifest 里 `mount_count`：17 条实测 `scenario_profile.mount_count = 2`（与 slice 一致）。

## 二、模板字节锚：15 文件 sha256 全长逐字取得，`belongs_to_entries` 复数字段确认

15 个文件全部 `in_runtime_index: true`。13 张 owner 模板 + 2 张已排除（G0 / G7，`belongs_to_entry=null` + `excluded_reason`）。

| entry | sha256（全 64 位） | 字节 |
|---|---|---|
| G1 | `eba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73` | 157,253 |
| G2（canary） | `c7563e85a3ebffb7f60a5800dca66f76a5baef97e57cd4be4147f484e7decc84` | 99,479 |
| G3 | `02a5727230a7e2b1f0d3504b87e45ab1998505bb891e8687f3fe0bd9be17a093` | 480,411 |
| **G4-main / -sppi / -ecl** | `da3a3480d37a4b958245abbe6895ed17a1504937bd49d4596aa41fe05a7be0bf` | 999,788 |
| G5 | `c59bba69789eba3f25a8037a5ed32f7482f5eacd08007ef632d04ef2ca0f4b99` | 398,912 |
| **G6-main / -sppi / -ecl** | `63bf38c797d4612e71eeea6fad9dd049765399663af56bc95f235023d2df8f34` | 981,008 |
| G8 | `5c8d3de7ee60ffef8677768c6c3966a313d4210ebc96b19a12c56721954b83b6` | 450,079 |
| G9 | `264322c0ed1b4bf6882687b973377ff0e90bdb5664edb4d7e3752ba39fec2379` | 88,636 |
| G10 | `3afd5131f3783c017f3b7e728e1b081188de71acebb46bdb43e2f8b24fb63da3` | 99,458 |
| G11 | `a1b1d87f29e2dc63e279326d887b3d09bcda6b48c9c54881d82a875a0fe0f513` | 75,600 |
| G12 | `6645caf0fdfadf38b5cc5919d8b4bc60e59dda7bda54747085a40bdf4b66a8f8` | 79,999 |
| G13 | `fd5e5e9eeca7b392d59ca54beac51e96bb1575894113c0f3e69f05a234b0f099` | 58,717 |
| G14 | `5ca770907cfd3723159f4eb45871102f1cee382255e391f3aca0b1d57a287dc6` | 60,094 |

G4 / G6 两条的 `belongs_to_entry = null` + `belongs_to_entries = [三条 entry_id]` 逐字确认，
`excluded_reason` 原文写明「belongs_to_entry 是单值字段，无法诚实表达 1:N ⇒ 记 null 并在
belongs_to_entries 列出真实归属，不硬塞给某一方」⇒ **GC-1（FC-3 不成立）有正向证据**。

## 三、🔴 现算发现三处 spec/slice 不一致（如实登记，不为对齐而伪造）

### 不一致 ①：BP-7 的 `blocked_by` 覆盖面 ≫ BP-7 正文覆盖面

| 来源 | BP-7 覆盖 |
|---|---|
| BP-7 **正文** | **只有** `xlsx/gt-g6-other-bond-sppi`（逐字：`useG6SppiFairValue.ts#L331` 的 `data.rows.map((r, i) => migrateFairValueRow(r, i + 1))` + `#L128` 的 `` `fv-${Date.now()}-${seq}` `` 回退） |
| `dynamic_row_identity.why_this_section_exists` | 同上，只举 G6-sppi（「② G6-sppi 的载入路径会把行身份退化成数组下标」） |
| 逐 entry `capability_target_blocked_by` | **9 条**：G1 · G2 · G3 · G4-main · G6-sppi · G10 · G11 · G12 · G13 |

这 9 条的 `row_identity_kind` 实测：G1/G3 = `generated_timestamp_string`、
G2/G4-main/G10/G11/G12/G13 = `generated_prefixed_opaque_string`、
G6-sppi = `generated_opaque_string_with_array_index_fallback`（**唯一**真正的下标回退）。

⇒ 结论：**只有 G6-sppi 有 BP-7 正文所述的缺陷**；其余 8 条的 `blocked_by` 列了 BP-7 但正文未展开。

**影响到三份 spec 的三处表述**（均需按本条修正，不得反向把 slice 抹平）：

| spec 位置 | 原文 | 实测 |
|---|---|---|
| foundation design §GC-7 | 「BP-7 只命中 **`xlsx/gt-g6-other-bond-sppi`** 一条」 | ❌ 正文只命中一条，但 `blocked_by` 列了 9 条 |
| foundation GF-P3 | 「BP-7 仅 G6-sppi」 | ❌ 判据若这么写会与 slice 逐元素比对冲突 |
| g4-g6 裁决 G46-H4 | 「slice 的 `blocked_by` 给 G4-main 列了 BP-7，但 BP-7 正文只展开了 G6-sppi」 | ✅ **这条是对的**，而且它描述的现象不止 G4-main 一条，是 8 条 |

**处置**（照 G46-H4 的纪律，推广到全部 8 条）：
判据 **GF-P3 按 slice 逐元素断言**（9 条含 BP-7），同时**另立一条子判据**断言
「BP-7 正文 + `dynamic_row_identity` 的实际缺陷面 == {G6-sppi}」，两条并存即把不一致本身锁成事实。
**不修**其余 8 条（它们没有该缺陷），**不删** 它们的 BP-7 标记（那是 slice 的冻结事实）。

### 不一致 ②：BP-9 不在任何 entry 的 `blocked_by` 里

BP-9（`useG1DualMode.ts` 被 G1 与 E1 两循环共用）正文明确指向 G1，但
`xlsx/gt-g1-trading-financial-assets` 的 `blocked_by = [BP-1,BP-2,BP-3,BP-4,BP-5,BP-7]` —— **无 BP-9**。
⇒ foundation GF-P3 的「BP-9 仅 G1」**不成立**（应为「BP-9 不在任何 `blocked_by` 内，只在 BP 清单里」）。
性质上合理：BP-9 的 `must_fix_before` 是「Task 72 的 Stage B 精确删除」，不是「标 bidirectional 之前」
⇒ 它本就不该是受管前置。判据按此修正。

### 不一致 ③：BP-6 覆盖面

| 来源 | BP-6 覆盖 |
|---|---|
| BP-6 正文 | 「source manifest 里 **17 条** G entry 的 capability 仍是 single_onlyoffice」 |
| 逐 entry `blocked_by` | **5 条**：G4-ecl · G5 · G6-main · G6-sppi · G6-ecl |

⇒ 正文覆盖 17 条、`blocked_by` 只标 5 条。实测 manifest 侧 **17 条全部** `capability='single_onlyoffice'`
（见本文第一节）⇒ **正文是对的，`blocked_by` 标注不全**。
另 **g4-g6 spec 的 entry 表遗漏了 G4-ecl 的 BP-6**（它写 G4-ecl = `BP-1~4 + BP-8`，
实测 `BP-1,BP-2,BP-3,BP-4,BP-6,BP-8`）⇒ 该 spec 的 Task 1 须按实测补。

## 四、逐 entry `capability_target_blocked_by` 现算全集（GF-P3 的判据基线）

| entry | blocked_by（逐元素，slice 原值） |
|---|---|
| G1 | BP-1 BP-2 BP-3 BP-4 **BP-5** BP-7 |
| G2（canary） | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G3 | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G4-main | BP-1 BP-2 BP-3 BP-4 BP-7 **BP-8** |
| G4-sppi | BP-1 BP-2 BP-3 BP-4 **BP-8** |
| G4-ecl | BP-1 BP-2 BP-3 BP-4 **BP-6** **BP-8** |
| G5 | BP-1 BP-2 BP-3 BP-4 **BP-6** |
| G6-main | BP-1 BP-2 BP-3 BP-4 **BP-6** **BP-8** |
| G6-sppi | BP-1 BP-2 BP-3 BP-4 **BP-6** BP-7 **BP-8** |
| G6-ecl | BP-1 BP-2 BP-3 BP-4 **BP-6** **BP-8** |
| G8 | BP-1 BP-2 BP-3 BP-4 |
| G9 | BP-1 BP-2 BP-3 BP-4 |
| G10 | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G11 | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G12 | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G13 | BP-1 BP-2 BP-3 BP-4 BP-7 |
| G14 | BP-1 BP-2 BP-3 BP-4 |

BP-1~4 **17/17 共有** ✅（与 spec 一致）。BP-5 仅 G1 ✅。BP-8 = G4×3 + G6×3 ✅。

## 五、真库载荷逐键实测（`store_payload_evidence` 的真源，2026-09-27）

查询：`checklist_responses` ⋈ `working_paper` ⋈ `wp_index`，按 `wp_index.wp_code ~ '^G([0-9]|1[0-4])$'`。

**17 条主受管表的载荷**（`transport_key_shape` 逐键）：

| store_item_id | remark B | conclusion B | 备注 |
|---|---|---|---|
| `G2-2-detail-rows` | **475** | 0 | 🔴 canary，`remark_only` 被字节实证 |
| `G5-2-rows` | **572** | **572** | 🔴 dual_write 唯一字节级实证 |
| `G6-2-rows` | 0 | 2 | 空数组只落 conclusion |
| `G9-detail-rows` | **605** / 2 | 0 | 两行（一真实一空数组） |
| `G8-detail-rows` · `G10-detail-rows` · `G11-detail-rows` · `G12-hedge-detail-rows` · `G13-detail-rows` · `G14-detail-rows` | 2 | 0 | 空数组 |
| `G1-2-rows` · `G3-2-detail-rows` · `G4-2-rows` · `G4-7-items` · `G4-9-rows` · `G6-5-fair-value-data` · `G6-11-rows` | — | — | **真库无行** |

**spec 声明逐条核验结果**：

| spec 声明 | 实测 | 结论 |
|---|---|---|
| G2-2-detail-rows 475 B | 475 | ✅ |
| G5 最多：8 行 / remark 12,952 + conclusion 2,844 | 8 行；remark 2+9+572+254+1209+798+5580+4528 = **12,952**；conclusion 2+9+572+254+1209+798 = **2,844** | ✅ 逐字 |
| G5 五键 remark == conclusion 字节 | `G5-2-rows` 572=572 · `G5-3-rows` 254=254 · `G5-4-rows` 1209=1209 · `G5-5-rows` 798=798 · `G5-2-aging-preset` 9=9 | ✅ |
| G3 最少 12 B | `G3-5-aging-custom-segments` 2 + `G3-5-aging-preset` 10 = **12** | ✅ |
| G4 册唯一载荷 `G4-4-interest-calc` 445 B | 445 | ✅ |
| RG-10 三个模板化拼接键 | `G11-adj-tb-writeback` **46** · `G9-adj-tb-writeback` **40** · `G8-adj-tb-writeback` **40** | ✅ |
| G6 披露键 `G6-disclosure-listed-rows` 4,304 B | 4,304 | ✅ |
| G4/G6 六条主表全零或仅空数组 | 五条无行 + `G6-2-rows` 空数组 | ✅ |

🔴 **spec 表述需微调一处**：`requirements.md` 写「G1~G14 **每个科目都有**（真库载荷）」——
按**科目**看成立（G1~G14 全非零），但按**主受管表**看不成立（7 条主表真库无行）。
lane spec 的 seed 决策必须按**主受管表**判，不按科目判。

## 六、wp_code 裁决条目：17 条已交付（脚本幂等）

脚本 `backend/scripts/fix/fix_g_cycle_wp_code_adjudication.py`（`--check` / `--apply`）。

```
--apply  → adjudications 总数 = 32；新 digest = 6f0452304a1e011499294d3539acdcf2ffdc3b84db9896dd2d106dbf08e30999
--check  → 0 项欠账（幂等）
round-trip → json.dumps(indent=2, sort_keys=False) 逐字节复现原文 ✅
digest   → 按文件自带的 adjudication_digest_algorithm 可复算 ✅
HEAD 已有 10 条 → 当前 32 条；HEAD 已有条目被改动 = 0、被删 = 0 ✅
```

### 🔴 偏差登记：交付 **17 条**（一 entry 一条），而 tasks.md 写「13 条（按册）」

三条理由，均现算可复核：

1. **文件的键是 `entry_id`，消费方按 `entry_id` 查**：
   `projection_target_resolution.py` 与 `fix_task76_provision_projection_definitions.py`
   都是 `adjudication.get(entry_id)`。按册写 13 条会让 `gt-g4-bond-investment-sppi` / `-ecl` /
   `gt-g6-other-bond-sppi` / `-investment-ecl` 四条查不到裁决 ⇒ 落回 Task 76 已判定为错的那条启发式
   （产出 `wp_index` 0 命中的幻影码）。
2. **F2 先例就是一 entry 一条**：四条共用 wp_code `F2` 的 entry 各有独立条目，
   在 `matcher_domain_conflict.conflicting_entries` 里互相列出。G4/G6 与它同型。
3. **GC-1 明令 pointer 按 `entry_id`**；按册聚合与 GC-1 自相矛盾。

G4/G6 的 6 条各带 `matcher_domain_conflict`（含 BP-8 逐字原文 + GC-1 解法 + `belongs_to_entries` 三元组），
其余 11 条为 `null`。

## 七、幻影码 0 命中现算（FC-2 的判据基线）

`wp_index` 按 13 个 `wp_code_pattern` 查：`G1T` `G2I` `G3D` `G4B` `G5L` `G6O` `G8O` `G9O`
`G10T` `G11I` `G12N` `G13F` `G14C` —— **全部 0 命中**。
真码 `G1`~`G14` 各有 4~5 行活行（`is_deleted=false`），`wp_name` 唯一。

## 八、不可达旧桩现状（BP-11，需求 2.6）

`xlsx/gt-g6-other-bond-ecl` 在现 manifest：
`capability='unreachable'` · `migration_state='unreachable_pending_delete'` · `independent_entry=False` ·
`host=None`（故 `mounts` 为空 ⇒ 连 `GtEntrySyncCapabilityNotice` 都没挂，与 spec 的 `notice=0` 一致）。
⇒ **不进任何受管清单**（它 `independent_entry=False`，本 spec 的 17 条全集按 `independent_entry=true` 取，天然排除）。
