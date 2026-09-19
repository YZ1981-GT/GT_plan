# `workpaper_sync_word_contracts/` —— Word lane 的 **staged** per-entry 契约

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`（Task 60 建目录并放入 F2-22 / F2-23）

生成器：`backend/scripts/gen/generate_task60_f2_word_contracts.py`（`--check` 幂等比对 / `--write` 覆盖）
守卫：`backend/tests/workpaper_sync/test_task60_f2_word_adapter.py`
发布记录：`backend/data/workpaper_sync_f2_word_lane_publication.json`

## 为什么不放进 `workpaper_sync_contracts/`

那个目录是**生产清册**：

- `contracts.available_contract_ids()` 扫它；
- `test_task13_contract_registry.py::test_contract_directory_matches_the_delivery_ledger`
  要求「目录 ↔ `registry.DELIVERED_PER_ENTRY_CONTRACTS` **双向等值**」，且登记表每行的
  `entry_id` **必须命中 source-backed manifest**；
- `registry.assert_contract_file_current`（RG-11）注册时按 `contract_path_for()` 读生产目录。

而 F2 Word 通道在 `backend/data/workpaper_sync_entry_manifest.json` 里**没有 entry**：
7 条 docx entry 全是 `A10B / A12B / A16B / A17B / GtWpRenderer / WorkpaperWordEditor /
WpPopupDocxEditor`，无一条 `wp_code` 前缀为 F。F2-22/F2-23 的在线编辑走
`useF2StocktakeDualMode.ts` 打四个 REST 端点，**没有任何 OO 组件挂载点**供 manifest
扫描器发现（`wpPopupDocxConfigs.ts` 的 `DOCX_POPUP_CONFIGS` 也只有 A 系列）。

⇒ 现在把契约放进生产清册只能二选一地假绿：要么登记表缺行（目录 ↔ 登记表不等值），
要么伪造一个不存在的 manifest `entry_id`。因此本目录是 **staged** 区：

| 事实 | 值 |
|---|---|
| `review_status` | `reviewed`（内容已逐字段对权威 docx 复核） |
| 是否进 `available_contract_ids()` | **否**（不在生产目录） |
| 是否可注册 adapter | **否**（RG-11 读生产目录） |
| 解除条件 | 发布记录的 `BP-10`：该 lane 先在 source-backed manifest 里有 entry |

## 契约内容的三边锁

1. **声明** —— 生成器的 `_PLAN_FIELDS` / `_SUMMARY_FIELDS`；
2. **磁盘真读** —— `zipfile` 直读 `backend/wp_templates/F/*.docx!word/document.xml`，
   逐 token 现算出现次数 / 段落序号 / **未 strip 的**段落原文 / run 数 / 是否在 `w:tbl`
   或既有 `w:sdt` 内；结果逐条落在发布记录的 `entries[].field_evidence`；
3. **impl 常量现读** —— 载体与锚点白名单委派 `WordSdtCarrierGate.load()`（真源 =
   `onlyoffice_word_sdt_carrier_contract.json` 的 `downstream_gate`），digest 链委派
   `build_word_template_payload` / `build_word_instrumentation_payload` +
   `definitions.canonical_digest`，契约强校验委派 `contracts.parse_contract`。

## 载体与锚点

- `identity_carriers` 只含 `field_sdt_inline` / `field_sdt_block`；
- **无 `repeaters`**：两份文档的 `w:tbl` / `w:tr` 计数现算为 0，且 Task 6 把 `row_sdt`
  列为 `carriers_blocked`（OO 9.4 首次序列化即剥离）⇒ 行载体在此既无对象也不许用；
- 锚点只用 `w:tag`。`source_ref` 里的 `p{NN}` 是**一次性迁移线索**，不是回写锚点
  （`paragraph_index` / `run_index` 在 Task 6 都是 `failed`）。
