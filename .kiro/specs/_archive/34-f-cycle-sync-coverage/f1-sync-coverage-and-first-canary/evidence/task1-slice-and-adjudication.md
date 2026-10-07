# Task 1 证据：slice 核对 + wp_code 裁决条目

**日期**：2026-09-26

## slice 核对

逐项核 `backend/data/workpaper_sync_f_cycle_manifest_slice.json` 中 `xlsx/gt-f1-prepayment`
条目与 manifest `backend/data/workpaper_sync_entry_manifest.json` 比对：

| 字段 | slice | manifest | 一致 |
|---|---|---|---|
| `entry_id` | `xlsx/gt-f1-prepayment` | `xlsx/gt-f1-prepayment` | ✅ |
| `migration_state` | `legacy_fake_bidirectional` | `legacy_fake_bidirectional` | ✅ |
| `adapter_id` | `null` | — (不存在) | ✅ |
| `template_ref` | `F/F1 预付账款.xlsx` | — | ✅ |
| `scenario_profile_id` | `xlsx.editable.shared.single.room_service_wired.v1` | — | ✅ |
| `mount_count` | 2 | 2 个 `<GtOnlyOfficeSheet>` mount | ✅ |
| 五个 null 供给位 | `authority_model/definition_bundle/instrumentation_candidate/published_representation` 全 null | — | ✅ |
| `capability` | `null` (slice) vs `single_onlyoffice` (manifest) | 不一致但已登记 BP-6 | ✅ |
| `capability_target_blocked_by` | `["BP-1","BP-2","BP-3","BP-4"]` | — | ✅（FC-13 逐元素断言） |

**结论**：slice 未过期，与 manifest 一致。

## wp_code 裁决条目新增

在 `backend/data/workpaper_sync_entry_wp_code_adjudication.json` 第 11 条新增 F1：

```json
{
  "entry_id": "xlsx/gt-f1-prepayment",
  "contract_id": "f1.prepayment_detail",
  "wp_codes": ["F1"],
  "matcher_domain_conflict": null,
  "resolvable_for_provisioning": true,
  "store_payload_evidence": {
    "store_item_id": "F1-det-rows",
    "wp_code_with_payload": "F1",
    "wp_count_with_payload": 1,
    "max_payload_bytes": 46295,
    "measured_at": "2026-09-26"
  }
}
```

`adjudication_digest` 已重算：`0307c22f360452ca...`（算法：sha256 of json.dumps(adjudications, sort_keys=True)）

裁决依据同 D1/D3/D7：F1P 是 CamelCase 幻影码 finder 零命中；store 载荷 `F1-det-rows`（46,295 B / 68 行）落在 wp_code=F1 上。
