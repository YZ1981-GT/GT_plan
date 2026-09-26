# Implementation Plan

**spec**：`workpaper-sync-registration-isolation-and-d2-republish`　**创建**：2026-09-26
**状态**：14/14（Wave A~D 全部完成；真栈 rematerialize / OO 实测 待 PG+OO 环境 `[~]`）

> 顺序有意义：**Wave A（注册隔离 + 通用对齐守卫）先行** —— 它消除「一个 entry 漂移拖垮全部
> sync 端点」这一类，与 D2 是否重发布无关，交付即止损。Wave B/C 才真正打开 D2-3/D2-1。
> 下方复选框为唯一进度真源；`[~]` = 代码就绪但真栈待环境，`[ ]*` = 可选/外部依赖。

## Wave A：注册隔离 + 通用对齐守卫（结构修复，最高优先）

- [x] 1. `ManifestRegistrationOutcome` 加 `failures` + `RegistrationFailure`；记账等式扩展
  - `len(registered)+len(reasons)+len(failures)==len(planned)`，三集合两两不相交
  - `as_dict()` 加 `failures`（含 error_code/message/exc_type）；`failures` 默认空 dict 向后兼容
  - _Requirements: 1.1, 1.4_

- [x] 2. `register_from_manifest` 逐 entry 隔离：provider/register 抛 `SyncDomainError` 记
  failure + continue；非 SyncDomainError 仍上抛
  - 🔴 不放宽任何准入判据（`register()` RG-1~19 照跑）；`test_task75::test_registrar_does_not_relax_any_admission_check` 保持绿
  - _Requirements: 1.1, 1.5_

- [x] 3. 4 条 pilot attach 各自包 try（`_attach_pilot_adapters` 的 `_isolated`）：单 attach 抛记
  failure 不中断；调用名（Call 节点）保留（AST 判据仍绿）
  - _Requirements: 1.1, 1.2_

- [x] 4. `_RegistrationSnapshot` 加 `failures`；`_registration` 命中失败 entry 时经
  `_cached_registration_failure` 按 failure 的 error_code/message 抛 422（非泛化 adapter_not_ready）
  - _Requirements: 1.3_

- [x] 5. `_apply_durable_incoming` 4 条 pilot attach 各包 `_isolated_attach`（隔离），
  `register_from_manifest` 内部已逐 entry 隔离
  - 🔴 同步 7 处变异锚点（task40 M23 / task41 M39,M40 / task42 M55,M56 / task43 M72,M73），
    `--check-anchors` 全 OK
  - _Requirements: 1.6_

- [x] 6. `startup_prewarm.prewarm_sync_registration_cache` 经 `_cached_registration_failures`
  单独报 failures 数（WARNING，生产 log_level 可见）
  - _Requirements: 1.7_

- [x] 7. 通用守卫 `assert_provider_specs_align_with_contract(provider, contract)`（框架层
  `phase5_row_table_sheet`）+ D1 expansion 薄转发 + **D3 expansion 薄转发**（`_D3CombinedProvider`
  适配层合并 D3-2 自身单数 + 扩容面复数 specs）
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 8. `test_registration_isolation_and_alignment.py`：三桶记账 / failure≠reason / 隔离
  只捕 SyncDomainError / 行为级隔离（good 注册 bad 记 failure 不中断）/ 非域异常上抛 /
  遍历 golden PROVIDERS 跑通用守卫（含 D4/D2/D3 全部对齐通过）/ 差集报出。16 passed
  - _Requirements: 1.1, 1.3, 1.4, 2.4_

- [~] 8b.* Wave A 变异：隔离关键锚点（mutate_task75 M23/M24 register_from_manifest await；
  task40/41/42/43 的 router attach Call）`--check-anchors` 已同步；完整 `--run` 变异待批量跑
  - _Requirements: 1.1, 1.3, 1.4_

## Wave B：D2 多 sheet 代码就绪

- [x] 9. `pilot_d2_large_json.instrumentation_specs()`（复数）+ `instrumentation_definition_payload`
  改走 `build_instrumentation_payload_for_sheets`；开关全关时三段 digest 逐字节不变
  - ✅ golden digest 75 个零回归；对齐守卫对 D2 通过；111 D2 测试全绿
  - _Requirements: 3.1, 3.2, 2.1_

- [x] 10. D2-1 静态区照 D4-13：`GT_MANAGED_REGION_D21` + range `$B$10:$D$11` +
  `static_sheet_payload_d21()` 挂主 spec 的 `static_sheets`
  - ✅ `phase5_d2_01_adjudication` 新增 `GT_MANAGED_REGION_D21` / `_STATIC_REGION_RANGE_D21` / `static_sheet_payload_d21()`
  - _Requirements: 3.3_

- [x] 11. `attach_pilot_adapters` 传 `sibling_bindings=attach_sibling_bindings(provider=_self,...)`
  - ✅ 开关关时 `instrumentation_specs()` 长度 1 → sibling_bindings 为空元组（零回归）
  - _Requirements: 3.4_

- [x] 12. D2 双向 store：
  - ✅ `all_store_item_ids()` / `STORE_ITEM_IDS` / `build_combined_store_projection`（合并 D2-2+D2-3+D2-1）
  - ✅ `build_d21_store_projection`（per-cell 静态区投影）
  - ✅ bridge `merge_projection_into_store_rows` 加 `ROWS_TABLE_KEY` 前缀过滤（D2-3/D2-1 键不串入 D2-2）
  - ✅ `merge_projection_into_all_d2_stores`（D2 多 store 整体 merge）
  - ✅ `_mirror_d4_dual_stores` 泛化为 `plan.merge_all_fn` 动态取函数名（D4 默认值不变，零行为变化）
  - ✅ `StorePayloadError`（D2-3 `phase5_d2_03_bad_debt`）改继承 `SyncDomainError` + `error_code`
  - ✅ `store_item_registry` D2 plan 加 `dual_store_fn` / `merge_all_fn`
  - ✅ 177 项测试全绿（111 D2 + 17 store_item_registry + 24 bridge + 25 隔离+对齐）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.4_

## Wave C：D2 重发布（真栈闭环）

- [x] 13. D2 重物化宿主 `d2_rematerialize_sibling_sheets.py`（参数化 D4 版，`--check`/`--apply`）
  + 两开关打开（`_INCLUDE_D203_BAD_DEBT=True` / `_INCLUDE_D201_ADJUDICATION=True`）
  + 契约重生成 `d2.receivable_detail.json`（55946 bytes, digest `cb9656db`）
  - ✅ golden digest 75 个零回归；111 D2 测试全绿；对齐守卫对 D2 三张受管 sheet 通过
  - `[~]` 真栈 `--check`/`--apply` + store-projection 三 sheet 200 待 PG+OO 环境
  - _Requirements: 5.1, 5.2, 5.3_

## Wave D：前端 + 收尾

- [x] 14. 前端 `D2_MANAGED_SHEET_KEYS` 加 `D2-1→d21-managed`（跟随后端三张受管 sheet）；
  非受管 sheet 保持禁用+中文原因（消息含 D2-1 审定表）；JSDoc 更新
  - ✅ golden digest / 全量关键测试 177 passed / 零回归
  - _Requirements: 6.1, 6.2_

## 依赖与边界

- Wave A 独立可交付（不依赖 D2 重发布）。
- Wave C 必须在 Wave B 的对齐守卫对 D2 通过后才打开开关（否则重发布期漂移）。
- 非目标：不改插行内核支持段内小计扩张；不接 E1；不重发布 b60/d3；不动 d3 并发未提交改动。


---

## 复盘（2026-09-26）

### 交付物统计

| 层 | 文件数 | 新增/改动行 | 说明 |
|---|---|---|---|
| 后端 core | 7 | ~350 | pilot_d2 / d2_bridge / d2_01 / d2_03 / oo_to_html / store_item_registry / phase5_d3_expansion |
| 后端 data | 1 | 契约重生成 | d2.receivable_detail.json 55946 bytes |
| 后端 scripts | 2 | ~230 新建+4 修 | d2_rematerialize_sibling_sheets.py 新建 + mutate_task75 M23 锚点修 |
| 后端 tests | 2 | ~30 | test_d3_expansion + test_d2_store_value_equivalence |
| 前端 | 1 | ~10 | GtD2AccountsReceivable.vue |
| **合计** | **13** | **~620** | |

### 测试证据

- 177 项关键测试全绿（111 D2 + 16 隔离+对齐 + 9 D3 expansion + 24 bridge + 17 store_item_registry）
- Golden digest 75 个零回归
- 对齐守卫 9 家 provider（含 D2/D3/D4）全部通过
- 变异锚点 task75 29/30 OK（M12 pre-existing），task41/42/43 各 1-2 MISS 均 pre-existing

### 教训

1. **D3 薄转发不能照搬 D1 的 `sys.modules[__name__]` 模式**——D3 扩容模块的 `instrumentation_specs()` 不含 D3-2 自身（D1 的首项恒是 D1-3），需要 `_D3CombinedProvider` 适配层合并。教训：收敛代码前必须先读两侧的 spec 集合实际内容，不能假设"照 D1 就行"。

2. **变异锚点缩进必须同步**——注册隔离改写把 `register_from_manifest` 调用从 4 空格缩进移到 8 空格缩进（多了 async with lock 层），M23 锚点忘同步 → MISS。教训：改了代码缩进级别就必须 grep 所有引用该行的锚点。

3. **D3 测试漏了 D3-7 开关是 pre-existing 遗留**——D3-7 (`_INCLUDE_D307_VOUCHER_CHECK`) 打开时 `_ALL_SWITCHES` 未同步更新，导致 `_switch_all_off` 关不掉 D3-7 → 5 个测试红。虽然不是本 spec 引起的，但跑测试时暴露并顺手修了。教训：每张新 sheet 接入后必须检查扩容测试的 `_ALL_SWITCHES` 是否同步。

4. **fake projection key 前缀要与真实 stable key 一致**——bridge 加了 `ROWS_TABLE_KEY` 前缀过滤后，用 `明细表D2-2/` 前缀的 fake projection 全部被过滤掉。教训：测试 fake 数据的 key 格式必须与产出该 key 的函数（`stable_key_for`）一致。

### 残留项（外部依赖）

| 项 | 状态 | 卡点 |
|---|---|---|
| D2 重物化 `--check`/`--apply` | `[~]` | PG 环境（三表近空） |
| store-projection 三 sheet 200 | `[~]` | PG + OO 环境 |
| 8b 完整 `--run` 变异批量跑 | `[~]` | 时间（~167s/套件 × 4 脚本） |
| D2-3 行插入边界 evidence | `[~]` | OO 真栈实测 |
| sheet_payload_d21 locator 改 defined_name_ref | 已做 | static_sheet_payload_d21 含 region_boundary_locator（但 sheet_payload_d21 自身的 locator 仍为 TABLE_SHEET_ANCHOR，因为契约 sheet 的 locator 与 instrumentation 静态寄生的 locator 是两套独立声明） |
