# Task 1：slice 核对 + wp_code 裁决条目（F3 / F4 / F5 共用）

**执行**：2026-09-26　**基线**：工作树（HEAD `07eb3fb75` + 并发会话 WIP）
F4/F5 的 Task 1 引用本文件（三条 entry 的实测在同一批查询里完成，分开写会产生三份互相漂移的副本）。

## 一、slice 核对：三条 entry 均未过期

源：`backend/data/workpaper_sync_f_cycle_manifest_slice.json` → `independent_entries`

| 字段 | `xlsx/gt-f3-notes-payable` | `xlsx/gt-f4-accounts-payable` | `xlsx/gt-f5-cost-of-sales` |
|---|---|---|---|
| `wp_code_pattern` | `F3N` | `F4A` | `F5C` |
| `capability` | `null` | `null` | `null` |
| `capability_verdict_stage` | `pipeline_entry_pending_definition_delivery` | 同 | 同 |
| `capability_target` | `bidirectional` | 同 | 同 |
| `capability_target_blocked_by` | `["BP-1","BP-2","BP-3","BP-4"]` | 同 | `["BP-1","BP-2","BP-3","BP-4","BP-7"]` |
| `migration_state` | `legacy_fake_bidirectional` | 同 | 同 |
| `adapter_id` / `authority_model` / `definition_bundle` / `instrumentation_candidate` / `published_representation` | 全 `null`（五个供给位） | 同 | 同 |
| `template_ref` | `F/F3 应付票据.xlsx` | `F/F4 应付账款.xlsx` | `F/F5 营业成本.xlsx` |
| `mount_count` | 2 | 2 | 2 |
| `scenario_profile_id` | `xlsx.editable.shared.single.room_service_wired.v1` | 同 | 同 |
| `html_counterpart_verdict` | `exists` | 同 | 同 |
| `manifest_mirror.capability` | `single_onlyoffice` + `divergence_from_slice` 已登记 | 同 | 同 |
| `ui_toolbar_gate` | `v-if="showHtmlToolbar"` | `v-if="showHtmlToolbar"` | `class="f5-cost-of-sales-toolbar"` + `ui_toolbar_gate_note` |

逐元素结论：
- 🔴 **F5 的 `capability_target_blocked_by` 含 BP-7、不含 BP-5**（BP-5 是 F2 专属）——F5 spec Task 1 要求的逐元素断言成立。
- F3/F4 恰为 BP-1~4（全 8 条 F entry 共有的平台级供给缺口），无 entry 专属阻塞。
- `published_representation = null` 三条齐全 ⇒ **BP-61-1 属实**，三份 spec 标 `[ ]*` 的发布链任务是真实外部阻塞。
- FC-12 属实：`manifest_mirror.capability=single_onlyoffice` 与 slice 的 `capability=null` 不一致且已在
  `divergence_from_slice` 登记 ⇒ 引用 manifest 值时按「overlay 组件级默认值」标注，不得为对齐而改 overlay/manifest。

## 二、真库实测（PG，只读）

### wp_index 行数 —— 幻影码零命中

```sql
SELECT wp_code, count(*) total, count(*) FILTER (WHERE is_deleted=false) live,
       count(DISTINCT project_id) projects
FROM wp_index WHERE wp_code IN ('F3','F4','F5','F3N','F4A','F5C') GROUP BY wp_code;
```

| wp_code | total | live | projects |
|---|---|---|---|
| F3 | 4 | 4 | 4 |
| F4 | 5 | 5 | 5 |
| F5 | 5 | 5 | 5 |
| **F3N / F4A / F5C** | **0 行（查询无结果）** | — | — |

### store 载荷 —— F5 完全无载荷

```sql
SELECT wi.wp_code, cr.item_id, length(cr.remark) bytes, cr.wp_id
FROM checklist_responses cr
JOIN working_paper wp ON wp.id = cr.wp_id
JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE (cr.item_id LIKE 'F3-%' OR cr.item_id LIKE 'F4-%' OR cr.item_id LIKE 'F5-%')
  AND cr.remark IS NOT NULL AND length(cr.remark) > 2;
```

| wp_code | item_id | bytes | 行数 | 行身份 |
|---|---|---|---|---|
| F3 | `F3-5-rows` | 675 | **2** | 2 行全带 `rowId`（0 行带 `id`） |
| F4 | `F4-2-rows` | 3,485 | **4** | 4 行全带 `rowId` |
| F4 | `F4-7-estimated-inbound-rows` | 1,211 | **2** | 2 行全带 `rowId` |
| F5 | （无任何行） | — | — | — |

🔴 与 spec 记载的差异（两处补充，非矛盾）：
- F3 spec 只记 `F3-5-rows` 675 B，未记行数 ⇒ 本次实测补 **2 行**。
- F4 requirements 记 `F4-2-rows`「4 行全带 rowId」✅ 与实测一致；`F4-7-estimated-inbound-rows` 1,211 B ✅，
  本次补测其为 **2 行**且与 `F4-2-rows` 落在**同一个底稿**（`wp_id=e4f00fc1…`）。
- F5「全部键 0 行」✅ 属实 —— 是 F 循环唯一完全无载荷的 entry，`max_payload_bytes` 如实记 **0**。

🔴 注意 F3/F4 的行身份字段实测是 **`rowId`**，而 F5 spec 记 F5-2/3/5/8 用 **`id`**。
两者不是同一套惯例，声明 `row_identity_key` 时必须逐 entry 按值取（FC-4）。

### finder 域（`backend/wp_templates/_index.json`，476 条）

| 码 | 是否在 `_index.json` |
|---|---|
| F3 / F4 / F5 | ✅ 有 |
| F3N / F4A / F5C | 🔴 **无** |

F 循环 `_index.json` 内的全部码：`F0` `F1` `F2` `F3` `F4` `F5`（六个，无任何幻影码）
⇒ 幻影码 finder 零命中，`assert_no_implicit_template_fallback` 的前提成立。

### 路由域（`backend/app/data/wp_code_overrides.json`）

| 码 | override 目标 |
|---|---|
| F3 | `f3-notes-payable` |
| **F4A** | `f4-accounts-payable` |
| F5 | `f5-cost-of-sales` |
| F3N / F5C | 无 |
| **F4** | 🔴 **无**（只有 F4A） |

🔴 **F4 撞码的精确形态（修正 spec 的表述）**：F4 spec requirements 写「`wp_code_overrides.json:549` 有
`"F4A": "f4-accounts-payable"`（应付账款实质性程序表的路由码）」✅ 属实；但**`F4` 本身在 overrides 里没有条目**。
所以撞码是「manifest 幻影码 `F4A` 与路由码 `F4A` **字面相同**」这一种，不是「F4 与 F4A 两条并存互相干扰」。
三条隔离判据（需求 1.3）的前提因此更强：finder 域（`_index.json`）与业务域（`wp_index`）都没有 `F4A`，
只有路由表有 ⇒ 幻影码不会在取数/查底稿路径上命中任何真实对象。

## 三、裁决条目（已写入）

`backend/data/workpaper_sync_entry_wp_code_adjudication.json`：条目数 **32 → 35**。

| entry_id | wp_codes | contract_id | `matcher_domain_conflict` | `max_payload_bytes` |
|---|---|---|---|---|
| `xlsx/gt-f3-notes-payable` | `["F3"]` | `f3.notes_payable_detail` | `null` | 675 |
| `xlsx/gt-f4-accounts-payable` | `["F4"]` | `f4.accounts_payable_detail` | `null` + **`phantom_code_collision`** | 3,485 |
| `xlsx/gt-f5-cost-of-sales` | `["F5"]` | `f5.cost_of_sales_detail` | `null` | **0** |

F4 条目额外带 `phantom_code_collision` 块（F4 tasks Task 1 要求）：
`phantom_code` / `collides_with` / `why_not_renamed`（裁决 F4-H2：两侧都不改）/
`isolation_evidence`（`index_json_has_f4a=false` · `index_json_has_f4=true` ·
`wp_index_f4a_rows=0` · `wp_index_f4_rows=5` · `provisioner_uses=["F4"]`）/ `measured_at`。

F5 条目的 `store_payload_evidence` 如实记 `max_payload_bytes=0` / `wp_code_with_payload=null` /
`wp_count_with_payload=0` + note 点明「验收前必须先 seed，否则空表往返会被判 `store_mirrored` 假绿」。

digest 按文件自带的 `adjudication_digest_algorithm`
（`sha256(json.dumps(adjudications, sort_keys=True, ensure_ascii=False, separators=(',',':')))`）重算：
`6f045230…` → **`7e4c6d67ad56d034e0935cf1a1d1eb348267fa4cb3d4b330eee95c5f5f77f825`**，已验证可复算。

写盘细节：保持原文件 CRLF 行尾（实测 1,092 处 CRLF / 0 处裸 LF）；**不加 `sort_keys`**
（既有条目并非全字母序 —— F2 的 `note` 在 `store_payload_evidence` 末位，加 sort_keys 会把无关条目
全部重排，让 3 条新增变成全文件 diff）。并发会话此前加的 F1/F2/G 共 19 条经核**完好未动**。

## 四、回归核查

`tests/workpaper_sync/test_task76_wp_code_adjudication.py` + `test_task76_projection_definition_provisioner.py`
+ `test_projection_first_publication.py`：**128 passed / 1 skipped / 2 failed**。

两条 failed 均**与本 Task 无关**，已定位归属：

| failed | 根因 | 归属 |
|---|---|---|
| `TestHostTargetResolutionHasASingleSource::test_host_target_codes_equal_the_reviewed_adjudication`（「只比对了 15 / 16 个已交付 entry」） | 16 个 `DELIVERED_PER_ENTRY_CONTRACTS` 里 **`xlsx/gt-e1-monetary-fund` 缺裁决条目** | E1 spec（并发会话在实施） |
| `TestPublishDoesNotDowngradeExistingGates::test_row_bearing_table_key_agrees_with_every_declaring_provider` | 契约 `e1.monetary_fund_detail` 有 2 张 row-bearing 表（`cash_detail_rows` / `digital_currency_rows`）而 provider 未声明 `ROWS_TABLE_KEY` | 同上 |

判定依据：我新增的三条 entry **不在** `DELIVERED_PER_ENTRY_CONTRACTS`（F3/F4/F5 尚无契约），
既不改变该判据的分母也不参与 `_row_bearing_table_key` 推导 ⇒ 两条 failed 与本次改动无因果关系。
