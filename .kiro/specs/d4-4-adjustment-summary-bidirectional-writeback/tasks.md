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

- [x] 10*. 发布链（**需 live PG**）：provision → `d43_rematerialize_dual_sheet.py --apply` →
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

- [x] 14*. **L1**（需 start-dev.bat 全栈 + OO 容器）：D4-4 加入
  `e2e/d4-bidirectional-acceptance.spec.ts` 的 `D4_ACCEPT_SHEETS`，`--workers=1` 串行跑；
  证据落 `docs/operations/evidence/d4-bidirectional-acceptance/D4-4.json`，
  `console_errors`/`http_errors` 为 0，无 `/d2-sync/*` 旁路。
  - ⚠️ 禁多 worker 并行（OO 8080 单实例 contention 造假失败）
  - ✅ 真栈跑通（详见下文「Task 14* L1 验收结果」）
  - _Requirements: 5.5, 7.1_

- [x] 15*. **L2 seed 前置**：真库 `D4-4-rows` 现 3 行全空白（`category` 是默认值、金额全 0）
  ⇒ 先 seed 带借贷金额的业务行，否则 L2 落进 `empty_payload_skip`。
  - _Requirements: 7.3_

- [x] 16*. **L2**（需 live PG + OO 容器）：真 OO canvas 写格 → forcesave（`cs_error=0`，
  `4=no_changes` 不算）→ callback durable → application `applied` → HTML store 镜像可见。
  - IF env 门不可跑 THEN 标 `UNVERIFIABLE`，**不得用 L1 通过冒充 L2**
  - ✅ 真栈跑通，`cs_error=0` / `cs_outcome=accepted`（非 `4=no_changes`），
    application `applied`、真库 store 逐值确认（详见下文「Task 16* L2 验收结果」）
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

**已完成 23/23**（含代码 + 测试通过证据）。原「21/23 + 2 项 env 门 `UNVERIFIABLE`」
已于 2026-09-30 在真栈（`audit-postgres` + `audit-onlyoffice` + 9980 后端 + 3030 前端）
全部跑通并逐项留证，见下文 Task 14* / 16* 结果节。

### 五项 env 门的最终状态（原「余 5 项」，现全部 ✅）

| # | 任务 | 状态 | 阻塞/说明 |
|---|---|---|---|
| 10* | 发布链 provision + rematerialize | ✅ **已完成** | 真栈 live PG 跑通：gen 166→167 / revision 186→187 / 31.8s；抓到并修复 footer marker 全等匹配缺陷 |
| 14* | L1 验收（e2e + 证据 JSON） | ✅ **已完成** | 真栈跑通 1 passed / 1.8m；`console_errors`/`http_errors` 均 0、`d2_sync_hits=0`；顺带抓出共享 playwright 配置 IPv4/IPv6 口径不一致 |
| 15* | L2 seed 前置 | ✅ **已完成** | 真栈 live PG：新建幂等 seed 脚本，3 行借贷各 168000 平衡；`--force` 发布后实测落 substrate R21~R23 十列全对、footer 正确下移 R24 |
| 16* | L2 真 OO canvas 往返 | ✅ **已完成** | 真栈跑通 1 passed / 1.2m：OO 写 J21 → `cs_error=0`/`accepted` → application `applied`（rev 190，conflict 0）→ 真库 store 只有目标行 remark 变成 marker，另 2 行逐字未动 |
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

### Task 10* 发布链结果（已完成，真栈 live PG）

`provision → rematerialize --apply → --check` 全链跑通，**耗时 31.8s**（soft_limit 120s 未动）。

| 步 | 结果 |
|---|---|
| provision（`fix_task76_provision_projection_definitions.py --apply --entry xlsx/gt-d4-operating-revenue`） | `status: ok`；artifact 176→178、bundle 86→88（两轮）；`content_revision` 186→186 未变（provision 不碰业务内容，正确） |
| rematerialize `--apply` | `status: rematerialized`；generation 166→**167**、revision 186→**187**；新 representation `d7465e5d…` |
| rematerialize `--check` | `already_on_desired_bundle`，且 current bundle `06fb97a2…` **== desired**（真收敛） |
| 异常 | 无 `MaterializeSoftTimeoutError` / `RoundtripEquivalenceError` / `FooterAnchorDriftError` / `adapter_unmanaged_region_drift` |

新 substrate `000000167-9f28d1a3224a.xlsx` 里 D4-4 的四个 definedName 全部就位，
与契约冻结值逐项吻合（`GT_*` 总数 149→**153**）：

| definedName | 值 | 对账 |
|---|---|---|
| `GT_MANAGED_REGION_D44` | `$A$6:$J$20` | 首数据行 6 / 末行 20 / 受管末列 J |
| `GT_ROW_UUID_RANGE_D44` | `$K$6:$K$20` | UUID 载体列 K（该 sheet `max_column` 10→**11**） |
| `GT_FOOTER_ANCHOR_D44` | `$A$21` | FOOTER_ROW 21 |
| `GT_SYNC_ANCHOR_D44` | `_GT_SYNC!$A$1` | 清册锚 |

#### 🔴 本步抓到一个只有真栈才能暴露的**真缺陷**（已修）

首版 `FOOTER_MARKER_D44 = "提示："`（前缀），理由是「A21 完整文本 63 字，取前缀作 marker，
引擎按前缀搜 A 列」。**那个理由是错的**：引擎 `excel_materialize._find_marker_row` 的判据是
`text.strip() == marker` —— **全等**，不是 `startswith`。

后果：rematerialize `--apply` 在 **14.2s** 抛
`FooterAnchorDriftError: 契约声明的 footer marker '提示：' 在列 A 上一处都找不到`。

为什么 48 个单测全绿却没拦住：我自己写的断言是
`a21.startswith(FOOTER_MARKER_D44)` —— **用的是我臆想的口径，不是引擎的口径**。
两个口径下同一份数据结论相反，而单测只验了我的那个。

修复：marker 改为 A21 的**完整 63 字文本**；两条断言从 `startswith` 改成全等；
并新增**变异反证** `test_engine_marker_matcher_rejects_a_prefix_marker` ——
真调 `_find_marker_row`：完整文本 → 命中行 21；前缀 `"提示："` → `None`。
对照佐证：已落地的同类 sheet 一律用完整行文本（D4-19 `三、审计说明` / D4-34 `2.咨询业务`），
**没有一个用前缀**。

⇒ 教训（与本 spec 已记的「代码坐标漂移」并列）：
**凡判据要与引擎对齐，断言必须直接调用引擎那个函数，不能自己写一个「同义」的判断。**
`startswith` 与 `==` 在人看来都叫「匹配 marker」，在代码里是两件事。

marker 变更连带影响：`mapping_digest` → contract digest 变（`90f9add7…` → `3121e56a…`）
⇒ 需重新 `generate --apply` + 重新 provision（bundle `3245ec37…` → `06fb97a2…`）。
instrumentation digest **未变**（`e070c21a…` reused）—— marker 不进 instrumentation 载荷，符合预期。

#### 🔴 另一个假绿：未 provision 时 `--check` 会报 `already_on_desired_bundle`

第一次跑 `rematerialize --check`（provision 之前）得到 `already_on_desired_bundle`，
看起来像「已经不需要做了」。但 `desired_bundle.sha256` 与 `current` **完全相同**
（`1ff44474…`）—— 因为 DB 里根本没有含 D4-4 的新 bundle，desired 就是 current。
若当时直接跑 `--apply`，它会因「已在 desired bundle」而什么都不做，随后 `--check`
再报 `already_on_desired_bundle` ⇒ **两步都「成功」，而 D4-4 一个字节都没进 substrate**。

⇒ 判据补强：`already_on_desired_bundle` 只有在 **desired bundle 已包含本轮改动**时才算通过。
本轮的可观察证据是 `current.bundle_sha256` 从 `1ff44474…` 变成 `06fb97a2…`
且 `generation` 166→167 —— 光看 status 字符串不足以判断。

#### 顺带发现（不在本 spec 范围，已登记）

`provision` 脚本不带 `--entry` 时会遍历全部 entry，在 `xlsx/gt-e1-monetary-fund` 上抛
`ProviderModuleNotAllowedError: provider app.services.workpaper_sync.phase5_e1_monetary_fund
缺 'publish_pilot_definitions'` 而整体失败。这是 **E1 的预存缺陷**，与 D4-4 无关；
本轮用 `--entry xlsx/gt-d4-operating-revenue` 绕开。⇒ E1 的 provider 供给不全，
需独立排查（否则任何「全量 provision」都跑不通）。

### Task 15* L2 seed 结果（已完成，真栈 live PG）

新建 `backend/scripts/e2e/seed_d4_4_adjustment_l2.py`（`--check` / `--dry-run` /
`--apply` / `--purge` 四模式，幂等，按 rowId 覆盖并保留其它行）。

**为什么必须 seed**：`D4-4-rows` 为空或全空白时，OO→HTML 回写会落进
`empty_payload_skip`（mirror 护栏 `applied <= 0 and base_rows` 直接跳过写库），
L2 既不报错也没有可观察结果 —— 那是假通过。

**现查确认 spec 描述准确但需更正目标 wp**：spec 说「真库 `D4-4-rows` 现 3 行全空白」，
现查那 3 行在 wp `21d8089b-…`（另一个项目）；而 T10* 发布链的目标 wp
`b3ab3c46-…`（项目 `0ec33ac9-…`，54 个 D4 item）**根本没有** `D4-4-rows`。
⇒ seed 落在后者（与发布链同一个 wp，否则验的不是同一条链）。

**造的数据性质**：3 行成对分录、借贷各 168000.00（平衡 —— 不平衡会让前端「确认调整」
按钮 disabled、页面状态与真实使用不符）、`description` 前缀 `[L2验收]` 可辨识、
`--purge` 可完整撤销。rowId 用前端 `generateRowId()` 的真实形态且**固定取值**保幂等。
**不冒充任何审计判断**。

写库结果：`status: written`，0 行 → 3 行，`content_version` null → 1。

#### 验证 seed 真的流到 substrate（`--force` 重新发布一次）

gen 167→**168**、revision 188，`store_bytes` 里 `D4-4-rows` = **1187 bytes**（store item 41 个）。

新 substrate `000000168-c294253907c7.xlsx` 的 D4-4 实际布局（`max_row` 23→**26**，
`max_column` 10→**11**）：

| 行 | 内容 |
|---|---|
| R6~R20 | 15 个模板骨架身份 `GTROW-D44-0006`~`0020`，业务列全空 |
| **R21~R23** | seed 的 3 行，**10 列逐字段全对**（含本轮新补的 F 补充说明 / J 备注），K 列为 seed rowId |
| **R24** | 提示文本 —— 从 R21 正确推到 R24，**未被覆盖** ⇒ Req 6.4 成立 |

`GT_FOOTER_ANCHOR_D44` 同步 `$A$21` → **`$A$24`**（随位移更新）；
`GT_MANAGED_REGION_D44` 与 `GT_ROW_UUID_RANGE_D44` 保持 `$A$6:$J$20` / `$K$6:$K$20`。

#### 🔴 顺带实证一条产品行为（与遗留项②同源）

seed 的 3 行没有填进空的 R6~R8，而是**在受管区末尾插了 3 行**。原因：R6~R20 的行身份是
instrument 注入的骨架 `GTROW-D44-*`，与 store 里的 `d4a-l2seed*` 不匹配 ⇒ 引擎判 3 个
orphan ⇒ `_plan_row_shift` 在区末插行。

这是**行身份驱动的设计行为**，不是缺陷；但它说明「HTML 侧新建行会让 sheet 长出新行，
模板预留的 15 个空行不会被复用」。与第十一轮登记的遗留项②（模板固有行未接进 store 初始化）
是同一个缺口的另一面。

#### 🔴 本步我的**探针判据**错了一次（不是产品错）

首版验证探针把期望写成「seed 落 R6~R8、提示文本在 A21」，跑出 **20 项失败**，
其中最刺眼的是 `A21 被破坏: '[L2验收]跨期收入调整…'` —— 看起来像 footer 被覆盖的重大缺陷。

实际是**探针没考虑插行位移**：`max_row` 23→26 已经摆明插了 3 行，footer 必然下移。
换成「不预设行号、全量打印、由数据说话」后结论反转为全部正确。

⇒ 教训：**验证插行路径的探针不得写死行号**。这与本 spec 已记的「spec 判据禁写死行号
（`.vue` 行号会漂）」同型，但这次漂的是**被验对象自己的行号**，而且是我自己引入的位移
造成的 —— 更容易误判成产品缺陷。正确做法是先读实际布局再定判据。

### Task 14* L1 验收结果（已完成，真栈 e2e）

命令（`cwd=audit-platform/frontend`，串行）：

```
$env:D4_ACCEPT_SHEETS='[{"code":"D4-4","name":"营业收入调整分录汇总D4-4"}]'
npx playwright test e2e/d4-bidirectional-acceptance.spec.ts --config playwright._d44.config.ts `
  -g "D4-4" --workers=1 --reporter=list
```

结果 **1 passed / 1.8m**，证据 `docs/operations/evidence/d4-bidirectional-acceptance/D4-4.json`：

| 判据 | 实测 |
|---|---|
| `store_projection_ok` / `materialize_ok` | `true` / `true` |
| `d2_sync_hits`（旁路） | **0** ✓ |
| `console_errors` / `http_errors` | **0** / **0** ✓ |
| `sync_host_mounted` / `oo_iframe_count` | `true` / `1` ✓ |
| `callback_url_keys` | `doc_key,generation,room_id,route_credential_id,route_token`（值已脱敏） |
| `doc_editor_called` | **`false`** —— 见下 |

D4-4 的 `console_errors=0` 属**较干净的一半**：现算 36 张 L1 证据里有 **16 张是 3 条**
console error，D4-4 与另 19 张同为 0。

#### `doc_editor_called: false` 不是 D4-4 的缺陷，是探针钩子的普遍局限

我在 tasks 里原本把它列进判据。现算 **36 张 L1 证据逐个取值，`doc_editor_called`
全部为 `false`**（无一例 `true`）⇒ 该字段的 init-script 包装（`DocsAPI.DocEditor`
猴补）在本平台从未真正触发，是**全 fleet 一致的探针失效**，不是 D4-4 特有表现。
OO 真实挂载由 `oo_iframe_count=1` + `sync_host_mounted=true` + `materialize_ok=true`
三项共同证据支撑。

⇒ **如实记：该判据不成立，改由上述三项承担**。这正是方法论铁律「结构性零/恒定值
必须配变异证明」的应用 —— 一个**在所有样本上都取同一值**的字段不具备判别力，
把它写成验收判据等于加了一条永假门（或永真门），必须换成有判别力的判据。

#### 🔴 顺带抓到一条共享配置缺陷（本 spec 范围外，已另立工单）

`audit-platform/frontend/playwright.config.ts` 自身 IPv4/IPv6 口径不一致：

| 位置 | 值 | 本机连通性 |
|---|---|---|
| `use.baseURL`（L12） | `http://127.0.0.1:3030` | ❌ `ECONNREFUSED` |
| `webServer.url`（L23） | `http://localhost:3030` | ✅ |

根因：Vite dev server 现算**只监听 IPv6** —— `netstat` 实测仅
`TCP [::1]:3030 LISTENING`，无任何 IPv4 监听项。于是 Playwright 的 `webServer`
探活走 `localhost`（解析到 `::1`）能过，而所有相对 `page.goto('/...')` 走
`baseURL` 的 `127.0.0.1` 必然拒连 ⇒ **本机任何 e2e 都跑不起来**，与 D4-4 无关。

Playwright **1.60.0 无 `--base-url` CLI 选项**（实测 `error: unknown option
'--base-url'`），故本轮用一次性配置 `playwright._d44.config.ts`（`_` 前缀 = 用完即删，
**已随探针一并清理**）只覆盖 `baseURL`，**不改共享配置**（改它会影响所有并发会话的 e2e）。
复现只需在 `audit-platform/frontend/` 下临时建这 6 行再删：

```ts
import base from './playwright.config'
export default { ...base, use: { ...(base.use ?? {}), baseURL: 'http://localhost:3030' } }
```

⚠️ 写该临时配置时踩了一个小坑：块注释里写 `T14*/T16*` 的 `*/` **提前终止了注释**
⇒ `BABEL_PARSE_ERROR InvalidOrUnexpectedToken`。已改用 `//` 行注释。

### Task 16* L2 验收（真 OO canvas 往返）

新增用例 `D4-4 L2 真 OO canvas 往返（无跨行污染）`（同文件，照 D4-1 L2 范式）：

* OO iframe 内切到 `营业收入调整分录汇总D4-4` → 写 `J21`（受管列 **J = 备注**，
  `MANAGED_FIELD_SPECS_D44` 的 `remark`/editable/text；选文本列避开数值转换与公式格）
* forcesave 直到 `cs_error=0`（`4=no_changes` 不算）
* 权威门：`checklist-responses` 的 `D4-4-rows` 回读到 marker
* Property 判据换成**无跨行污染**（D4-4 是单区动态行表，无 D4-1 那样的双区）：
  marker 只许落在 `rowId=d4a-l2seed001-a1b2c3d` 那一行，其余行出现即失败
* 前置数据门不满足 → 显式 `blocked` + `test.skip`，**不用 L1 通过冒充 L2**

#### 🔴 一个被证伪的「缺陷假设」——回读区间的权威载体是 Excel Table ref

T15* 登记过「seed 3 行落 R21~R23，而 `GT_MANAGED_REGION_D44`/`GT_ROW_UUID_RANGE_D44`
仍是 `$A$6:$J$20`/`$K$6:$K$20`」。本步先把它当**候选真缺陷**查：若回读只扫声明区间，
就只能看到 15 个空骨架行、完全看不到这 3 行数据 ⇒ OO→HTML 方向静默丢数据。

探针现算（gen168 substrate）：

| 载体 | 值 | 覆盖 seed 行 R21~R23 |
|---|---|---|
| `GT_MANAGED_REGION_D44` | `$A$6:$J$20` | ❌ |
| `GT_ROW_UUID_RANGE_D44` | `$K$6:$K$20` | ❌ |
| **Excel Table `GT_D44_ROWS`** | **`A6:K23`** | ✅ |

再读代码定权威：`excel_extract._resolve_dynamic_region` 对
`BindingKind.excel_table`（D4-4 属此）**从 `binding.table_name` 取 Table 的 `ref`**
解析 `first_row`/`last_row`；definedName 只在 `static_region` 分支用。且全仓 grep
`GT_ROW_UUID_RANGE` 现算**无任何生产读方**（只有 `excel_instrumentation` 写侧 +
4 个测试 + 1 个 diagnose 脚本）。

⇒ **结论反转：不是缺陷**。Table ref 已随插行扩到 `K23`，回读区间正确覆盖 3 行数据；
definedName 滞后属**纯元数据滞后**，无功能影响。

⇒ 教训（与已记的㉑同族）：**「声明值与数据不符」不等于缺陷，先确认哪个载体是权威读方**。
我差点把一个元数据滞后写成「OO→HTML 静默丢数据」的 P0。判定顺序必须是
①现算各载体实际值 ②**读代码确认谁是权威** ③再下结论，不可在第①步就定性。

### Task 16* L2 验收结果（已完成，真栈真 OO canvas 往返）

**1 passed / 1.2m**，证据 `docs/operations/evidence/d4-bidirectional-acceptance/D4-4-L2.json`。

| 环节 | 实测 |
|---|---|
| OO canvas 写格 | `activeSheet=营业收入调整分录汇总D4-4`（从 47 张 sheet 里按名精确切中）、`J21`、`cellTextAfterSave=d44r737694` |
| forcesave | HTTP **202**，body `cs_error=0` / `cs_outcome=accepted` / `callback_expected=true` ⇒ **不是** `4=no_changes` |
| operation | `ba2781a0` direction `oo_to_html` state **`applied`** |
| application | `51ecca4b` gen 169 state **`applied`** / `logical_result_code=applied` / `result_revision=190` / `conflict_count=0` / `durable_at` 与 `finished_at` 均有值 |
| HTML store 镜像 | 真库 `checklist_responses.D4-4-rows` 第 1 行 `"remark": "d44r737694"` |
| 无跨行污染 | 另 2 行 remark 逐字未动（`同笔分录借方` / `仅影响报表列报，不动科目余额`），第 1 行其余 9 个字段亦未动 |
| 旁路 / 报错 | `d2_sync_hits=0`、`http_errors=[]`、`console_errors=[]` |

即：**OO 侧改一个格 → 经真实 forcesave/callback/application 链 → HTML store 精确落到
同一 rowId 的同一字段**，这是 D4-4 真双向的端到端闭环证据（不是 L1 冒充）。

#### 🔴 本步抓到的两个缺陷**都在测试自己身上**（产品侧零缺陷）

**缺陷 A：点击时机 —— 没等切换器解除 `disabled` 就点，点击被静默吞掉。**

`useD4SyncMode.switchMode` 第一行是 `if (busy.value && !isAppliedHtmlReturn(target)) return`。
首版直接 `waitForTimeout(1500)` 后就点「在线编辑」，而此刻 `busy` 仍真 ⇒ 点击被吞 ⇒
materialize 永不发出。表象是「点了没反应」，错误却报在 180s 后的 materialize 轮询上，
**报错位置离真因隔了 3 分钟**。真栈快照坐实：`表格视图` 与 `在线编辑` 两个 radio
**同时** `[disabled]` + 状态标签 `同步中…`。

修法 = 先 `expect.poll` 等 `ooDisabled === false` 再点，并把「进入时 / 门后」两组状态
（标签文本 + 两个 radio 的 disabled）连同 `hits`/`httpErrors`/`console` 一起写进错误信息。
另把 materialize 轮询 180s → **300s**：D4 是整册 37 张 sheet 的 materialize，首版实测
**轮询超时后 18 秒**才出现 `applied` 的 operation —— 判据只差 18s 就把一次成功切成失败。

**缺陷 B：读 forcesave 响应体有竞态 —— 把一次真实成功误判成失败。**

首版从 `page.on('response')` 里 `void res.json().then(b => forcesaveBody = b)` 异步塞的
变量读 `cs_error`。而 `page.waitForResponse` 在**响应头**到达就 resolve，body 解析的
microtask 往往还没跑 ⇒ 读到 `null` ⇒ 循环判「非 0 非 1」直接 break ⇒
`expect(cs_error).toBe(0)` 拿 `null` 打红。

当时的证据其实已经自相矛盾：同一份 evidence 里 `probe.cellTextAfterSave` 已经是 marker、
`forcesave_hits` 已经是 **202**，却报 forcesave 失败。**「关键字段为 null」优先怀疑
自己的取值时序，而不是先怀疑被测对象** —— 若当时顺着「forcesave 坏了」去查产品侧，
会在正确的实现上白挖一轮。

修法 = 从 `await wait` 拿到的 `Response` **直接** `await res.json()`，并把
`cs_outcome` / `callback_expected` / 完整 body 一并记进证据（只记一个 `cs_error`
数字时，分不清「CS 拒了」和「我没读到」）。

⇒ 这两条与方法论铁律㉗第 7 点（`subprocess` 捕获输出时解码失败不会让 `run()` 失败，
只断言退出码必假绿）**同型**：**异步取得的观测值，必须等它真的到位再断言**；
只不过那条是「假绿」，这两条是「假红」——同一个坑的两面。

#### 顺带留下 1 条可观察残留（本轮阻断式 abort 的副作用，非产品缺陷判定）

run 2 在 forcesave 后约 1 秒因断言失败 abort、浏览器随即关闭 ⇒ OO 会话在 CS 完成保存前
断开 ⇒ 该次 callback 永不到达，真库留下 `working_paper_forcesave_request` seq 1
state **`frozen`**（`accepted_at` NULL）+ `working_paper_sync_operation` `b614493d`
state **`created`**（只有一条 `request_frozen` 事件）。run 3 在同一 room 新开 seq 2
正常走完（`correlated` → application `applied`），说明**不影响后续**。

是否该有 reaper 把这类「等不到 callback 的 frozen request」收敛掉，属平台侧课题
（`command_service` 里已有 `forcesave_callback_wait_timeout_seconds` 的 destroy 决策口径，
但那是「离开时怎么判」，不是「后台清理」）—— 登记为遗留项，不在本 spec 范围内擅自改。

---

## 2026-10-01 d44-managed golden 红收口（用户明确授权，append-only）

前述完整 `FOOTER_MARKER_D44` 修复已由真栈与 48 条契约测试证明正确，但
`backend/scripts/check/_sync_provider_golden_digest.json` 仍冻结旧前缀版 digest，导致
`check_sync_provider_golden_digest.py` 唯一红：

```text
[d4] sheet[d44-managed]: 基线=a367bf8bf2e02e71 现算=1fa82f831f2f034a
```

本次**没有**执行 `--update`。先把 current 与 baseline 做全字段递归 diff，现算有 **14** 处差异：
除 d44 两处因果字段外，还含 D3 新增 `d34~d37-managed`、6 家 provider 的整体 contract digest 与
`digest_count 198→202` 等并发/additive 状态；全量更新会把它们一起固化，无法归因。

只精准更新 d4 的两处：

| baseline 字段 | 旧值 | 新值 | 理由 |
|---|---|---|---|
| `providers[d4].contract_payload_sha256` | `90f9add7…` | `3121e56a…` | d44 既有 sheet 的 marker 变化会改变 d4 整体 contract；同步更新保持该 provider 快照自洽 |
| `providers[d4].sheet_digests[d44-managed]` | `a367bf8b…` | `1fa82f83…` | `.tables[0].footer_anchor.marker` 从错误前缀改为模板 A21 完整 63 字 |

其余字段一字不动。更新后严格递归 diff 从 **14→12**，且 d4 provider（索引 4）差异为 **0**；
剩余 12 条仍是 D3/H 等其它 lane 的 additive/整体摘要差异，没有被本次“顺手批准”。

验收：

* `test_d4_4_adjustment_contract.py`：**48 passed**（含真调 `_find_marker_row`：完整文本命中 R21、前缀返 `None`）；
* `check_sync_provider_golden_digest.py`：**202 digest 逐个不变，34 家，零跳过**；
* `test_check_sync_provider_golden_digest.py`：**11 passed**；
* 联跑 golden coverage 时另有 a51 单条红（`bidirectional` 但未入 `PROVIDERS`），是
  `sync-editor-host-discovery-contract-closure` 已独立交棒的欠账，与 d44 无因果关系，不通过改 d44 基线掩盖。

教训：**接受一个既有 sheet 的行为修复时，应更新该 sheet digest + provider 整体 contract digest；
但绝不能用全量 `--update` 代替归因。先递归列出将变化的每个路径，再只接受有因果链的字段。**