# 交棒：本轮引入的 10 条回归红 — 逐条归因与 owner 建议

**spec**：`sync-editor-host-discovery-contract-closure` · **Task 16** · 日期 2026-10-01
**定位**：本文件是这 10 条红的**权威归因清单**。各 lane 的 tasks.md 只放一行指针回这里，
避免同一事实在多处漂移。

## 归因方法（可复现）

定向 A/B，不是整套两态：

```
# ① B 态全量（62 个引用四件产物的测试文件）→ 282 red，按文件聚合 + 关键词筛出 53 个可疑节点
.venv\Scripts\python.exe backend\scripts\analyze\_fx_ab_regression.py --phase b
.venv\Scripts\python.exe backend\scripts\analyze\_fx_ab_triage.py
# ② 只对这 53 个节点跑两态（A 态 = 七件产物/真源 git show HEAD: 覆盖，finally 按 sha256 强制还原）
.venv\Scripts\python.exe backend\scripts\analyze\_fx_ab_targeted.py --run
```

结果：**A 态 43 red → B 态 53 red ⇒ 本轮引入 10、转绿 0、预存 43**。
（探针是 `_fx_*` 一次性件，已随交付删除；上面命令留作方法记录，不是可直接运行的资产。）

🔴 为什么不跑整套两态：62 文件单态 **903s** 且与并发会话的 pytest 抢真库连接，两态耗时不
对称 ⇒ 差集会混入环境漂移。定向跑把分母从 4600 降到 53，两态各约 50s，而**判据等价** ——
要回答的是「B 态这些红里哪些是本轮引入的」，跑其余 4500 个绿测试对这个问题零贡献。

## 本轮产物变化（这 10 条红的共同上游）

| 指标 | HEAD | 现状 | Δ |
|---|---|---|---|
| `entry_count` | 155 | 189 | +34（34 个 `d4/**` tab 成为 parent_duplicate） |
| `independent_entry_count` | 142 | 142 | **0** |
| `parent_duplicate_count` | 12 | 46 | +34 |
| `capability.bidirectional` | 14 | 28 | +14（13 G + a51，见 design §九 T5 越界登记） |
| `by_component.GtOnlyOfficeSheet`（挂点） | 238 | 222 | −16（并发会话换挂点，见 §九 T7） |
| `by_component.WorkpaperSyncEditorHost` | — | 96 | +96 |

🔴 **本表刻意是 Git / A-B 的提交产物口径**：HEAD 155 → 现状 189，用于解释这 10 条测试红；
它不是功能本体的修复前活源码口径。后者是 **138 → 189**（+17 独立 A 类 +34 d4 parent），
因为 HEAD 产物相对当前在途宿主源码已经 stale。两口径均已在 design §九 T6 独立复现，禁止互换。

## 逐条清单

### ① room_service（平台级，🔴 **疑真实缺陷，优先级最高**）

* **节点**：`test_task21_room_service.py::TestDocKeyIsMtimeFree::test_rg17_is_clear_on_the_real_manifest`
* **失败文案**：`RG-17 有 17 处`，逐条形如
  `xlsx/gt-a101-governance-communication: room_model=shared 但 doc_key 不含 wp 维度 ⇒ 多底稿会共享同一 room`
* **根因**：17 个 A 类 entry 的 `room_model` 是 `shared`，而 RG-17 要求 shared room 的 `doc_key`
  必须含 wp 维度。它们在 HEAD 里**也是 shared**，但 HEAD 的 manifest 里这些 entry 的 resolver 是
  `legacy_sheet_onlyoffice_router`，RG-17 的判据按 resolver 分流 ⇒ 之前不走这条臂。
* **🔴 为什么认为是真缺陷而不是判据过期**：RG-17 描述的危害（多个底稿共享同一 OnlyOffice room
  ⇒ 甲的编辑出现在乙的文档里）是**运行时后果**，不是清册口径问题。本轮只是让它**可见**。
* **owner**：`workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 21（shared room / participant lease）；处置路线两条择一：
  (a) 给这 17 个 entry 的 `doc_key` 加 wp 维度（治本，但要确认不破坏既有 room 的续接）；
  (b) 若 A 类确实该共享 room（例如同一份沟通函多底稿引用），则 RG-17 需要一条**显式豁免**
  并写明豁免条件 —— 不要默认豁免。
* **本轮不动的理由**：改 `doc_key` 会影响运行中 room 的身份，属高风险，且与「修发现契约」无关。

### ② golden digest 覆盖棘轮（平台级 / a51 owner）

* **节点**：`test_golden_digest_coverage_ratchet.py::test_no_bidirectional_entry_escapes_the_golden_gate_beyond_the_two_pilots`
* **失败文案**：`bidirectional 但未进 golden 门的 family = ['a51']`，期望 `[]`
* **根因**：a51 本轮按 Task 14 归位成 `bidirectional`，但它**不在** `check_sync_provider_golden_digest.py`
  的 `PROVIDERS` 里。
* **🔴 它只点 a51、不点 G1~G14** ⇒ 反证 g1~g14 的 provider 全部已在基线内（这条同时是 §九 T5
  裁定「13 条 G override 声明为真」的关键证据）。
* **处置提示（给 owner，本轮不代做）**：a51 是**纯静态 entry**（无动态行表），现算它
  不在 `STORE_MERGE_REGISTRY`（42 键零命中）、`html_store` 刻意留空。把它加进 `PROVIDERS`
  时**必须**按该脚本既有约定关掉不适用的那一段开关（`has_projection=False`，B60/g7 先例），
  而不是让它整家抛异常被 `[SKIP]` 吞掉 —— 那个 `[SKIP]` 曾让 f1 整家从未进过基线。
* **owner**：`workpaper-sync-pure-static-lane-and-combined-workbook-resolution`（a51 是其 Lane A canary）

### ③④ D 循环（2 条）

* **节点**
  * `test_task46_d_cycle_migration.py::TestProperty69EvidencePerEntry::test_slice_scope_is_recomputable_from_the_manifest`
  * `test_task46_d_cycle_migration.py::TestProperty70NoCrossEntryReuse::test_parent_duplicates_not_counted_as_independent`
* **失败文案**：`manifest parent_duplicate=34，slice 40` / `slice 40 与 manifest 不符 34`
* **根因**：D slice 冻结了「D 域 parent_duplicate = 40」这个快照。本轮 34 个 `d4/**` tab 从
  「完全没有 entry」变成「`xlsx/gt-d4-operating-revenue` 的 parent_duplicate」⇒ 现算 34 ≠ 冻结 40。
* **🔴 这不是「数字变小了」而是「口径变了」**：旧的 40 是在那 34 个 tab **不可见**时统计的
  （见本 spec requirements §缺陷描述），两个数不能直接比大小。重算前请先确认 slice 的
  `parent_duplicate` 定义是否包含本轮新可见的 tab。
* **owner**：`d-cycle-sheet-bidirectional-expansion`

### ⑤⑥⑦ G 循环（3 条）

* **节点**
  * `test_task49_g_cycle_migration.py::TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice`
  * `test_task49_g_cycle_migration.py::TestAdjudicationLegality::test_manifest_mirror_divergence_is_registered_not_silently_equal`
  * `test_task49_g_cycle_migration.py::TestProperty20And21NotClaimedPassingForThisSlice::test_no_slice_entry_has_a_registered_adapter`
* **失败文案**（逐条）
  * `xlsx/gt-g1-trading-financial-assets 在 slice 里没有 adapter，却被前端登记为已注册 ⇒ 界面会以「已双向」呈现`
  * `xlsx/gt-g1-... 的 manifest_mirror.capability 与 source manifest 不符`
  * `source manifest 里 xlsx/gt-g1-... 已有 adapter_id`
* **根因**：本轮 overlay 的 13 条 G override 把 G1~G14（除 G7）翻成
  `capability=bidirectional` / `migration_state=adapter_registered`，而 G slice 是**冻结快照**，
  记录的是 provider 交付前的状态。
* 🔴 **这 3 条同时是 design §九 T5 登记的「边界越界」的下游表现**。本轮裁定保留那 13 条
  （四条理由见 §九 T5），因此这 3 条红归 G lane 处置。
* **两条可能的处置方向（请 owner 裁定，本轮不预判）**
  (a) slice 过期 ⇒ 重取 G slice 快照并更新守卫基线（需 owner 复核 provider 确已交付）；
  (b) 认为不该翻 ⇒ 删 overlay 里那 13 条 + 重跑两个生成器即可完全复原（可逆）。
* **owner**：`g-cycle-adjudication-sheets-coverage`（及 `g4-g6-shared-workbook-three-entry-lanes`
  / `g5-nested-sections-and-template-defects` 两条相邻 lane 视 G4/G5/G6 归属）

### ⑧⑨ A/B/C/S 共享（2 条）

* **节点**
  * `test_task57_abcs_and_shared_migration.py::TestAdjudicationLegality::test_manifest_mirror_divergence_is_registered_not_silently_equal`
  * `test_task57_abcs_and_shared_migration.py::TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero`
* **失败文案**：`assert 'single_onlyoffice' == 'bidirectional'`（a51）/ `assert 12 == 46`（parent_duplicate 总数）
* **根因**
  * 前者：a51 的 capability 本轮翻绿（Task 14 要求），而 abcs slice 冻结了 `single_onlyoffice`。
  * 后者：守卫断言「in_scope parent_duplicate 计数为零所以该小节缺席」，用的是全局
    `parent_duplicate_count`（HEAD 12）与冻结值比对；现算 46。
* 🔴 后者的名字 `..._is_absent_because_in_scope_count_is_zero` 说明它的前提是「A/B/C/S 域内
  parent_duplicate 为 0」。本轮新增的 34 个 parent_duplicate **全在 `d4/`**，不在 A/B/C/S 域内
  ⇒ 该前提**仍然成立**，红的是它顺手拿来比对的**全局**数。建议改成域内计数（更贴它自己的命名）。
* **owner**：`a-cycle-sync-foundation-and-first-canary`

### ⑩ 子码裁决（1 条）

* **节点**：`test_task63_subcode_adjudication.py::TestResidencyReverification::test_bp16_manifest_criterion_is_recomputed_from_the_manifest`
* **失败文案**：`assert 155 == 189`
* **根因**：BP-16 判据把 HEAD 的 `entry_count=155` 写死在裁决记录里。
* 🔴 **这条最该改成棘轮或现算而不是等值**：entry_count 会随任何宿主迁移变化，等值断言注定
  周期性打红（本仓已有同类裁定 —— 见 `workpaper-sync-adopt-overwrite-and-refresh-source`
  的 `TestSkipCensusRecount` 从等值改棘轮那一条）。
* **owner**：`workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 67（其 Task 63 现有正文已明确 BP-16 owner 是 manifest 生成侧 / Task 67，**不在 Task 63**）

## 预存红（43 条）—— 本轮**无关**，不在交棒范围

A 态与 B 态同样红的 43 条，分布在 `test_projection_lane_*`(5) / `test_task41`(2) / `test_task44`(2) /
`test_task46`(2) / `test_task47`(1) / `test_task48`(2) / `test_task54`(3) / `test_task55`(6) /
`test_task56`(5) / `test_task57`(9) / `test_task63`(2) / `test_task67`(2) / `test_task75`(1) /
`test_task76`(1)。清单见本轮探针输出（已随交付删除，可按上面方法重跑复现）。

🔴 另：B 态全量 62 文件共 **282** red（212 failed + 70 error），上面 53 是「名称命中 manifest/
entry/overlay 等关键词」的可疑子集。剩余 229 条未逐条做 A/B —— **不声称它们与本轮无关**，
只声明「它们的名称与本轮改动面无交集，且本轮未触碰其判据读取的任何文件」。真要确认需对
全量做两态（单态 903s）。
