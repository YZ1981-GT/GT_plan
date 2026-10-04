# F1 vs D4 复盘比照

**日期**：2026-09-26

## 架构定性

| 维度 | D4 | F1 | 结论 |
|---|---|---|---|
| **范式** | 手工门面（每 sheet 独立模块 + 主文件硬接线） | 泛型框架（SPEC 对象 + `phase5_row_table_sheet` 引擎） | ✅ 正确选型：F1 的 7 个受管区形态同构，泛型范式省 ~2000 行代码 |
| **规模** | ~2720 行主文件 + 20+ 子模块 | ~420 行主文件 + 7 个薄声明 | ✅ 一致性更高 |
| **扩展模式** | 新 sheet → 新模块 + 主文件硬接线 | 新 sheet → 新 SPEC + 灰度开关一行 | ✅ 维护成本低 |

## 逐项差异与判定

### ✅ 无问题的差异（合理省略）

| D4 有而 F1 没有 | 原因 | 判定 |
|---|---|---|
| `mapping_digest` 体系（3 个函数） | D4 是 Phase 5 首个 canary，mapping digest 用于冻结字段映射防漂移；F1 走引擎层的 SPEC 对象，字段映射内嵌在 spec 声明中，由 `build_contract_payload → assert_contract_file_matches_source` 双向锁死替代 | ✅ 不需要 |
| `iter_store_rows` / `split_store_row` / `store_row_identity` | D4 手工拆分投影，F1 全走 `phase5_row_table_sheet.build_store_projection` 框架层 | ✅ 不需要 |
| `_ensure_months_list` | D4 特有的 months 数组维度，F1 无 | ✅ 不适用 |
| `build_combined_store_projection` | D4 需要联合 30+ store 投影做 materialize overlay；F1 只有 1 个受管 store（canary），framework 按 single-item 路径处理 | ✅ 不需要（开灰度后由 registry 的 `store_merge_plan` 分发） |
| `merge_projection_into_all_d4_stores` | D4 的 30+ store 联合合并；F1 走 `store_item_registry.STORE_MERGE_REGISTRY` 查表分发 | ✅ 不需要 |
| 6 个 sibling merge 函数 | D4 dict/转置/静态区形态；F1 全是 rows 行表 | ✅ 不适用 |
| `_attach_sibling_bindings` | D4 多 sheet 同 entry 需要对齐 sibling binding；F1 当前只 1 个受管 sheet（canary），开灰度后需要 | ⚠️ 见下方 |
| `authority_model_payload()` | D4 发布链五元组的一部分；F1 卡 BP-61-1 无需发布 | ✅ 暂不需要 |

### 🔴 需要关注的差异（潜在遗漏）

| 编号 | 差异 | 风险 | 行动项 |
|---|---|---|---|
| **R1** | F1 `attach_pilot_adapters` 不调 `_attach_sibling_bindings` | 当前只 1 受管 sheet 无影响；翻 F1-5/F1-7 灰度后多 sheet 同 entry **必须**补 sibling binding，否则 publish 与 attach 的 binding 漂移 | 🔴 **翻第二个灰度开关前必补**。参照 E1（多 sheet 同 entry 已验证的路径：`phase5_row_table_sheet.attach_sibling_bindings`） |
| **R2** | F1 无 `publish_definitions` + `Phase5Definitions` | BP-61-1 解除后需要发布链五元组才能真正注册 adapter | 🟡 **BP-61-1 就绪前不紧急**，就绪后从 D3/E1 复制即可（~80 行逐字同构） |
| **R3** | F1 `assert_manifest_capability_enabled` 不检查 `adapter_id` | D4 额外检查 `entry.adapter_id == ADAPTER_ID`，防止 overlay 裁决 bidirectional 但 adapter_id 指向错误 provider | 🟡 **安全补丁**：加一行 `adapter_id` 校验（D4 从 overlay 回写 adapter_id 后才有值；F1 卡 BP-61-1 overlay 未裁决，当前无影响） |
| **R4** | F1 `review.html_store` 用 `item_ids` 平铺列表，D4 用 `item_id` + `sibling_stores` | 契约 parse 和 `store_projection_response.py` 两处消费 html_store：前者只读 item_id（兼容两种形态），后者读 item_ids（E1 同款）。**F1 走 `item_ids` 是 E1 验证过的路径，无问题** | ✅ 无需改动 |
| **R5** | F1 无 D4 的「D4-5 固定项」、「D4-13 ERP 检查」等非行表 sheet 处理 | F1 目前 7 个受管区全是行表（含 dict 子数组），无 fixed_text / static_region 需求 | ✅ 如后续发现 F1-4 区①②③ 需受管（当前裁决 HTML-only），再补 |
| **R6** | F1 `build_contract_payload` 不含审定表 sheet | `_INCLUDE_F101 = False` 时 `managed_row_table_specs()` 不含审定表，但审定表不走行表路径（`AdjudicationSheetSpec` 有独立的 `adjudication_sheet_payload()`）。翻灰度后需在 `build_contract_payload` 的 `sheets[]` 中追加审定表 payload | 🔴 **翻 F101 灰度前必补**。参照 D3 `phase5_d3_expansion.adjudication_sheet_payload()` |

### 🟢 F1 做对了而 D4 踩过的坑

| D4 坑 | F1 处置 | 状态 |
|---|---|---|
| D4-35 漏 instrumentation spec 致整 entry fail-closed | F1 走 `managed_row_table_specs()` 动态聚合 + `instrumentation_specs()` 从同一清单派生，单一口径不可能漏 | ✅ |
| D4 store item 多处并集维护不一致（出/回两侧各自维护并集） | F1 `all_store_item_ids()` 单一口径 + `_spec_of_store_item` 路由 | ✅ |
| D4 `assert_entry_selectable` 带 `require_wp_codes` 开关（E1 反例 FC-2） | F1 无关闭开关 + P5 判据真调真 manifest | ✅ |

## 总结

F1 provider 结构是**正确且充分**的——在当前 1 个受管 sheet（canary）+ BP-61-1 阻塞的阶段，
所有必要方法都已就绪。与 D4 的差异全部可追溯到架构选型差异（泛型 vs 手工）和阶段差异（canary vs 30+ sheet 完整注册）。

**6 个行动项中 2 个 🔴 是翻灰度必补的前置**（R1 sibling binding + R6 审定表 sheet payload），
2 个 🟡 是 BP-61-1 就绪后补（R2 发布链五元组 + R3 adapter_id 校验），2 个 ✅ 无需行动。
没有发现「现在就会出错」的遗漏。
