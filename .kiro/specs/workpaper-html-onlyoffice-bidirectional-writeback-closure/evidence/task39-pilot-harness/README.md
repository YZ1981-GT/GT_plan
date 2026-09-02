# Task 39 evidence：pilot harness / source-profile-derived test-run / freshness guard

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 3 Task 39
Requirements: 4.10, 5.8, 6.8, 12.2, 12.10, 12.11, 12.12, 14.1, 14.10, 14.14, 14.16
Properties: **P25 / P26 / P49 / P69 / P70 / P71 / P72**

## 一句话结论

harness 建成了，并且它**拒绝宣称真实 OO pilot 已通过**：一个证据齐全、环境对齐、每条场景
都有自己实体与 trace bundle 的 run，在没有真实 OnlyOffice/浏览器时 `aggregate_result`
落 `failed`（服务端重算给出 `unverified` + `scenario_not_passed`），四类 Excel pilot 全部
`UNVERIFIABLE`，容量 profile 状态恒为 `registered_pending_execution`（owner = Task 71）。

## 交付物

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/services/workpaper_sync/pilot_harness.py` | 新建 | 31 条 scenario oracle 登记表（与 `evidence.py` 双向锁）、19 码 fail-closed rejection、写入侧 harness、P25/P26 与时序 oracle、四类 pilot 覆盖评估 |
| `backend/app/services/workpaper_sync/evidence_freshness.py` | 新建 | AC 14.16 的 bundle / authority / typed-child **三条**失效轴 + 篡改检测 + 组合结论 |
| `backend/app/services/workpaper_sync/capacity_profile.py` | 新建 | AC 14.10/14.12 容量 profile（**只登记**）+ 与 `requirements.md` 原文交叉锁 |
| `backend/app/services/workpaper_sync/evidence.py` | 只加不动 | `StaleReason` 新增成员 `definition_bundle_child_changed`（emit 点在 freshness guard） |
| `backend/app/services/workpaper_sync/merge.py` | 只加不动 | `RETIRED_DEFERRALS` 追加一条：harness 是 merge 域的**只读**消费方 |
| `backend/tests/workpaper_sync/test_task39_pilot_harness.py` | 新建 | 82 例离线守卫 |
| `backend/tests/workpaper_sync/test_task39_pilot_harness_pg.py` | 新建 | 30 例真库守卫（一次 `asyncio.run` 采集 + scratch schema） |
| `backend/scripts/diagnose/mutate_task39_pilot_harness_guards.py` | 新建 | 68 条变异，全部 RED |
| `backend/scripts/diagnose/select_task39_radiation.py` | 新建 | AST 级辐射面选取（19/2296） |
| `backend/tests/workpaper_sync/test_task29_timeline_evidence.py` | 扩一行 | `StaleReason` 分母补 typed-child 轴（AC 14.16 原文「**及其** typed child identities」） |
| `backend/tests/workpaper_sync/test_task15_content_mutation.py` | 扩一段 | 唯一 commit 边界判据接入「只读 merge 消费方」形态，并用 **AST** 证明零写入面 |

无新迁移：harness 只写 V151 已有的 `working_paper_sync_test_run` /
`working_paper_entry_evidence_scenario`，容量 profile 是代码级登记 + canonical digest。

## required scenario set 的推导链与实测分母

```
source-backed manifest（editability / room_model / scenario_profile）
  + capability（manifest 裁决）
  + approved definition bundle → authority model definition artifact → AuthorityModel 枚举
      ↓  evidence.derive_required_scenarios（纯函数，Task 29）
required scenario set  →  digest 冻结进 test run
      ↓  pilot_harness.SCENARIO_ORACLES（双向锁）
每条场景的 oracle + 它需要哪种证据
```

`authority_model` **不是入参**：`SyncTestRunHarness.resolve_bundle_identity()` 从
`bundle row → authority_model_definition_id → artifact.authority_model_type` 读出并按封闭
枚举解析。未知枚举/自由文本 ⇒ `authority_model_not_enumerated`。

实测分母（真 manifest，186 entries，source_digest `b0fd31f1…`，manifest digest `8b4f15a5…`）：

| entry 形态 | 数量 | required set 大小 | 说明 |
|---|---|---|---|
| `single_onlyoffice / editable / shared / xlsx…single` | 178 | **24** | 16 基础 − 2 字段级 + 2 authority 替代 + 8 close |
| `single_onlyoffice / editable / shared / docx…single` | 1 | **26** | 上者 + 2 Word |
| `single_onlyoffice / editable / exclusive / docx…dynamic` | 1 | **18** | 16 + 2 dynamic（room 非 shared ⇒ 无 close） |
| `unreachable / none` | 1 | **0** | ⇒ `plan()` 抛 `empty_required_set`（零场景不算通过） |
| `single_html / editable / exclusive`（profile drift） | 5 | 不可推导 | Task 1/67 欠账，recomputer 记 `profile_cross_rule_drift` |

场景声明总数 = 16 base + 8 close + 2 dynamic + 2 word + 1 single_html + 2 substitutes
= **31** = oracle 表条目数（双向锁）。其中 **17** 条需要真实 OO/浏览器，**2** 条因上游实现
缺口只能 `failed`。

close 谓词 `editable AND (bidirectional OR shared)` 在真 manifest 上命中 **179** 个 entry，
逐个断言 8 条 close 场景齐备（`test_close_scenarios_are_required_for_every_editable_shared_entry`）。

## 每条 Property 的 oracle 落点

| Property | oracle | 判据 |
|---|---|---|
| **P25** | `evaluate_different_field_merge` | 真跑 `merge_projections`；三条同时成立：`conflict_count==0`、merged 的 A 键 == current 侧、B 键 == incoming 侧。只断零冲突挡不住「incoming 整体覆盖」 |
| **P26** | `evaluate_same_field_conflict` | 真跑 merge；冲突存在 + 三值与输入逐一相同 + merged ≠ incoming（未裁决不得采纳 OO 侧） |
| **P49** | `assess_pilot_classes` + `run_scenario_oracle` 的黑盒分支 | 四类由 entry_id 匹配 + `capability=bidirectional` + **服务端重算通过**三者共同决定；只读 manifest 机器字段，**不读** `entry["evidence"]` 自由文本。今天：候选 1/1/3/174，bidirectional **0**，四类全 `unverifiable` |
| **P69** | `SyncTestRunHarness` + Task 29 `EvidenceRecomputer` | `record_scenario` 无 `result` 入参、`finalize_run` 无 `aggregate_result`/`verified_at` 入参；结果分别由 oracle 执行与服务端重算推导 |
| **P70** | `assert_no_reuse_within_run` / `assert_no_reuse_across_entry` | 写入时即拒；真库上借用另一个 entry 的 application id ⇒ `entity_reused_across_entry` |
| **P71** | `evidence_freshness.bundle_stale_reasons` + `assert_bundle_child_inventory_intact` | 补上 Task 29 从未 emit 的两条轴 + 新增 typed-child 轴；bundle 行 digest 与 child 现算值不符 ⇒ `BundleTamperError` |
| **P72** | `capacity_profile` | profile 的七个数字与 `requirements.md` AC 14.10/14.12 原文交叉锁；digest 覆盖每个数字；`assert_capacity_verified(None)` **抛** `CapacityNotExecutedError` |

## 上游缺口的处置（编排器登记的 6 条）

| 缺口 | 处置 |
|---|---|
| 1. `claim_recovery_case` 从不校验 `expected_generation` / `expected_write_fence` / `expected_definition_bundle_sha256` | **登记给 Task 32**，场景 `wrong_prior_confirmation_bundle_fence_contributor_rejected` 的 oracle 带 `upstream_debt` ⇒ 恒 `failed` + `error_code="upstream_gap"`，notes 指名 Task 32。刻意**不是** `unverifiable`：缺的是实现不是环境，否则「接了 OO 就自动变绿」 |
| 2. claim 的 202 响应不带 `shape` | 与缺口 1 同一登记（同一 claim 路径），不单列 |
| 3. `room_latest_durable_application_id/_sequence` 无读路由 | **登记给 Task 32**，场景 `same_application_higher_sequence_fold` 同上，恒 `failed` |
| 4. `GET operations/{id}` 不含 incoming artifact digest | 未接。本任务的 scenario 行**自带** `artifact/projection digest` 字段（AC 12.11），因此不阻塞 evidence 结构；读路由补齐归 Task 28/32 |
| 5. 3 条 bridge 边不可达 / 6. 2 个 bridge 状态不可观测 | 前端 bridge 域（Task 32/33/34），与后端 harness 判据不相交。本任务的 `browser_trace` 证据种类把它们统一表达为「无真实浏览器 ⇒ `unverifiable`」，不伪造可观测性 |

另有一条**已存在**的 schema 欠账原样保留并 fail closed：
`quarantined_rejects_application_and_engine` 在 V151 下无法记成 `passed`
（AC 5.6 的零 application × `ck_wpees_standard_requires_entities`）⇒ harness 记
`unverifiable` + `error_code="scenario_kind_unrepresentable"`，entry 保持未验收。
**未**擅自加 `authorization_reject` kind：那要动 V153 + Task 29/30 四处已锁死的断言，
owner 仍是 `evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS` 里登记的 Task 9 / 39 / 70 链，
建议随 Task 70 全量刷新一起做。

## 变异检验

68 条，**全部 RED**（`--check-anchors` 68/68 唯一命中、只读性核验通过）。分批产物：

| 产物 | 内容 |
|---|---|
| `mutation_batch1_refix.json` | M04/M05/M08/M14 修守卫后 4/4 RED（首轮 M01–M14 是 10 RED / 4 GREEN，落盘失败——目录当时还不存在） |
| `mutation_batch1.json` | M01–M14 修守卫后复跑，**14/14 RED** |
| `mutation_batch2.json` | M15–M27 首轮（8 RED / 4 GREEN / 1 WRONG-TEST） |
| `mutation_batch2_refix.json` | M15/M16/M18/M22/M27 修守卫后 5/5 RED |
| `mutation_batch3.json` | M28–M40，13/13 RED |
| `mutation_batch4.json` | M41–M52 首轮（9 RED / 3 GREEN） |
| `mutation_batch4_refix.json` | M43/M44/M52 修守卫后 3/3 RED |
| `mutation_batch5.json` | M53–M67 首轮（13 RED / 2 GREEN） |
| `mutation_batch5_refix.json` | M59/M63 修守卫后 2/2 RED |
| `mutation_batch6_boundary.json` | M68（只读消费方边界）RED |

首轮 13 条非 RED 的归因与修法 —— 每一条都是**守卫缺陷**，不是代码问题：

| # | 首轮 | 根因 | 修法 |
|---|---|---|---|
| M04 | GREEN | 三种 ref 解析失败共用一码，只断 `kind` ⇒ 形态分支被遮蔽 | 判据加断**诊断文案**（`必须形如` / `无法 import` / `里没有`） |
| M05 | GREEN | 三个样例全落 `ModuleNotFoundError`（`ImportError` 子类）⇒ 宽捕获不可 falsify | 真放盘一个语法错模块，证明 `SyntaxError` 也必须转成分型拒绝 |
| M08 | GREEN | 判据只看 plan 产出的场景 id，少了解析并不改变它 | 改为「把某必需场景的生产符号换成不存在的名字，`plan()` 必须拒」（真库行为判据） |
| M14 | GREEN | want 指向直接调 `evaluate_*` 的判据，而那道门在 `run_scenario_oracle` 里 | 新增走 `run_scenario_oracle` 的「缺三方输入 ⇒ `merge_evidence_missing`」判据 |
| M15 | WRONG-TEST | 确实打红了但不是登记的那条 | `want` 指向新增的「给了三方输入必 passed」判据 |
| M16 | GREEN | **真实数据上分支不可达**：判据用的三方本来就零冲突 | 专门构造一份会冲突的三方 |
| M18 | GREEN | 只测了 current 侧那一半 | 补对称的 incoming 侧（monkeypatch 成「current 整体保留」） |
| M22 | GREEN | 没有任何判据构造过「三值与输入不一致」的冲突记录 | monkeypatch 把 `ConflictRecord.base` 改掉 |
| M27 | GREEN | 判据只比「行结果 == decision 结果」，两者一起变 | 改为「喂 recovery 序列必 passed / 喂 OO 序列必缺阶段」 |
| M43 | GREEN | 触发点用非法枚举值 ⇒ 枚举分支抛同一个码，kind 分支被遮蔽 | 用 `kind='contract'` + **合法** `authority_model_type` 专测 kind 分支 |
| M44 | GREEN | 触发点只用 approved child ⇒ state 分支不可达 | 补 `authority_state='candidate'`，并断言三种成因文案可区分 |
| M52 | GREEN | 判据是源码级 presence：`if False:` 之下 `self._runner_version` 仍留在 raise 体里 | 改行为判据（`session=None` 即可触发，该校验是 `open_run` 第一条语句） |
| M59 | GREEN | 真实 `requirements.md` 上 7 条正则全命中 ⇒ fail-closed 分支不可达 | 用合成副本（改掉数字措辞 + 抽掉 AC 编号）让两条分支各自可达 |
| M63 | GREEN | want 指向 digest 判据，根本不调 `evaluate_capacity_run` | 补「p95 超预算 ⇒ shortfall 且不算达标」直接判据 |

## 测试与门禁实测

* `test_task39_pilot_harness.py` **82 passed**；`test_task39_pilot_harness_pg.py` **30 passed**（合计 112）
* 辐射面（AST 级 import/符号引用 + 测试模块闭包）**19 / 2296** 个测试文件，
  **1311 passed / 2 failed**；两条失败逐一归因后，本任务侧已清零，剩余 1 条属并发会话
  （`word_sdt_engine.py` 未登记进 merge 域退役表 —— Task 59 的债）
* `backend/tests/workpaper_sync/` 全量：**3282 passed / 4 failed**（4 条全部为并发 Task 59 在途：
  `test_task59_word_sdt_engine.py` × 2 + 上述 merge 登记 1 条 + 已被本任务修掉的 matrix 1 条）

四个门禁（收尾实测）：

| 门禁 | 结果 |
|---|---|
| `check_workpaper_writer_revision_gate.py` | `multi_resolver=4`、`unadjudicated_writer=236`、`bypasses_unified_commit=261`、`non_canonical_resolver_only=63`、`total blocking facts=916`、`[BLOCKED]` —— 与基线逐字相同（Task 20 按设计留红） |
| `generate_workpaper_resolver_migration_matrix.py --check` | exit 0，`row_count=78 migrated=14 deferred=64 regressed=0` |
| `generate_workpaper_sync_frontend_contract.py --check` | exit 0，digest `ca3b003aeaad2f154677a9f9e499fd66e306c5ff49882c169ccc720fa0056c5b` |
| `generate_workpaper_sync_manifest.py --check` | exit 0，digest `8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28` |

🔴 收尾时发现并修复了一条**由本任务引入的连锁 stale**：新增三个生产模块让
`backend/data/workpaper_writer_inventory.json` 的 `source_digest` 过期 ⇒ writer gate 提前
以「stale inventory」失败（而不是按设计报 916 条 blocking facts），`test_task30_closure_gate.py`
6 例连带 ERROR。`--apply` 重生成后 writer gate 恢复基线数字；由于
`workpaper_resolver_migration_matrix.json` 的 `matrix_digest` 含 `inventory_digest`，
矩阵也必须随之 `--apply`（`test_task12_canonical_resolver.py::test_matrix_is_fresh` 是它的
唯一判据）。**结论：这两份生成物是一条链，动了 `backend/app` 的生产模块就要一起重生成。**

## 新登记的债

1. **`authorization_reject` scenario kind（V151）** —— 见上文；不做的理由与 owner 已在
   `evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS` 里，建议随 Task 70 一起。
2. **Task 32 的两条 claim/fence 缺口** —— 已在 `pilot_harness.UPSTREAM_DEBT_*` 里成为
   **运行时可见**的 `error_code="upstream_gap"` notes，不是注释。
3. **产物未入库** —— `backend/app/services/workpaper_sync/**`（含 Task 29 的 `evidence.py`）
   与本任务全部新文件在 git 里仍是 `??` 未跟踪。挂进 CI 的 job 在干净 checkout 下会挂。
4. **`word_sdt_engine.py` 未登记进 `merge.RETIRED_DEFERRALS`** —— 并发 Task 59 的债，
   本任务不代改（会覆盖他们在途的登记内容）。
