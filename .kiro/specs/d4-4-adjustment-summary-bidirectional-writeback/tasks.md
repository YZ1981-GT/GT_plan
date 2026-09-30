# Tasks — D4-4 调整分录汇总双向回写

> 参照实现 `phase5_d4_discount_sheet.py`（D4-19，单区动态行表）。差异 4 处见 design §1 表。
> 🔴 任务标 completed 必须有实际代码 + 测试通过证据；外部依赖/待环境如实标 `[ ]*` 并用
> 「代码已改但未实测」措辞，不假绿。

## 🔴 实施期登记的三处 spec 前提更正（2026-09-28，以现算为准）

按 Req 1.5「以现算为准」逐条登记。三处都不是业务判断错，而是**代码坐标漂移**——
不会报错，只会让人少做几处而不自知。

| # | spec 原文 | 现算 | 处置 |
|---|---|---|---|
| 1 | Task 2：「`oo_to_html.py` 的 4-tuple 硬解包行仍在（现算 L2842）」 | **已不在 `oo_to_html.py`** —— 同一天早些时候 spec `workpaper-sync-managed-row-convergence` Task 3 把三个 `_mirror_*` 抽到会话无关模块 `store_mirror.py`。现算硬解包在 **`store_mirror.py` L314**；`_mirror_d4_dual_stores`(×2) / `_dict_store_items`(×7) 也都在该模块 | Task 7/8 的目标文件改为 `store_mirror.py`；守卫文件头过期描述已更正 |
| 2 | design §3 表列 **8 处**接线 | 现算 D4-19 的真实接线点是 **11 处**（design 把 `values.update` / `row_keys` / `results` 合并计了）。全部照做：1 import · 2 flag · 3 `STORE_ITEM_IDS` · 4 `instrumentation_specs` · 5 `sheets` · 6 `d44_projs` · 7 `values.update` · 8 `row_keys` · 9 `d44_results` · 10 `**d44_results` · 11 `_RAW_PAYLOAD_ITEM_TABLE_KEYS` | 按 11 处实施；探针 `_d44p_wiring.py` 11/11 全命中 |
| 3 | design §2.1 flag 名 `_INCLUDE_D44_SHEET` | 既有 5 个同类 flag 均为 `_INCLUDE_D{n}_{名字}_SHEET`（D419_DISCOUNT / D417_CUTOFF / D420_RETURN / D434_CONTRACT / D48_PRODUCT_MARGIN） | 采用 `_INCLUDE_D44_ADJUSTMENT_SHEET` |

另有一处**期望值不变但成因改变**（Task 13）：spec 预期 `d4LegacyOoBlocked.spec.ts` 的
「推导 legacy 命中集」从 4 张变 5 张，现算**仍是 4 张** —— D4-4 原先被禁入名单挡住、
现在被 `bridged`（dedicated）排除，两条路径都不进命中集。已补独立用例把**成因**钉死。

## 阶段 0 — 几何冻结与前置确认

- [x] 1. openpyxl 现算复核 Req 1 的几何冻结表，逐项与 `backend/wp_templates/D/D4 收入底稿.xlsx`
  的 `营业收入调整分录汇总D4-4` 对账；任一不符即停止并重新裁决，不得带着不符往下做。
  - 必核项：`A1:J23` / 表头 R5 十列逐字 / 首数据行 6 / 末数据行 20 / footer R21 / A21 文本 63 字 /
    数据区公式格 0 / 数据区非空格 0 / 合并仅 A1:J1+A2:J2 / K~O 五列全空
  - 同时确认 `LAST_DATA_ROW=20` 不与 `FOOTER_ROW=21` 冲突
  - 🔴 IF 任一现算值与 Req 1.1 冻结表不符 THEN **以现算为准**，在本 task 下逐条登记更正
    （写明"文档值 X → 现算 Y"），不得沿用文档旧值往下做
  - _Requirements: 1.1, 1.2, 1.5_

- [x] 2. 确认接线点真名与参照 provider 未漂移：`STORE_ITEM_IDS` 与 `_normalize_merge_updates`
  仍定义在 `phase5_d4_revenue_detail.py`（**不在** `oo_to_html.py`）；`oo_to_html.py` 的 4-tuple
  硬解包行仍在（现算 L2842，行号会漂 ⇒ 用形态特征
  `for item_id, (merged_rows, applied, _visited, _touched) in updates.items()` 定位，禁写死行号）。
  - _Requirements: 4.2, 4.3_

## 阶段 1 — 后端 provider

- [x] 3. 新建 `backend/app/services/workpaper_sync/phase5_d4_adjustment_sheet.py`，按 design §2
  写常量 + 字段表 + 12 个函数（结构对齐 D4-19，后缀 `_d44`）。
  - 🔴 `ROW_IDENTITY_KEY_D44 = "rowId"`（**非** `id`，不可照抄 D4-19）
  - 🔴 `stable_field_key` 经 `_snake()` 全小写；`json_pointer`/store 写回保持驼峰
  - 🔴 `_FORMULA_MASK_D44 = ()` 空元组
  - `footer_anchor.carries_total_formula = False`（R21 是提示文本非合计）
  - _Requirements: 1.3, 2.1, 2.2, 2.4_

- [x] 4. `_rows()` 按 design §4 实现：只校验「非空 + 不重复」，**禁加 rowId 格式正则**；
  对 bare list / 空串 / None payload 给容差（不抛 `StorePayloadError` 打挂全 entry rematerialize
  —— D4-9 踩过）。
  - _Requirements: 1.4_

- [x] 5. 新建 `backend/tests/test_d4_4_adjustment_contract.py`：几何常量 vs openpyxl 实测逐项对账
  + 字段 10 个 + `formula_mask` 空 + `stable_field_key` 全小写（正则 `^[a-z0-9_./{}-]+$`）
  + `parse_contract(build_contract_payload())` 不抛 + projection↔merge 往返等值
  + **两种 rowId 格式各跑一遍** + 空 base 不投 0 守卫。
  - **变异反证须实做**：删 `placeholder` 字段 → 红；`UUID_COL_D44` 改 `J` → 红
  - _Requirements: 1.1, 2.1, 2.2, 2.4_

## 阶段 2 — 接线（8 处逐处核对）

- [x] 6. 按 design §3 表在 `phase5_d4_revenue_detail.py` 完成第 1~7 处接线。
  - 🔴 第 4 处 `d44_projs` 默认值必须 `[]` **不是** `{}`（D4-8 曾因此静默把 180 cell 全投 0）
  - 🔴 第 7 处：`STORE_ITEM_IDS` 登记 `D4-4-rows` + merge 返回经 `_normalize_merge_updates` 归一 4-tuple
  - 完成后逐处 grep 自检（combined projection / values.update / row_keys / STORE_ITEM_IDS 四点）
  - _Requirements: 4.2, 4.3, 4.4_

- [x] 7. 第 8 处：确认 `oo_to_html.py` 的 `_mirror_d4_dual_stores` 能取到 D4-4 base。
  D4-4 是 **list 形态** ⇒ 走既有 rows 循环，**不**加进 `_dict_store_items`。
  - _Requirements: 4.5_

- [x] 8. 扩 `backend/tests/workpaper_sync/test_d4_mirror_shape_invariants.py` 覆盖 D4-4：
  merge 返回是 4-tuple + store item ∈ `STORE_ITEM_IDS` + 复刻 mirror 硬解包不抛。
  - **变异反证须实做**：monkeypatch 掉 `_normalize_merge_updates` → 复现非 4-tuple 与 ValueError
  - _Requirements: 4.1, 4.6_

## 阶段 3 — 契约与发布链

- [x] 9. 跑 `python backend/scripts/gen/generate_phase5_d4_contract.py --apply`，磁盘契约
  **35 → 36 张**（新增 `d44-managed`）、受管字段 **775 → 785**；
  `assert_contract_file_matches_source` 返回 OK 无 DRIFT。
  - 落盘前先 dry-run 确认不产生非法 key（D4-8 曾因非法 key 打挂整份 parse）
  - 同时确认契约 schema 校验 **CS-13** 通过：本表无 `mode="formula"` 字段 ⇒「formula 字段必须落在
    `formula_mask` 内」为空分母成立；须**显式记录该空分母**，不得因 `formula_mask` 为空而被误判违规
  - _Requirements: 3.1, 3.2, 2.3_

- [ ] 10*. 发布链（**需 live PG**）：provision → `d43_rematerialize_dual_sheet.py --apply` →
  `--check` 返回 `already_on_desired_bundle`；无 `MaterializeSoftTimeoutError` /
  `RoundtripEquivalenceError` / `FooterAnchorDriftError` / `adapter_unmanaged_region_drift`。
  - 记录 materialize CPU 段耗时并与基线对比（Wave 5 后 69.33s / +D4-33 后 82.53s），**不得提高 soft_limit 120s**
  - IF 环境不可用 THEN 标 `UNVERIFIABLE` + 写明环境门，不假绿
  - _Requirements: 3.3, 3.4, 3.5, 3.6_

## 阶段 4 — 前端接桥

- [x] 11. `D4TabAdjustment.vue` 按 design §5.1 接 `useD4SyncMode`（sheetKey `d44-managed`）+
  `WorkpaperSyncEditorHost`，包在带确定高度的 `.oo-container` 里。
  - 🔴 `flushHtml` 必须先 `await flushPendingSave()`（`debounceSave` 是 2000ms，不 flush 会丢最后一次编辑）
  - 🔴 健康门禁点击时 `await checkOoHealth()` 再判（不得只读初始 false 就静默 return）
  - _Requirements: 5.1, 5.2, 5.6_

- [x] 12. **同一批**改两处（缺一即坏，见 design §5.2）：
  - `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` 加 `'D4-4'`
  - `composables/d4Constants.ts` 的 `D4_LEGACY_OO_BLOCKED_SHEETS` **移除** `'D4-4'`（保留 `'D4-5'`）
  - 同步更新 `d4Constants.ts` 里该常量的注释（移除 D4-4 那段说明，改记「已接桥」）
  - _Requirements: 5.3, 5.4_

- [x] 13. 新建 `d4AdjustmentSyncHostWiring.spec.ts`（经 `useD4SyncMode` 接桥 + 挂 host +
  `.oo-container` + sheetKey 字面量 `d44-managed`）；改 `d4LegacyOoBlocked.spec.ts` 三处期望
  （`isD4LegacyOoBlocked('D4-4')` 翻 `false`、dedicated 交集、**推导 legacy 命中集重算**）。
  - **变异反证须实做**：名单里留着 `'D4-4'` → 前端名单用例红
  - _Requirements: 5.4_

- [x] 13b. 按 design §5.1b 给 `D4TabAdjustment.vue` 表格补 **补充说明**（`placeholder`，插在
  「附注项目」与「借方」之间）与 **备注**（`remark`，插在「索引号」之后）两列，复用既有
  `updateCell(row.rowId, field, v)` 写入路径并受 `isReadonly` 门控。
  - 🔴 **同名陷阱**：该文件已有 6 处 `placeholder="…"` 是 el-input 占位属性，与 `D4AdjustmentRow.placeholder`
    字段无关；grep 判断「是否已有该字段列」时必须区分，否则会误判为已实现
  - 判据：DOM `thead th` 得 10 个业务列，顺序 `[摘要,分类,报表项目,会计科目,附注项目,补充说明,借方,贷方,索引号,备注]`
  - 加守卫：断言表格列数与 `MANAGED_FIELD_SPECS_D44` 的字段数一致（**列数-字段数 对账**，防将来加受管字段忘补 UI）
  - _Requirements: 2.5, 5.7_

## 阶段 5 — 验收

- [ ] 14*. **L1**（需 start-dev.bat 全栈 + OO 容器）：D4-4 加入
  `e2e/d4-bidirectional-acceptance.spec.ts` 的 `D4_ACCEPT_SHEETS`，`--workers=1` 串行跑；
  证据落 `docs/operations/evidence/d4-bidirectional-acceptance/D4-4.json`，
  `console_errors`/`http_errors` 为 0，无 `/d2-sync/*` 旁路。
  - ⚠️ 禁多 worker 并行（OO 8080 单实例 contention 造假失败）
  - _Requirements: 5.5, 7.1_

- [ ] 15*. **L2 seed 前置**：真库 `D4-4-rows` 现 3 行全空白（`category` 是默认值、金额全 0）
  ⇒ 先 seed 带借贷金额的业务行，否则 L2 落进 `empty_payload_skip`。
  - _Requirements: 7.3_

- [ ] 16*. **L2**（需 live PG + OO 容器）：真 OO canvas 写格 → forcesave（`cs_error=0`，
  `4=no_changes` 不算）→ callback durable → application `applied` → HTML store 镜像可见。
  - IF env 门不可跑 THEN 标 `UNVERIFIABLE`，**不得用 L1 通过冒充 L2**
  - _Requirements: 7.2, 7.4_

- [x] 17. 行数超模板容量回归：造 20 行（> 模板 15 行）跑 materialize，断言提示文本 A21 仍在、
  内容未被覆盖、插行发生在 marker 之前。
  - _Requirements: 6.4_

- [x] 18. 既有能力零回归：`test_d4_4_import_export_roundtrip.py`（12）保持绿；
  CRUD / 借贷平衡 / `pushToA13` / `publishAdjustment` / `useAdjustmentCentralSync` 行为不变；
  `flushSave()` 仍 dispatch `d4:save-items` 且宿主监听器仍在；
  D4 辐射面回归（`pytest -k "d4 and not task44"` 基线 301 passed，只增不减）。
  - ⚠️ 用不带 `rtk` 的原始 pytest 输出核实计数（rtk 压缩会报错测试数）
  - _Requirements: 6.1, 6.2, 6.3_

## 阶段 6 — 文档与登记

- [x] 19. `docs/operations/d4-bidirectional-writeback-inventory.md` 追加本轮记录（append-only）：
  逐张清册 D4-4 行 `⬜ single_html` → `✅`；统计段 `⬜` 1 张 → **0**、契约 35 → 36 张、
  字段 775 → 785；`✅ 三维代码全绿` 34 → 35 张。
  - 🔴 计数一律现算，禁按增量推算
  - _Requirements: 8.1_

- [x] 20. `.omm/d-cycle-sales/d4-operating-revenue/concern.md`：§6 更新（D4-4 不再是唯一未接双向的
  有载荷表；禁入名单已摘除）；§7 补记 D4-4 为「N/A 裁决被推翻」的第四例。
  - _Requirements: 8.2_

- [x] 21. `.kiro/specs/INDEX.md` 登记本 spec。🔴 Active 数**现扫** `.kiro/specs/*/tasks.md` 得出，
  禁按增量推算；INDEX.md 是纯 CRLF ⇒ 须 `read_bytes().decode('utf-8')` + `write_bytes()`，
  表格第三格内禁裸 pipe，校验「每行恰 4 个未转义 pipe」。
  - _Requirements: 8.3_

- [x] 22. 交付前自检：每条 Requirement 至少被某个 task 引用一次（脚本化检查，不只数编号连续性）；
  清理本轮一次性探针（`backend/scripts/analyze/_*` 前缀）。
  - _Requirements: 8.4_

## 交付状态（2026-09-28 实施收尾，如实登记不假绿）

**已完成 19/23**（含代码 + 测试通过证据）。

### 余 5 项及各自的真实阻塞

| # | 任务 | 状态 | 阻塞/说明 |
|---|---|---|---|
| 10* | 发布链 provision + rematerialize | `UNVERIFIABLE` | **需 live PG**。契约已 `--apply` 落盘且 `assert_contract_file_matches_source()` 无 DRIFT，但 provision/rematerialize 未跑 |
| 14* | L1 验收（e2e + 证据 JSON） | `UNVERIFIABLE` | **需 start-dev.bat 全栈 + OO 容器** |
| 15* | L2 seed 前置 | `UNVERIFIABLE` | **需 live PG**（真库 `D4-4-rows` 现 3 行全空白，L2 前须 seed 带借贷金额的业务行） |
| 16* | L2 真 OO canvas 往返 | `UNVERIFIABLE` | **需 live PG + OO 容器**。🔴 **不得用 L1 通过冒充 L2** |
| 18 | D4 辐射面全量回归 | ✅ **已完成** | 826 passed / 4 failed，4 红已 stash 归因为预存 |

### Task 18 全量回归结果（已完成）

**76 个 D4 测试文件**（79 个中排除 3 个 `*_live.py`，避开 `-k` 全目录遍历与 live 超时）：
**826 passed / 4 failed，250.36s**。

4 条红已用 `git stash` **权威归因为预存失败**（与本轮无关）：

| 失败用例 | 性质 |
|---|---|
| `test_d4_inspection_io_roundtrip::test_d4_14_seven_dimension_round_trip_and_score_reset` | D4-14 七维 Hypothesis PBT，4 个 distinct failures |
| `test_d4_price_import_formula_preserve::test_parse_d4_9_and_d4_11_field_mapping` | D4-9/D4-11 字段映射断言 |
| `test_note_d4_segment_structure::TestNoteTemplateAlignment::test_column_keys_are_stable_form[listed]` | 附注模板标签列须显式 flat |
| 同上 `[soe]` | 同上 |

🔴 **归因过程踩了一个坑，值得记**：首次 `git stash push` 把**新文件**
`phase5_d4_adjustment_sheet.py`（untracked）也列进 pathspec ⇒ git 报
`pathspec ... did not match any file(s) known to git` 并**整体失败**（没有创建任何 stash），
而后续命令照常执行、测试照常报 4 红 ⇒ **看起来像完成了归因，实际改动一直在工作树上**。
第二次只 stash 两个 tracked 文件（`phase5_d4_revenue_detail.py` + 契约 json），
并显式验证「`git stash list` 顶部是本次条目」+「`git status` 对这两个文件无输出」
才算真回退；此时 4 红依旧 ⇒ 归因成立。
⇒ **`git stash` 用于归因时必须验证它真的创建了 stash**，不能只看后续命令跑通了。
（这与「工具报 0 errors 先查是否崩溃」同型：命令没生效不一定会让流程显式失败。）

恢复后复跑 `test_d4_4_adjustment_contract` + `test_d4_mirror_shape_invariants` +
`test_d4_operating_revenue_contract` = **103 passed**，确认 stash/pop 未损坏改动。

**其他 D4 provider 未被破坏的独立证据**：13 个 D4 契约测试文件（含 D4-6/10/11/12/13/17/18/19/20
共 9 个**其他** sheet 的 provider 契约）合计 **177 passed** —— 证明对
`phase5_d4_revenue_detail.py` 的 11 处接线没有影响任何既有 provider。

**非回归判据逐条现读确认**：`pushToA13` / `publishAdjustment` / `useAdjustmentCentralSync` /
`syncToCentral` 调用链未动；借贷平衡四项（`debitTotal`/`creditTotal`/`isBalanced`/`balanceDiff`）
仍是 `computed` 未纳入受管；宿主 `d4:save-items` 监听器（`onMounted` 注册 +
`onBeforeUnmount` 注销）完好；`test_d4_4_import_export_roundtrip.py` 保持绿。

### 🔴 本轮新增的一条环境事实（供后续 spec 复用）

`pytest tests/ -k "<模式>"` 在本仓库是**高成本操作**：① 要遍历整个 `tests/` 目录做 collection；
② 可能命中 `*_live.py`，在无 live PG 时等超时（本轮首次前台 25 分钟超时、后台长时间无输出，
根因就在此）。
⇒ 后续 spec 写回归判据时应直接给**明确文件列表**并显式排除 `*_live.py`，
而不是给 `-k` 表达式 —— 否则判据在无 live 环境下不可执行。
### 🔴 本轮新增的一条环境事实（供后续 spec 复用）

`pytest tests/ -k "<模式>"` 在本仓库是**高成本操作**（全目录 collection + 可能命中 live 测试）。
后续 spec 写回归判据时，应直接给**明确文件列表**并显式排除 `*_live.py`，
而不是给 `-k` 表达式 —— 否则判据在无 live 环境下不可执行。
