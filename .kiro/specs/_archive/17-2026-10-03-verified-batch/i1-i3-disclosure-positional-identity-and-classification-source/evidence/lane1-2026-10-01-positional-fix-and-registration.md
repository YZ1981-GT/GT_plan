# Lane 1 · 2026-10-01：位置化行身份修复（Task 4~7）+ 契约字段补齐（Task 14/15）+ 注册实测（Task 17）

## 一、为什么 2026-09-27 那轮被回滚、这轮怎么解

回滚原因是 `test_task51_i_cycle_migration.py` 的两条判据「实测命中 == slice 登记」——缺陷还在才绿。
本轮按 H 循环 `test_h_cycle_registered_defects_fixed.py` 的先例处置：

- 两条判据从 task51 摘出（原位留指针注释），翻面版写进 `backend/tests/workpaper_sync/test_i_cycle_registered_defects_fixed.py`
- slice **不回填**（append-only）：翻面版断言 slice 登记保持 6 / 1 / 4 / 20 原值，同时断言现算为 0
- 扫描口径复用 task51 的 `_positional_identity_hits`，并扩一支 `${added}`（slice 口径漏族 D 两处）

## 二、8 个 site 的处置

| # | 族 | 位置 | 修复前 | 修复后 |
|---|---|---|---|---|
| 1 | A′ | `useI3Disclosure.ts` cgu_allocation | `` `cgu-${i}` `` | 按 CGU 名复用旧 id，否则 `_stableRowId('cgu')` |
| 2 | B | 同上 bookValue | `` `bv-${r.rowId \|\| i}` `` | 上游 rowId 优先 → 按被投资单位复用 → 新生成 |
| 3 | B | 同上 impairment | `` `imp-${r.rowId \|\| i}` `` | 同上 |
| 4 | B | 同上 performance | `` `perf-${r.rowId \|\| i}` `` | 上游 rowId 优先 → 新生成（该分支 performanceRows 恒空，无旧池） |
| 5 | B | `I3TabRecoverableTest.vue` cguList | `` `cgu-${idx}` `` | 按 CGU 名 + 同名次序的确定性 id（`legacyCguRowId`） |
| 6 | B | `i1DisclosureEnhance.ts` draftTitleRowsFromI18 | `` `tc-i18-${r.rowId \|\| i}` `` | 上游 rowId 优先 → 新生成 |
| 7 | D | `useI3Disclosure.ts` seedPerformanceFromBookValue | `` `perf-${Date.now()}-${added}` `` | `_stableRowId('perf')` |
| 8 | D | 同上 seedAssumptionFromCgu | `` `ap-${Date.now()}-${added}` `` | `_stableRowId('ap')` |

### 与 design 的两处偏离（如实登记）

1. **族 A′/B 不是「一律换新生成器」，而是「先按业务值复用旧 id」**。design 只说改生成器 + grandfather，
   但 `pullFromDetailRows` 是覆盖式重建：只换随机生成器，每次「从 I3-2 取数」都会把全部行身份换新
   ⇒ OO 侧看到的是全删全增。按业务值复用同时解决了两件事：删中间行后剩余行身份不变（ID-6）、
   旧格式 `cgu-3` 只要业务值还在就原值保留（ID-P4 grandfather）。
2. **site #5 不用 `useI3Impairment._genRowId` 的随机生成器**。design 要求复用它，但这里是 `computed`，
   每次 `allResponses` 变化都会重算 ⇒ 随机 id 每次保存都变（`cguRowId` 写进 `I3-7-dcf-cgu-*`，
   chip `:key` 也绑它）。改用按 CGU 名的确定性 id，与同文件 `handleLinkToI36` 的
   「rowId 优先 / cguName 兜底」匹配口径一致。代价：缺 rowId 的旧行改 CGU 名会换身份 ——
   只影响上游从未落过 rowId 的旧数据（`useI3Impairment` 新建行都带 rowId）。

## 三、验证

- vitest `composables/__tests__/i3DisclosureRowIdentity.spec.ts` **9 passed**：
  生成器格式 / 旧格式正则 / reuser 逐个消费 / 族 D 同毫秒两次批量不撞 / ID-6 五行删第 3 行 /
  上游 rowId 优先 / 新行新格式 / grandfather `cgu-3` `bv-0` / I1 族 B
- **变异**：把 cgu 改回 `` `cgu-${i}` `` ⇒ vitest 3 红（`expected 'cgu-2' to be 'cgu-3'`，正是数据串行形态）、
  pytest `test_no_positional_identity_left_in_i_cycle` 红；还原后全绿
- pytest `test_i_cycle_registered_defects_fixed.py` 11 passed + `test_task51_i_cycle_migration.py` 121 passed
- vitest I 循环相关 53 文件 975 passed；eslint 0 error（27 条 warning 全为既有）

## 四、Task 14/15 契约

两份契约早已由 provider 生成并通过 `parse_contract` + 双向锁（I3 23,611 B / I1 35,588 B），
本轮只把 provider `review` 里的位置化状态从「修复归 Task 3~9」更新为已修：
`positional_identity_fix_status = fixed_out_of_sheet` + `legacy_positional_ids_grandfathered = true` +
旧格式正则；I3 另加 `positional_identity_persist_chain`。经 `generate_phase5_i_contracts.py --only i{1,3} --apply`
重生成（非手改 JSON），其余 4 份 `--check` 无漂移；`check_sync_provider_golden_digest.py` rc=0（157 digest 不变）。

`positional_identity_sites` 仍为 `[]`：8 个 site 都不在受管 sheet（明细表I1-2 / I3-2）内，
sheet 行身份是 `useI1Detail` / `useI3Detail` 的族 A 安全生成。

## 五、Task 17 注册：真实 PG 实测（保持 `[ ]*`）

探针在真实 PG 上跑 `build_production_registry().register_from_manifest(session=…)`（只读，结尾 rollback）：

- 注册计划：I 循环 6 条 entry **全部绑定**（`contract_id` + `provider_module` 齐，`blocked_reason=None`）
- 实际注册：**0 条**（全库 `registered_adapter_ids = ()`，含 D4 等既有 entry）
- 6 条 I entry 的拒绝原因一致：该 entry 尚无 current published representation（`working_paper_sync_entry_state` 无行；全库仅 1 行）

⇒ 代码侧（台账 + 白名单 + provider + 契约）已就绪，`capability` 变 `bidirectional` 卡在
published representation / approved bundle 的供给（BP-2 / BP-3），不是本 lane 代码能补的；manifest 未手改。

## 六、顺带勘误：假绿复位

三份 spec 中以下 `[x]` 任务没有满足其自身判据的证据，复位为 `[ ]*`：

- roundtrip（foundation 22 / lane1 18 / lane2 19）：判据要求 `sync_test_run_id` 来自真 OO 栈；
  foundation `evidence/task22-roundtrip-blocked.md` 自述阻塞，且真实注册 0 条
- 人工审核 + approved bundle（foundation 24 / lane1 19 / lane2 19a）：`evidence/task24-human-review-blocked.md` 自述阻塞
- 业务确认类（lane1 11a / lane2 6a）：契约里两处仍是 `defect_registered_not_fixed`
- lane2 15a（I2 发布门收敛）：契约仍登记 `gate_layer: host_tab` 未收敛

## 七、全量回归归因（`tests/workpaper_sync` + golden digest 守卫）

- 改后全量：419 failed / 167 errors / 12837 passed（共 84 个文件有红）
- 归因方法：只 `git stash` 本轮 9 个文件（新守卫文件暂时移开），在旧代码上复跑这 84 个文件，按节点 id 对比
- 结果：改后红 569 个节点，旧代码红 558 个。只在改后红的有 14 个，全部在 `test_l1_adapter_registration` / `test_l_lane2_*` / `test_task52_j` / `test_task54_l` / `test_task56_n` 里。这 5 个文件对 I 循环符号 grep 命中 **0**；红的原因是 L/N/J 宿主、契约目录、真库 entry_state 在测试窗口内被并发会话改动（同期工作树 169 条脏文件，例：N4/N5 宿主新挂 notice、`useL*DualMode.ts` 被删）
- ⇒ **本轮引入 0 条**；另有 3 条旧代码红、改后转绿（同样是并发改动带来的，不归功于本轮）
- I 循环直接相关的守卫：`test_task51` 121 passed · `test_i_cycle_registered_defects_fixed` 11 passed · golden digest rc=0
