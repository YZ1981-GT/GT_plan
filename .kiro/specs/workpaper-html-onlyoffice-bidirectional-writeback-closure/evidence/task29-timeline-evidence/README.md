# Task 29 证据：append-only timeline、source-profile-derived test-run/scenario evidence、脱敏与告警

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 5.10, 5.11, 10.7, 12.10, 12.11, 12.12, 13.1, 13.2, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 14.16
Properties: **P52 / P53 / P54 / P68 / P69 / P70 / P71**

## 产物

| 路径 | 作用 |
|---|---|
| `backend/app/services/workpaper_sync/timeline.py` | operation / application / recovery case / close-intent 四条 append-only 流的读取与**投影一致性**判据；七个 locator 的查询面 |
| `backend/app/services/workpaper_sync/evidence.py` | 从 source-backed manifest `editable/room_model/scenario_profile` + capability + authority model 推导 required scenario set；`EvidenceRecomputer` 逐项重算 FK / hash / bundle digest 并判 stale |
| `backend/app/services/workpaper_sync/redaction.py` | 版本化 `RedactionPolicy`：键名层 → allowlist 投影 → 值形态 → URL 形态 → 容器上限，五层 |
| `backend/app/services/workpaper_sync/alerting.py` | 版本化 `AlertRuleRegistry`：阈值/窗口/severity/去重键/恢复条件/runbook，与指标目录**双向锁死** |
| `backend/app/services/workpaper_sync/metrics.py` | 指标目录（唯一词汇表）+ 四级归因 + 禁止把三类终态压成通用 error |
| `backend/data/workpaper_sync_redaction_policy.json` | 脱敏策略真源（读不到即 fail closed，**不** fallback） |
| `backend/data/workpaper_sync_alert_rules.json` | 告警规则真源 |
| `backend/app/routers/wp_sync_router.py` | timeline / recovery-case timeline 两个端点 + 指标 emit 点（读 `outcome.result`，不读「没抛异常」） |
| `backend/tests/workpaper_sync/test_task29_timeline_evidence.py` | 130 条离线判据 |
| `backend/tests/workpaper_sync/test_task29_timeline_evidence_pg.py` | 44 条真库判据（真实行之间的 FK / hash / 跨 entry 复用） |
| `backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py` | 62 条变异（`_mutation_kit.span`，不落 `.mutbak`） |
| `backend/scripts/diagnose/radiation_task29_timeline_evidence.py` | 按真实 import/符号引用反查辐射面 |
| `mutation_report.json` | 62 条四态判定 + 每条 `added/hit/restored_sha256` + 批次出处 |
| `radiation.json` | 39 个受影响测试文件及其命中原因 |

## 基线

```
py -3 -m pytest backend/tests/workpaper_sync/test_task29_timeline_evidence.py \
                backend/tests/workpaper_sync/test_task29_timeline_evidence_pg.py -q
→ 174 passed（130 离线 + 44 真库）
```

## 变异矩阵：62 条全 RED

```
py -3 backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py --check-anchors  # 只读，秒级
py -3 backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py --run <批次>
→ RED 62 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0
```

**分批前台执行后合并**（`mutation_report.json` 的 `batch_provenance` 逐条记录出处）。
不用 `--run all`：62 条单跑约 20 分钟，被 kill 会跳过 `finally`，把生产代码留在变异态。

**判定不看退出码**，只看失败名集合差集；另有独立复核逐条比对
`verdict=RED ∧ added≠∅ ∧ hit≠∅ ∧ restored_sha256 == 当前磁盘 sha256`（6 个生产文件）。
`redaction.py` 被本任务改动后，R01~R14 **整批重跑**（batch1b），否则旧报告里的
`restored_sha256` 记录的是改动前的 sha，无法证明已还原。

### 变异检验抓到的三个守卫缺陷（均已修）

| 变异 | 首轮判定 | 根因 | 修法 |
|---|---|---|---|
| **R03** `_matches_secret_key` 两步顺序交换 | GREEN | **等价变异** —— 判据是合取，`A and B` ≡ `B and A`。10 个探针键（`Authorization` / `authorization_result` / `token_digest` / `digest_token` / `state_authorization` / `sha256_secret` / `x-callback-token` / `stale` / `""` …）交换前后行为逐一相同 ⇒ 恒 GREEN。生产 docstring 却写着「两条判据，顺序不可交换」，是一条**不存在的不变量**。顺带暴露真实缺口：该处**唯一**承载行为的不变量是「角色词豁免只锚定 `segments[-1]`」，而原守卫只有放行侧（`token_digest` 非凭证）断言、屏蔽侧一条都没有 ⇒ 末段锚定实际无守卫 | ①改正 docstring，不再宣称假不变量；②补屏蔽侧断言：`digest_token` / `state_authorization` / `sha256_secret` 必须屏蔽；③变异换成「末段锚定 → 任一段命中即放行」 |
| **R31 / R32** 从 `validate_registry()` 删「alert_required 指标必须有规则」/「13.9 逐条覆盖」两条分支 | GREEN ×2 | 原判据是 `test_registry_self_check_is_clean`（`assert validate_registry(registry) == ()`）。`validate_registry` 的每条分支**在合规数据上恒返回空** ⇒ 删掉任何一条自检仍为空。另两条候选判据（`test_every_requirement_13_9_condition_has_a_rule` / `test_every_alert_required_metric_has_exactly_one_rule`）断言的是**注册表数据**，根本不经过 `validate_registry` | 改为**注入型**判据：摘掉一条「既属 13.9 点名、指标又 alert_required」的规则，再断言各自分支**独有**的措辞恰出现一次。R32 还叠了一层遮蔽 —— 紧随其后的 `for condition in AlertCondition` 兜底分支对同一缺口也会报，所以判据必须断言报的是 **13.9 的中文标签**而不是 enum 名，否则兜底分支会替它顶班 |
| **R57** 把 required-set digest 里的 `scenario_ids` 置空 | GREEN | 原判据是 `test_changing_the_scenario_profile_payload_changes_the_digest` —— 它改的是 `scenario_profile` payload，而 `scenario_profile_digest` 是 digest 里**另一个仍在**的字段，摘掉 `scenario_ids` 它照样绿。**当时全部 5 条 digest 测试都有同一问题**：它们改的输入自己都在 digest 里，所以对「场景清单是否进 digest」全都不敏感。而这正是 P71 的核心 —— 增删一条必需场景后 digest 不变 ⇒ 旧 test run 永不 stale | 补 `test_the_scenario_list_itself_is_part_of_the_digest`：monkeypatch 目录追加一条探针场景，**只**改场景清单，并逐项断言其余六个 digest 输入不变（独立分母，防假红），再断 digest 不等 |

### 新增一条此前单侧锁的变异

`validate_registry` 的加宽方向（`covered_metrics - required_metrics`，规则引用了
`alert_required=False` 的指标）与 R31 是同一条规则的两面，原先只有减少侧有变异。
补 **R38** + `test_a_rule_for_a_non_alert_required_metric_is_reported`：单侧锁的实际后果是
「把指标的 `alert_required` 翻成 False」可以在不动规则表的情况下悄悄解除一类告警的覆盖承诺。
判据改的是**目录**一侧（`dataclasses.replace(..., alert_required=False)` + monkeypatch），
因为改规则一侧会先被 `_parse_rule` 的封闭域校验拦下，测不到 `validate_registry`。

## required scenario set：对真实 186 条 manifest 的实测普查

推导**唯一**输入是 source-backed manifest 的 `editable / room_model / scenario_profile`
+ capability + authority model（Task 73 已闭账），没有第二份平行清单、没有手填。

```
capability  = {'single_html': 5, 'single_onlyoffice': 180, 'unreachable': 1}
editability = {'editable': 185, 'unreachable': 1}          # 三值列，非布尔
room_model  = {'exclusive': 6, 'none': 1, 'shared': 179}

close 谓词命中（editable=true AND (capability=bidirectional OR room_model=shared)）= 179 entry
每 entry 场景数分布 = {0: 1（unreachable）, 18: 1, 24: 178, 26: 1}
```

集合规模：基础集 16 + close 集 8 + dynamic 2 + word 2 + single_html 1；
不可替换集合 14（close / recovery / authorization 三个 family 全员）。

`editable` 是从 `EntryProfile.editable` **单点派生**的布尔视图，三值 `editability`
（`editable/readonly/unreachable`）才是与 V151 `ck_wpstr_editability` 同域的真源 ——
没有引入平行布尔字段。

### 强制场景逐条对账（Task 29 bullet 3）

| bullet 要求 | scenario_id | 覆盖 |
|---|---|---|
| HTML→OO | `html_to_oo` | ✅ 推导 |
| OO→HTML | `oo_to_html` | ✅ |
| identity | `identity_retention` | ✅ |
| different-field merge | `different_field_merge` | ✅ |
| same-field conflict/resolve | `same_field_conflict_resolve` | ✅ |
| frozen-base status 6/2 dedupe | `frozen_base_status_6_2_dedupe` | ✅ |
| same-app higher-sequence fold 不 self-stale | `same_application_higher_sequence_fold` | ✅ |
| 跨 participant 同 key + 不同 kind/payload 均 409 且不泄露旧 ID | `cross_participant_idempotency_409` | ✅ |
| quarantined 拒绝 application/engine | `quarantined_rejects_application_and_engine` | ✅（见下「已登记 schema 欠账」） |
| opaque `version_id` rollback + 跨 wp 同 numeric revision 无碰撞 | `opaque_version_rollback_no_numeric_collision` | ✅ |
| browser crash no-userdata recovery case | `browser_crash_no_userdata_recovery_case` | ✅ |
| authorization-first claim | `authorization_first_recovery_claim` | ✅ |
| 错误 prior confirmation/bundle/fence/contributor 拒绝 | `wrong_prior_confirmation_bundle_fence_contributor_rejected` | ✅ |
| download-only 三实体为 0 | `download_only_zero_three_entities` | ✅ |
| refresh/reopen | `refresh_required_reopen` | ✅ |
| rollback | `rollback` | ✅ |
| single close | `single_participant_close` | ✅ 8 条 close 集 |
| 两用户两种关闭顺序 | `two_user_close_order_a_then_b` / `_b_then_a` | ✅ |
| A terminal 前/后 B close | `b_close_before_a_forcesave_terminal` / `_after_` | ✅ |
| leader revoke/expire 后有 successor | `close_leader_revoked_successor_exactly_one` | ✅ |
| 无 successor 的 `recovery_required` | `close_leader_revoked_no_successor_recovery_required`（`expected_close_captures=0`） | ✅ |
| reconciler 重入 exactly-one | `close_reconciler_reentrant_exactly_one_capture` | ✅ |

**custom/opaque 的字段级替换**：只允许把 `different_field_merge` /
`same_field_conflict_resolve` 两条换成 `authoritative_revision_conflict` /
`no_silent_overwrite`，且允许替换的 authority model 是**枚举**
（`custom_authoritative_ooxml` / `opaque_single_onlyoffice`）。
未知枚举、自由文本理由、替换 close/recovery/authorization 一律
`ScenarioSubstitutionError`（R53 / R54 变异 RED）。**不接受自由文本豁免。**

### 已登记的 schema 欠账（**不是**豁免）

`quarantined_rejects_application_and_engine` 在当前 V151 下**无法以 `result='passed'`
入库**：AC 5.6 要求 quarantined incoming 永不创建 application（`application_ids` 恒空），
而 `ck_wpees_standard_requires_entities` 要求非 `download_only/recovery_reject` 的 passed 行
`application_ids>=1`。两条当前不可同时满足。

处理方式：该场景**仍在** required set 里、**仍必须跑**，`EvidenceRecomputer` 对它记
`scenario_kind_unrepresentable` 且该 entry **保持未验收**。登记只为让「为什么永远差这一条」
可归因，owner 是 evidence schema（V151 需要一个 `authorization_reject` kind）。
R65 变异锁住「已登记欠账与真实失败必须各有独立缺陷码」—— 合成一个码会让真实失败被淹掉。

### manifest profile drift：5 条，owner 不在本任务

`docx/gt-a10-bundle`、`gt-a12-bundle`、`gt-a16-bundle`、`gt-a17-bundle`、`gt-wp-renderer`
是 `single_html + room_model=exclusive`（`room_model_fact =
frontend_endpoint_without_backend_route`）。推导把交叉一致性**委派**给 Task 13 的唯一规则
（`assert_profile_consistent_with_capability`），于是它们变成 5 条**可指名的 profile drift**
并被记成未验收，而不是让整批重算崩掉（R66 变异锁住这一点：改成上抛 ⇒ 这些 entry 会从
AC 12.13 的五类计数里**消失**而不是计为未验收）。欠账 owner 是 Task 1 / 67。

判据刻意**不**断言 drift 的具体条数 —— 那会把 manifest 当前的欠账锁成基线。

## 脱敏：反向泄露测试与两侧锁

反向侧（合成 event 带 token / URL / 嵌套 payload / 异常文本，出来必须已脱敏）：
`TestRedactionReverseLeak` 的 `test_no_credential_shape_survives_projection` /
`test_bytes_never_reach_the_record` / `test_depth_and_container_limits_bound_the_record` /
`test_exception_text_is_scrubbed_and_truncated`，对应变异 R01/R02/R04~R10 全 RED。

allowlist **两侧锁死**：
* 加宽 → `test_no_allowlisted_key_is_a_credential_name`（把凭证键登记进 allowlist 必须在**构造期**拒），变异 R11 RED；
* 清空 → `test_emptying_a_group_is_refused`（任一分组清空即拒），变异 R12 RED；
* 整组缺失 → `test_dropping_a_group_entirely_is_refused`，变异 R13 RED。

生产路径自身也 fail closed：`RedactionPolicy.assert_no_leak()` 对 URL 形态**不跳过**，
而是换成更强判据（每个 URL 子串必须已无 userinfo/query/fragment 且 host 在 allowlist 内
或为占位符）—— 裸跳过会让「整条 URL 根本没进 scrub」也判通过。

## 指标：归因四级 + 三类终态不得压平

`METRIC_CATALOG` 是唯一词汇表（32 条），`AttributionDim` 是唯一标签名词汇表。归因分四级：

* `operation_scoped` —— 必带 room / generation / **requested + canonical** operation / application / participant（六维齐全，R21 变异 RED）；
* `room_scoped` —— room / generation / participant；
* `route_scoped` —— **刻意禁止** participant（R22 变异 RED）。AC 5.1 / 10.9 明文「callback 是 room/generation 级服务事件，不得把 route participant 当唯一作者」；若把 callback 侧指标划成 `room_scoped`，emit 处就只能填 route participant —— 那正是被禁的归因；
* `platform_scoped` —— outbox / orphan / retention 等**语义上没有 room** 的指标。硬塞 `room=unknown` 会让「按 room 聚合」看起来能做、实际全落 unknown 桶。

`FORBIDDEN_GENERIC_ERROR_OUTCOMES` 把 Task 29 点名的三类终态 + 另两类有独立 runbook 的
状态挡在 `workpaper_sync_error_total` 之外，`record_error()` 直接抛并指出该用哪个专用指标
（R23 变异 RED）：`same_application_sequence_fold`、
`cross_participant_idempotency_conflict`、`close_leader_no_successor_recovery_required`、
`refresh_required`、`post_durable_failure`。

**「没抛异常就 +1 成功」的结构性防线**：`record_outcome(result=..., landed=...)` 两参数
**无默认值**（R26 变异 RED）。Task 22 的 `handle_callback` 与 Task 26 的
`apply_durable_incoming` 在 incoming durable 之后**刻意不抛异常**（非零 ack 会让 OO 丢件），
失败落在 `response_error` / `outcome.result` 里。router 侧对应判据：
`test_the_apply_path_reads_the_result_instead_of_assuming_success`（R74）、
`test_the_callback_metric_reads_durable_at_not_a_state_name`（R73，耐久判据只认 immutable
`durable_at`，不认泛化 terminal 名单）、`test_no_metric_emission_uses_a_defaulted_getattr`
（R75，回归变异 —— 带默认值的 `getattr` 在字段名写错时让指标永远记成
`application_created`，而 Volar/vitest/get_diagnostics/HEAD-swap 四层全绿）。

## 辐射面与既存红的归因

```
py -3 backend/scripts/diagnose/radiation_task29_timeline_evidence.py   → 39 个测试文件（全量 2281）
py -3 -m pytest <这 39 个文件> -q -rfE                                  → 2594 passed, 28 failed, 0 error
```

不跑全量（`backend/tests` 下 2281 个测试文件，前台跑会被当成卡死），按**真实
import/符号引用**反查（AST，不是裸词 —— 本 spec 多个 docstring 里逐字写着这些类名）。

28 条既存红**逐条归因，与 Task 29 无关**，且 Task 29 的两个测试文件零失败：

| 条数 | 文件 | 失败形态 | 归属 |
|---|---|---|---|
| 26 | `test_wp_onlyoffice_router.py` | 24 × `assert 404 == 200`、1 × `assert 'Not Found' == '底稿不存在'`、1 × `assert 404 == 403` —— 三种形态同一根因：harness 只 `include_router(router)`，callback/WOPI/health 都挂在 `public_router` 上，路由未注册于是返回 FastAPI 默认 404 | 既存 harness 挂载问题（Task 28 已证明 `include_router(public_router)` 可修，未单方面改） |
| 2 | `test_task21_..._contract_numbers_have_single_source_in_oo_contract`、`test_task22_..._jwt_decoding_lives_only_in_callback_route` | 都追到 Task 24 的 `command_service.py` | Task 30 的门 |

既存红名单里另外 26 条（`test_onlyoffice_word_template_callback.py` 5 条、
`test_onlyoffice_session_lifecycle.py` 11 条、`test_onlyoffice_wopi_auth.py` 10 条，
后两者根因是 **Task 21** 的 room-derived doc_key 多了一次 mock 未喂的 DB 往返）
**不在本辐射面内** —— 那三个文件不 import Task 29 的任何模块，故未运行。

## digest 与共享文件：零 delta

```
py -3 backend/scripts/gen/generate_workpaper_sync_manifest.py --check
→ [OK] manifest digest 8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28
  [SOURCE] 与 [CHECKED] 逐项相等（hosts/mounts/entries/editability/room_model/scenario_profiles）
```

**没有重新生成 manifest**，`manifest_digest` / `profile_source_digest` / `overlay_digest` /
`source_digest` 全部未变 —— 因此无 digest delta 需要归因。

`backend/data/amount_input_migration_status.json` 未触碰。

## AC coverage matrix：stale 标记是既存的，计数未动

```
py -3 backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py --check
→ [MATRIX] ac=170 property=72 task=73 family=14 clean_ac=69 defective_ac=101
  [MATRIX] defects={'no_dependency_edge': 1, 'no_property_oracle': 101, 'self_certified_single_task': 8}
  [FAIL] stale generated matrix（exit 2）
```

**stale 是既存的，不是本任务造成的**：矩阵 mtime 2026-08-27 11:26，而
`design.md` 17:47 与 `tasks.md` 08-28 08:52 都在之后被改过。本任务**未触碰**
requirements.md / design.md / tasks.md 三份文档。

新鲜重算出的统计与 on-disk 文件里记录的 `stats` **逐字段相等**（`ac_count`=170、
`no_property_oracle`=101、`self_certified_single_task`=8、`no_dependency_edge`=1、
`defects_by_earliest_wave` 全同）⇒ 语义内容没变，只有 digest 因别的 task 的文档编辑而
过期。`no_property_oracle=101` 是 **Task 8** 的欠账，**未吸收、未恶化**。

**刻意不重新生成**：该文件是跨 task 共享数据文件，重算会把别人的文档编辑吞进本任务的
改动集，且 delta 无法归因；最终 reconcile 归 **Task 67**。

## 真实覆盖 vs 移交（不夸大）

### 本任务真实闭合

* **bullet 1（append-only timeline）** —— 四条流的读取 + 投影一致性四条独立缺陷码（顺序断裂 / 伪造 event / 服务端时钟回退 / current state 与末 event 分叉，R41~R45 各自 RED；共用一个码会让靠后的遮蔽靠前的，本 spec 已三次踩到）；七个 locator 查询（wp/room/request/participant/operation/recovery case/application/sequence/correlation id，R47/R48 RED）；`assert_server_clock_only()` 锁住排序列只能来自服务端时钟（AC 13.10，R46 RED）；normal accepted 的 nullable-application shell timeline 与「recovery claim 前不得伪造 operation timeline」各有类型级判据（R49/R50 RED）。
* **bullet 2（evidence recomputer）** —— 推导 + 固定 manifest/profile/source digest + 逐项重算 FK/hash/bundle digest + 变更自动 stale，真库侧 44 条（R61~R67 RED）。
* **bullet 3（强制场景集）** —— 见上「逐条对账」，全部**由推导产生**，无第二份平行清单。
* **bullet 4（脱敏 + 告警）** —— 见上两节，反向泄露与合成 event 判据全过。
* **bullet 5（指标）** —— 目录 32 条覆盖 bullet 列举的全部类别，四级归因，三类终态不得压平。

### 明确移交，本任务**不**宣称

* **场景的实际执行与 `sync_test_run` / scenario rows / trace bundle 的实际持久化**归
  **Task 39**（harness）与 **Task 70**（真实 OO 9.4 全 entry 刷新）。本任务交付的是
  *推导器 + 重算器 + 判据*；`EvidenceRecomputer` 与 `AlertRuleRegistry` 当前**只有测试
  调用方**（`app/services/workpaper_sync/__init__.py` 导出面之外零生产调用），这是
  Task 39/70 的接线点，不是本任务漏接 —— 如实登记，不当作已闭环。
  `timeline` / `redaction` / `metrics` 三者已有生产调用方（router → timeline；
  timeline → redaction；router + alerting → metrics）。
* **P52 / P53 / P54（outbox 仅 commit 后发布 / replay 保留完整 payload / after-save 失败
  可重试）** 的**事务级**证据在 Task 16 的 durable outbox（`test_task16_durable_outbox_pg.py`）
  与 Task 18 已建立；本任务侧只锁「timeline/指标不得从『没抛异常』推断成功」这一面，
  以及 outbox 堆积的指标与告警规则（`workpaper_sync_outbox_backlog`）。
  前端刷新一侧归 **Task 35**。
* **`multi_resolver`** 判据自 Task 20 移交 **Task 30**，本任务不涉及。
* **Task 20 的 writer gate 仍按设计为红**（236 `unadjudicated_writer` + 261
  `bypasses_unified_commit` 是真实迁移欠账）。本证据目录**没有任何产物**把平台表述为
  writer-clean。
* Task 27 把 `oo_to_html.DEFERRED_ADJUDICATION_CONSUMER` 翻成
  `RETIRED_ADJUDICATION_CONSUMER`；退役登记表**保留不删**，本任务未动。

## 🔴 产物入库状态：仍是 `??` 未跟踪

```
?? backend/app/services/workpaper_sync/            （整包自 Task 9 起未跟踪）
?? backend/data/workpaper_sync_redaction_policy.json
?? backend/data/workpaper_sync_alert_rules.json
?? backend/tests/workpaper_sync/
?? backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py
?? backend/scripts/diagnose/radiation_task29_timeline_evidence.py   （本任务新增）
?? .kiro/specs/.../evidence/task29-timeline-evidence/               （本任务新增）
```

这是**整个 spec** 的既存状态，不是 Task 29 引入的。两条后果照旧成立：①挂进 CI 的 job
在干净 checkout 下必挂（文件不存在）②工作树一丢全部蒸发。**未自行 commit**（未获授权），
在此登记待 add。
