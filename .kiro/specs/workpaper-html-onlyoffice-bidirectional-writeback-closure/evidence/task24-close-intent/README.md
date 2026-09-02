# Task 24 · Command Service forcesave 与 close-intent exactly-one — 验证证据

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10 · Properties: P12 / P13 / P15 / P43 / P64

---

## 1. 建了什么

| 产物 | 路径 | 说明 |
|---|---|---|
| 纯仲裁域 | `backend/app/services/workpaper_sync/close_intent.py` | comparator（最高 `(intent_sequence, id)`）、四条独立失格子判据、promoted 幂等短路、服务边界双记账比对；`assert_at_most_one_open_capture` / `assert_no_live_intent_remains` / `assert_frozen_identity_complete` 三条判据**抽成模块级纯函数** |
| 出站客户端 | `backend/app/services/workpaper_sync/command_service.py` | 凭据自证 → target 归属校验 → null initiator 拒绝 → 短期 JWT 签名 → HTTP 200 语义分类 → destroy 闸 |
| 仓储侧仲裁 | `backend/app/services/workpaper_sync/repository.py` | 可重入 `reconcile_close_intents()`：room row lock 内选 leader、`authorization_stale` 审计 + eligibility epoch/digest 推进、barrier 放行、CAS 建唯一 close-capture |
| 返回码契约 | `backend/data/onlyoffice_callback_state_contract.json` | 七个返回码的 `platform_outcome` / `retryable` / `callback_expected` 真值表（timers 单一真源） |
| 离线守卫 | `backend/tests/workpaper_sync/test_task24_close_intent.py` | 88 例 |
| 真库守卫 | `backend/tests/workpaper_sync/test_task24_close_intent_pg.py` | 94 例 |
| 变异脚本 | `backend/scripts/diagnose/mutate_task24_close_intent_guards.py` | 40 条（M01–M40） |

### 为什么三条判据必须抽成纯函数

内嵌在服务方法里时，正确实现下 `count` 恒为 0/1、`live_intents` 恒为空 —— 短路它们
**不会有任何测试变红**。也就是说内嵌形态下这三条判据*不可证伪*，等于假绿入口。抽成
模块级纯函数并用合成输入喂之后，M18 / M19 / M20 才成为真判据。

---

## 2. leader 仲裁结果

仲裁键 = 最高 `(intent_sequence, id)`。`created_at` **只作审计，禁止参与仲裁**。

### 2.1 运气无关性（luck-independence）

🔴 本任务最容易假绿的地方，且本 spec 已付过一次代价：**Task 23 的第一个并发场景通过了
每一条断言，而被测路径一次都没执行** —— 因为赢家恰好是「无论如何都会赢」的那一条。

close leader 有完全相同的形状：`intent_sequence` 由 `max+1` 生成，于是默认情况下

```
最高 sequence ＝ 最后插入 ＝ created_at 最晚 ＝（多半也是）id 最大
```

四种错误 comparator 会给出同一个答案，怎么改都测不出来。两道防线：

**(a) 每个核心场景跑四种扰动** `none` / `created_reversed` / `sequence_reversed` / `both`。
中间两种让「最高 sequence」与「`created_at` 最晚」**必然分离**。
`test_created_at_does_not_decide_the_leader` 先断言判别性本身
（`highest_seq_equals_latest_created is False`）**再**断言结论 —— 少了第一句，扰动失效时
这条测试会静默退化成恒真。

**(b) 专门的判别性场景** `deterministic_leader_discriminating`（`test_deterministic_leader_is_neither_first_inserted_nor_latest_created_at`）：

四个 participant 真实关闭 → 从 `rows[1] / rows[2]`（**既非首插入也非末插入**）中挑一个
**不是全局最大 id** 的作为 target → 赋予最高 `intent_sequence = 99` 与**最早** `created_at`
（其余各自 +10/+20/+30 分钟）。

于是这个场景里的确定性 leader **既不是首插入、也不是末插入、也不是最晚 `created_at`、
也不是最大 id**：

| 断言 | 值 | 含义 |
|---|---|---|
| `intent_count` | 4 | |
| `target_is_first_inserted` | `False` | 「按插入序取首」会选错 |
| `target_is_last_inserted` | `False` | 「按插入序取尾」会选错 |
| `target_is_global_max_id` | `False` | 「按 id」会选错 |
| `leader_is_latest_created_at` | `False` | 「按 created_at」会选错 |
| `highest_seq_equals_latest_created` | `False` | 判别性成立（两者是不同两条） |
| `leader_equals_target` | `True` | leader 仍是最高 sequence 那条 |
| `leader_sequence` | 99 | |

四种错法**各自确定性地选错**，不依赖随机 id 碰运气。M21（comparator 改回 `created_at`）
实测打红的正是这条 + `test_created_at_does_not_decide_the_leader[*__created_reversed]`，
证明该场景真的在承重。

**结论：要求 4 的场景已存在，无需新增。**

### 2.2 同一 eligibility snapshot 内 leader 稳定

`test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[revoked|expired]`
刻意停在 promotion **之前**（第三个 participant 仍 `active` ⇒ barrier 不放行），于是两次
reconcile 都真的走到 comparator。它与
`test_reconciler_is_reentrant_without_a_second_capture` **不重复**：后者的第二次 reconcile
在 promotion 之后，`already_promoted` 短路直接返回、comparator 一次都没执行 ——
那证明的是「短路有效」而不是「comparator 稳定」。

断言顺序本身是判据设计：**先证明路径真的跑了，再断言结论**。

- `first/repeat_promoted_short_circuit is False` —— 没走幂等短路
- `first/repeat_eligible_count >= 2` —— `max()` 面对的是真选择（只剩一条时「leader 不变」恒真）
- `same_snapshot_open_captures == 0` —— 确认仍在 promotion 之前
- `same_snapshot_same_epoch` / `same_snapshot_same_digest` —— 这才叫「同一个 snapshot」
- `same_snapshot_same_leader is True` —— 结论

---

## 3. 各行为场景与 capture 条数

每个场景都在真实 PostgreSQL 上跑（scratch schema `tmp_task24_ci_<hex>`，结束
`DROP SCHEMA CASCADE`），逐个数 capture。`all_captures` 与 `open_captures` **都**断言
—— partial unique 只管 open 状态，「造过第二条又终结掉」在只看 open 时是隐形的。

| 场景 | 扰动 | 场景数 | `open_captures` | `all_captures` |
|---|---|---|---|---|
| `single__*`（单人关闭，无 predecessor） | ×4 | 4 | 1 | 1 |
| `order_ab__*`（A 先关 B 后关） | ×4 | 4 | 1 | 1 |
| `order_ba__*`（B 先关 A 后关） | ×4 | 4 | 1 | 1 |
| `terminal_before__*`（A predecessor terminal **先于** B close） | ×4 | 4 | 1 | 1 |
| `deterministic_leader_discriminating` | — | 1 | 1 | 1 |
| `leader_disqualified__revoked`（promotion 前撤权） | — | 1 | 1 | 1 |
| `leader_disqualified__expired`（promotion 前 lease 过期） | — | 1 | 1 | 1 |
| `concurrency`（两人**真并发** close） | — | 1 | 1 | 1 |
| `no_successor`（全部失格） | — | 1 | **0** | **0** |

扰动 = `none` / `created_reversed` / `sequence_reversed` / `both`。
合计 **20 个场景恰一条 capture + 1 个场景零 capture**。

补充判据：

- 每个 capture 场景另断言 `promoted_intents == 1` 且 `promoted_with_request == 1`
- 先关闭者建普通 forcesave predecessor、最后关闭者不建，且 `predecessor_links == 1`
  （`ordinary_forcesave_request_id` 真的被写上 —— 该列在 Task 24 之前**没有任何生产代码写过**）
- reconciler 重入不产生第二条 capture（`reentrant_capture_created is False`）
- `test_no_capture_before_predecessors_are_terminal` —— barrier 放行前零 capture
- 并发是**实测而非自述**：`distinct_backend_pids == 2`、`ready_count == 2`、
  `max_t_ready <= min_t_call`（时刻真重叠）、`distinct_sequences == 2`
  （room row lock 真的把 `max+1` 串行化了）
- `test_database_forbids_equal_intent_sequences_so_id_tiebreak_is_defensive_only` ——
  V151 的 `uq_wpoci_sequence` 使同 sequence 在真库**不可达**，故 comparator 里的 id
  tiebreak 是防御性确定性，只能由离线合成输入证明（M03）。该「不可达」前提本身被断言，
  否则约束哪天被去掉，上述结论会悄悄过期而无人变红。

### 3.1 无 successor 的终态

`no_successor` 场景（leader 失格且**无**合法 successor）：

| 断言 | 值 |
|---|---|
| `no_successor` | `True` |
| `capture_created` | `False` |
| `open_captures` / `all_captures` | `0` / `0` |
| `room_superseded` | `True` |
| `room_state` | `recovery_required` |
| `live_after` / `live_intents` | `0` / `0` |
| `reentrant_live` | `0` |
| `reentrant_no_successor` | `True` |
| `reentrant_capture_created` | `False` |
| `intent_states` ⊆ | `{authorization_stale, recovery_required, superseded, error}` |
| `leader_before ∈ stale_reported` | `True` |
| `authorization_stale_events` | `≥ 1` |

即：**不造 request、原子 supersede generation、每条 intent 落显式终态**。
`live_after == 0` 与 `open_captures == 0` 合起来才是完整的「既不永久 blocked、也不第二条」
—— partial unique 对「一条 capture 都没有」毫无意见，这条卡死只能靠行为判据抓。

---

## 4. 通过数

| 项 | 数 |
|---|---|
| 离线守卫 `test_task24_close_intent.py` | **88 passed** |
| 真库守卫 `test_task24_close_intent_pg.py` | **94 passed** |
| 合计（冻结基线） | **182 passed** |

```
py -3 -m pytest backend/tests/workpaper_sync/test_task24_close_intent.py \
                backend/tests/workpaper_sync/test_task24_close_intent_pg.py -q
⇒ 182 passed in 23.86s
```

🔴 **基线沿革（改基线必须写来源）**：`178`（守卫补齐前）→ `180`（M01–M21/M23/M24 批次实测，
batch1 报告即此基线）→ **`182`**（M22 首判 GREEN 后补 2 例
`test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[revoked|expired]`）。
本轮 M15–M40 单次运行的基线实测 **182 passed、失败集合为空集**，与脚本冻结值一致、无 WARN。

---

## 5. 变异检验 M01–M40

四态定义（由 `_mutation_kit` 统一给出，**退出码不作判据**，只看失败测试名集合的差集）：
RED = 新增失败含 `want` · GREEN = 无新增失败（**守卫缺陷**） ·
WRONG-TEST = 有新增失败但不含 `want`（污染残留 / 锚点错位 / **want 误declare**） ·
ANCHOR-MISS = 锚点无法唯一定位或未落盘（**脚本缺陷**）。

**最终结果：M01–M40 全部 RED（40/40）。**

| 批次 | 范围 | 结果 | 报告 |
|---|---|---|---|
| batch1 | M01–M14 | 14/14 RED | `mutation-batch1.json` |
| **batch2（本轮，单次运行）** | **M15–M40** | **26/26 RED** | `mutation-batch2.json` |
| batch2 首轮（留档） | M15–M40 | 25 RED + 1 WRONG-TEST（M40） | `mutation-batch2-firstrun-M40-wrongtest.json` |

历史批次 `mutation-batch3/3b/4/5.json` 是本轮之前被中断的分批尝试的留档，其判定已被
本轮单次运行的 `mutation-batch2.json` 完整覆盖。

### 5.1 全表

| # | 落点文件 | 注入 | want（打红项） | 判定 | 归因 |
|---|---|---|---|---|---|
| M01 | `close_intent.py` | `max` → `min` | `test_leader_is_highest_sequence_even_when_it_is_neither_first_nor_last_inserted` | RED | — |
| M02 | `close_intent.py` | 排序键丢 `intent_sequence`、只按 id | 同上 | RED | — |
| M03 | `close_intent.py` | 排序键丢 id tiebreak（R01 回归） | `test_equal_sequence_falls_back_to_highest_id` | RED | — |
| M04 | `close_intent.py` | `if p.revoked:` → `if False:` | `test_eligibility_has_one_independent_branch_per_disqualifier[revoked]` | RED | — |
| M05 | `close_intent.py` | `if p.expired:` → `if False:` | `…[expired]` | RED | — |
| M06 | `close_intent.py` | 非 `closing` 判据短路 | `…[still_active]` | RED | — |
| M07 | `close_intent.py` | live 状态判据 → `return True` | `…[terminal_intent]` | RED | — |
| M08 | `close_intent.py` | 去掉 promoted 幂等短路（R02 回归） | `test_promoted_short_circuit_precedes_staleness_check` | RED | — |
| M09 | `close_intent.py` | 「零 intent」被当成「全部失格」 | `test_no_successor_is_distinct_from_no_intents_at_all` | RED | — |
| M10 | `close_intent.py` | 不比对 leader | `test_leader_mismatch_raises_arbitration_error` | RED | — |
| M11 | `close_intent.py` | 不比对 `no_successor` | `test_no_successor_mismatch_raises_accounting_error` | RED | — |
| M12 | `close_intent.py` | 不比对 `authorization_stale` | `test_missing_authorization_stale_raises_accounting_error` | RED | — |
| M13 | `close_intent.py` | accounting 继承 arbitration（R04 回归） | `test_close_intent_refusals_are_pairwise_disjoint` | RED | — |
| M14 | `close_intent.py` | `OPEN_CAPTURE_STATES` 变第三份手抄常量（R05 回归） | `test_open_capture_states_are_locked_to_the_sql_index` | RED | — |
| M15 | `close_intent.py` | 仍有 active editor 时不建 predecessor | `test_first_closer_gets_a_predecessor_and_last_closer_does_not[order_ab__none]` | RED | — |
| M16 | `close_intent.py` | 不写 `ordinary_forcesave_request_id` | `test_intent_records_its_predecessor_link_and_timeline` | RED | — |
| M17 | `close_intent.py` | predecessor 转换写错 `to_state`（R03 回归） | 同上 | RED | — |
| M18 | `close_intent.py` | 不再拒 >1 条 open close-capture | `test_more_than_one_open_capture_is_refused[two]` | RED | — |
| M19 | `close_intent.py` | no-successor 后仍有 live intent 时不拒 | `test_live_intent_after_no_successor_is_refused[one_live]` | RED | — |
| M20 | `close_intent.py` | 「非空」写成真值判断（`permission_epoch=0` 被误判缺失） | `test_zero_permission_epoch_and_zero_fence_are_valid` | RED | — |
| **M21** | `repository.py` | 🔴 **comparator 改回 `created_at`** | `test_created_at_does_not_decide_the_leader[order_ab__created_reversed]` | **RED** | — |
| **M22** | `repository.py` | 🔴 **同一 eligibility snapshot 内换 leader**（round-robin：选 leader 时排除当前 leader） | `test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[revoked]` | **RED** | 见 5.2 |
| **M23** | `repository.py` | 🔴 **漏写 `authorization_stale`** | `test_leader_disqualified_before_promotion_yields_a_legitimate_successor[revoked]` | **RED** | — |
| **M24** | `repository.py` | 🔴 **有 successor 仍 blocked**（barrier 永不放行） | `test_capture_scenario_yields_exactly_one_close_capture[order_ab__none]` | **RED** | — |
| M25 | `command_service.py` | 跳过凭据自证 `assert_dispatchable()` | `test_precreated_application_is_refused_before_any_network_call` | RED | — |
| M26 | `command_service.py` | 不再要求 Task 23 凭据类型 | `test_non_credential_argument_is_refused_before_any_network_call` | RED | — |
| M27 | `command_service.py` | 不校验 target 的 room/generation 归属 | `test_target_must_belong_to_the_frozen_request_generation[other_room]` | RED | — |
| M28 | `command_service.py` | null initiator 不再在出站前被拒 | `test_null_initiator_is_refused_before_the_command_service_call` | RED | — |
| M29 | `command_service.py` | 非 200 不再归传输层异常 | `test_non_200_is_a_transport_failure_not_a_return_code` | RED | — |
| M30 | `command_service.py` | body 缺 `error` 不再拒 | `test_unreadable_or_unknown_return_code_fails_visible[missing_error_key]` | RED | — |
| M31 | `command_service.py` | `bool` 不再被拒（`True == 1` 被读成 error 1） | `…[error_is_bool]` | RED | — |
| M32 | `command_service.py` | 无 JWT secret 时不拒（fail-open） | `test_missing_jwt_secret_fails_closed_instead_of_signing_nothing` | RED | — |
| M33 | `command_service.py` | JWT 签成 flat body 而非契约点名的 payload_wrapped | `test_outbound_request_carries_doc_key_request_id_and_signed_short_ttl_jwt` | RED | — |
| M34 | `command_service.py` | `ONLYOFFICE_URL` 为空时不拒 | `test_empty_onlyoffice_url_is_refused_instead_of_defaulting` | RED | — |
| M35 | `command_service.py` | timeout/TTL 改成代码字面量（违反契约单一真源） | 同 M33 | RED | — |
| M36 | `command_service.py` | 可重试错误不再先于 FSM terminal 判定 | `test_retryable_error_is_checked_before_fsm_terminality` | RED | — |
| M37 | `command_service.py` | 超时不再单独成态 | `test_timeout_never_permits_reload_html` | RED | — |
| M38 | `command_service.py` | 崩溃恢复放行条件由合取松成析取 | `test_editor_destroy_gate_branches[crash_durable_but_no_case_refused]` | RED | — |
| M39 | `…callback_state_contract.json` | error 4 `no_changes` → `server_error` | `test_every_contract_return_code_has_a_closed_outcome` | RED | — |
| **M40** | `…callback_state_contract.json` | error 3 `server_error` → `configuration_error` | `test_http_200_with_nonzero_error_is_never_accepted[error3]` | **RED**（修 want 后） | 见 5.3 |

### 5.2 M22 — 首判 GREEN，归因「无效变异」，已换注入形态并补判据

**首轮注入**：让排序键依赖 reconciler **自己写的** `reconciled_at`。**实测 GREEN**。

**归因 = 无效变异（不是守卫缺陷）**：每条 intent 在它自己那次 close 的 reconcile 里就已
成为当时的最高 sequence ⇒ 全部被写上 `reconciled_at`，注入的键分量在整个 eligible 集合上
**恒为同值**、完全不影响 `max()`。唯一它非空的时刻（新 intent 尚未 reconcile）那条恰好
也是 sequence 最高的 —— 两种 comparator 选同一个人，**不可证伪**。

**处置（两件事，缺一不可）**：

1. 换注入形态为 **round-robin** —— 选 leader 时把*当前* leader 排除掉（只剩它时回退全集，
   以免退化成崩溃而非选错）。于是第一次 reconcile 选出 L 后，同一 snapshot 的第二次
   reconcile 必然改选另一条，而 eligible 集合 / epoch / digest 全都没变。
2. 补 2 例 `test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader`。**原判据只有
   「两次 leader 相等」一句，缺「comparator 这次真的跑了」的前置事实** —— 这正是要求 4 所指
   的 Task 23 假绿形态在本条上的复现风险。补的四条前置事实见 §2.2。

基线随之 180 → 182。改后**实测 RED**（本轮单次运行复现）。

### 5.3 M40 — 首判 WRONG-TEST，归因「脚本缺陷」，已修 want

**首轮**：`want` 写的是 M39 那条结构判据 `test_every_contract_return_code_has_a_closed_outcome`，
实测 **WRONG-TEST** —— 实际打红的是
`test_http_200_with_nonzero_error_is_never_accepted[error3]`。

**归因 = 脚本缺陷（want 从 M39 顺手抄来）**。不是守卫缺陷，也不是生产缺陷：

- 该结构判据对 error 3 只断言 `retryable is True`、对 error **4** 才断言 `outcome is no_changes`；
- 本变异把 error 3 的 outcome 换成 `configuration_error` 时**没有动 `retryable`**，
  且 `callback_expected is (outcome is accepted)` 在 `configuration_error` 下依然成立
  ⇒ 该结构判据三条断言**全部不受影响**；
- 真正拥有「error 3 的 outcome 列被消费」这一属性的是行为判据
  `test_http_200_with_nonzero_error_is_never_accepted[error3]`
  （断言 `dispatch.outcome is CommandOutcome.server_error`）。

**处置**：`want` 改指该行为判据。**属性本身自始至终是被锁死的**，修的是期望声明而非判据强度。
`want` 刻意写**不带 `[error3]` 后缀**的裸方法名：kit 的 `_locate_want` 用
`want.split('::')[-1]` 去守卫文件里做子串定位，带 parametrize 后缀的字面量在源码里不存在
（id 由 `ids=[...]` 另行声明），会让 `--list` 判定「want 定位不到」。修后 `--list` 仍 0 退出。

### 5.4 刻意避开的无效变异形态

- 改注释 / docstring —— 不在判据作用域内；
- 绝对 `line=` 定位 —— 行号随上游补类/补注释漂移（Task 22 M02 实测 ANCHOR-MISS）。
  唯一需要消歧的 `no_successor=False,`（两处）用 `scope` + `offset` 相对定位；
- 短路 `assert_timer_single_source` / `_assert_at_most_one_open_capture` 的**内嵌**形态
  —— 正确实现下恒不触发，单独短路必判 GREEN（见 §1）。

### 5.5 复现

```powershell
# 只读锚点自检（秒级、零风险；「变异体系是否还可复现」的最便宜判据）
py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py --check-anchors
# ⇒ 40/40 OK，目标文件 md5 全未变、无 .mutbak 残留

# 声明校验（40 条声明 + 2 个分母文件全部可定位）
py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py --list

# 本轮单次运行
py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py \
  --run M15,…,M40 --out <此目录>/mutation-batch2.json
```

**运行后完整性核验**（本轮实测）：`.mutbak` 残留 **0**（全仓扫描），
`close_intent.py` SHA-256 = `267FF8D23D291C5D…`（与运行前逐字一致），
`repository.py` = `72C037538E741B2C…`、`command_service.py` = `B453F85831BE5DE2…`、
`onlyoffice_callback_state_contract.json` = `895B8EF2A59991B4…`。
还原由 `_mutation_kit.apply.mutated()` 在 `finally` 内完成并逐字节比对 md5，
26 条记录的 `restored` 全为 `true`。

🔴 **中断即污染**：被 `^C` 打断的运行可能留下 `.mutbak` 且目标文件处于变异态 ——
此时基线被污染，**每一条判定都失效**。本轮因此把运行放在后台、不设短超时。
运行前先扫残留（kit 在发现 `.mutbak` 时直接 ABORT）。

---

## 6. 未验证 / 不声称覆盖

1. 🔴 **Command Service 的 HTTP 端点是可编程 stand-in，不是真实 OnlyOffice。**
   离线守卫用 `_RecordingTransport`、真库守卫用 `_ProgrammableTransport`（确定性、可断言
   调用序）。它们覆盖的是「出站请求形态（doc_key / request id / 短期 JWT / timeout 来源）」
   与「HTTP 200 只代表 accepted」这两条**语义**。
   **真实 OO 9.4 的端到端验收是 Task 44 / 70 的闸，本任务不声称覆盖它。**
   契约里 `oo94_observed: false` 的返回码（error 2 / 3 / 5）属协议文档态，未在 9.4 实测到。
2. **前端 destroy 闸只验到后端判定函数**。Property 13 的「timeout 保持 OO、`reloadHtml`
   次数为 0」在本任务由 `command_service` 的闸函数分支判据覆盖；真实浏览器里
   editor destroy 的时序未在此验证。
3. **id tiebreak 在真库不可达**：`uq_wpoci_sequence` 禁止同
   `(room, generation, intent_sequence)`，故 comparator 的 `str(i.id)` 分量只由离线合成
   输入（M03）证明，真实 schema 下走不到。该前提本身已被断言，见 §3。
4. **崩溃恢复 / 后台重放不换 leader** 由「同一 eligibility snapshot 两次 reconcile」建模
   （§2.2）。真实进程崩溃后重启的 recovery 路径属 Task 27 的 recovery case 范畴。
5. **相同 Idempotency-Key 重放先重验授权与 frozen fingerprint** 在本任务只覆盖到
   Command Service 出站前的凭据自证与 target 归属；完整重放语义属 Task 25/27。
6. 🔴 **生产实现文件与守卫文件在 git 中均为未跟踪（`??`）**：
   `close_intent.py` / `repository.py` / `command_service.py` /
   `onlyoffice_callback_state_contract.json` 都不在 HEAD 里，故本轮完整性核验只能以
   **SHA-256 逐字比对**为锚，无法用 `git diff` 复核。工作树一丢即全部蒸发，
   建议尽快入库。
