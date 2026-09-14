# Task 15 收口证据：唯一 `ContentMutationService.commit(...)` 与独立 `RepresentationService`

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 15
Requirements: 2.1 / 2.2 / 2.3 / 2.4 / 3.1 / 3.6 / 6.18 / 8.10 / 8.12 / 13.1
Properties: **P4 / P5 / P10 / P61 / P65 / P67**

## 一、交付物

| 文件 | 责任 |
|---|---|
| `backend/app/services/workpaper_sync/content_mutation.py` | 所有业务 writer 的**唯一** commit 边界：单事务见证、commit 计数闩、revision 域门面、authority 形态门、冲突门、roundtrip 等值、pending mutation 四条拒绝、内容寻址载荷、事件 payload |
| `backend/app/services/workpaper_sync/representations.py` | 独立 `RepresentationService`：只接 approved immutable bundle，为**既有** content version finalize 新 immutable generation 并切 entry pointer；构造上碰不到 revision 域 |
| `backend/tests/workpaper_sync/test_task15_content_mutation.py` | 纯域守卫（80 例，含 2 条 Hypothesis property） |
| `backend/tests/workpaper_sync/test_task15_content_mutation_pg.py` | 真 PostgreSQL 守卫（49 例：xmin 全等、rollback 零可见、幂等重放、finalize additive-only、room 双基线、custom 权威） |
| `backend/tests/workpaper_sync/test_task14_merge_conflicts.py` | Task 14 边界**翻转**：merge 域消费方恰一个且是唯一 commit 入口（178 例） |
| `backend/scripts/diagnose/mutate_task15_commit_representation_guards.py` | 41 条变异 + 四态判定 |
| `evidence/task15-content-mutation/mutation_report.json` | 本次全量变异实跑结果 |

**未新增迁移。** 开工前实扫 `backend/migrations/V*.sql` = 151 个文件、最高 V151
（`V151__workpaper_sync_content_application_bundle_scope.sql`，配 `R151__rollback_…`），
由 Task 9/10 落库，Task 15 只做服务层提交边界。

## 二、四条硬约束怎么落地的

### 1. bidirectional 保存是**单次**业务 commit

`commit()` 的顺序即判据：冻结身份 → 幂等重放 → 冲突门 → materialize/反读/未管理区域
（**全在事务外**）→ publish artifact → **一个** DB 事务写
`revision / content_version / representation / entry_pointer / outbox` → 恰一次提交。

四道互相独立的机制把「先提交 projection-only version 再补一次 revision」变成*不可能*：

| 机制 | 判据在哪 | 可 falsify 由 |
|---|---|---|
| 单一 commit 出口（`_CommitLatch`） | `DoubleCommitError` | M08 |
| 单事务见证（每步取 `pg_current_xact_id()`） | `TransactionSplitError` | M07 · **M20** |
| 五步完整性 | `TransactionStepMissingError` | M06 |
| revision 域门面（`RevisionLockedRepository`） | 调用即抛 | M09 · M10 · **M21** · **M23** |

### 2. 纯 representation/definition 升级**不**递增 content revision

`RepresentationService.__init__` **无条件**把 repository 包成 `RevisionLockedRepository`
—— 即使调用方传裸 repository 也拿不到 `bump_content_revision` /
`set_current_content_version` / `create_content_version`。`finalize_candidate` 沿
`assert_candidate_finalizable`（Task 12）→ `load_bundle_snapshot`（逐 child 校验
kind/state/digest + canonical digest 重算）→ `assert_bundle_snapshot_finalizable`
（typed slot 形态 + `projection_contract` 必须 approved definition contract）→
`assert_publish_order` 校验，成功后 `RepresentationFinalizeOutcome` 直接返回
`content_revision_before/after` 供守卫断言。

### 3. adapter 不 commit / 不递增 revision / 不发事件

`_build_context()` 造的 `SyncContext` 逐字段过 Task 13 的 `assert_no_mutation_surface`；
adapter 的四个方法全部在事务外调用（事务内禁远程下载与 OOXML 大解析）。

### 4. DB 失败只留不可见 orphan

artifact 先 publish 再开短事务；事务失败 ⇒ 文件已在 `.versions` 但**零 DB 行引用**
⇒ 不可见 orphan，由 Task 11 的 reconciliation 收。`TestRollbackLeavesInvisibleOrphan`
四条判据实测：pointer/revision 不变、零新行存活、零提交、文件仍在磁盘且无引用。

## 三、变异四态（全量，41 条）

`.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task15_commit_representation_guards.py --run all`
基线 **307 passed**（80 + 49 + 178），失败名集合为空。

**RED 40 · GREEN 1 · WRONG-TEST 0 · ANCHOR-MISS 0**

唯一的 GREEN 是 **M24**，它是**声明式的等价变异**（`generation = 0 or await …` 恒等于原式）
做反向自检：它必须 GREEN。若它打红，说明某条守卫在数行数/比字符串，那种判据会随任何
无害改动假红。**其余任何 GREEN 都是守卫缺陷。**

| 组 | 变异 | 判据落点 |
|---|---|---|
| bundle/typed slot 拒绝矩阵（R 2.3） | M01–M05 | `test_unapproved_bundle_rejected` / `test_slot_omission_rejected` / `test_invalid_slot_digest_rejected`（4 参数）/ `test_marker_cannot_impersonate_per_entry_contract` / `test_all_zero_authority_digest_rejected` |
| 单事务见证与 commit 计数 | M06–M08 | `test_missing_step_is_its_own_error_type` / `test_split_transaction_is_detected` / `test_commit_latch_allows_exactly_one_commit` |
| revision 域门面（P4） | M09 · M10 | `test_revision_domain_methods_are_unreachable` / `test_forbidden_set_covers_the_three_revision_writers` |
| authority 形态门（R 2.11 / 3.3 / 6.19） | M11–M13 | `test_projection_based_requires_projection` / `…_requires_contract` / `test_custom_authority_rejects_contract` |
| 冲突门（不自动选边） | M14 · M15 | `test_unresolved_conflicts_block_commit` / `test_partial_resolution_is_still_rejected` |
| roundtrip 等值（P65） | M16–M19 | `test_value_drift_is_rejected` / `test_missing_managed_field_is_rejected` / `test_unmanaged_region_drift_blocks_commit` / `test_decimal_is_serialized_without_float_error` |
| **注入式反例**（否定式承诺） | M20–M23 | `test_all_five_writes_share_one_transaction_id`（+47 条连带）/ `test_finalize_succeeded` / `test_finalize_is_one_transaction` |
| 反向自检（等价变异） | M24 | — 必须 GREEN |
| pending mutation 四条拒绝（P10） | M25–M28 | `test_each_rejection_has_its_own_type_and_message`（cross_wp / cross_entry / expired / wrong_base）/ `test_replay_returns_the_same_version_without_new_revision` |
| finalize 的 generation / artifact 身份 | M29 · M30 · M41 | `test_finalize_succeeded` / `test_foreign_candidate_artifact_is_rejected`（foreign_path / forged_digest） |
| finalize 前置原因可分辨（联动 Task 12） | M31 | `test_not_ready_candidate_is_rejected` |
| 事件 payload（R 13.1 / 13.2 / AC 8.12） | M32–M35 | `test_business_commit_payload_has_design_required_keys` / `test_definition_upgrade_payload_marks_revision_unchanged` / `test_event_type_exists_and_matches_design` / `test_new_representation_is_recorded_as_definition_upgrade` |
| room 双基线（AC 2.9 / 8.12） | M36 · M37 | `test_room_entered_refresh_required_with_a_reason` / `test_room_commit_succeeded` |
| 唯一入口与退役登记（P61 / Task 14 翻转） | M38–M40 | `test_revision_bump_has_exactly_one_call_site` / `test_merge_domain_has_exactly_one_production_consumer` |

## 四、首轮四态复盘：5 条非 RED 全部归因并修掉

首轮全量跑出 **RED 33 / GREEN 5 / WRONG-TEST 2**。逐条归因后没有一条是「代码没问题」——
四条是**判据或脚本缺陷**，一条是声明式的自检。这一节是本任务最贵的经验。

| 首轮 | 首轮判定 | 真凶 | 修法 | 复跑 |
|---|---|---|---|---|
| **M15** | GREEN | **脚本缺陷**：`kind=delete` 删的是**多行调用**的首行 ⇒ 后两行成悬空实参 ⇒ SyntaxError ⇒ 文件级 collect ERROR。pytest 的 `-rf` 摘要里**没有任何 failed 名**，而四态判定看的是失败名差集 ⇒ 报 GREEN | 改 `kind=replace`，把调用换成等价元组构造 `_ = (`：语法合法、两个实参照旧求值、唯一消失的就是覆盖检查 | RED |
| **M38** | GREEN | **脚本缺陷**：`insert` 落在 `class ContentMutationService:` 之后 ⇒ 原类体前多出一个顶层 class、类体缺失 ⇒ IndentationError ⇒ 同上退化成 GREEN | 改锚 `__all__` 的收尾 `]`（模块顶层语句边界），并加 `scope_check` 断言注入确实落在第 0 列 | RED |
| **M20** | WRONG-TEST | **采集缺陷（非 fail-open 不足，而是 fail-*too-hard*）**：注入的第二次 commit 让业务 commit 抛错被 ① 段捕获，但紧随其后的快照查询 `SELECT … .one()` 落在任何 per-section `try` 之外 ⇒ `_collect()` 整体抛 ⇒ 45 条 PG 守卫全部 **ERROR**（errors 不进 `-rf` 摘要）⇒ 无新增失败可判 | `_collect()` 加外层 `except`：把异常记进 `snap["errors"]` 并返回部分快照 ⇒ `test_no_harness_errors` 必红。**不是 fail-open** —— 有一条守卫专门断言它为空 | RED（47 条新增失败） |
| **M25** | GREEN | **场景缺陷（合取项互相遮蔽）**：scope 判据是 project/wp/entry 三个独立合取项，而唯一的跨 scope token **同时**换了 wp 与 entry ⇒ 短路 entry 那一项后 wp 那一项照样拦下，异常类型与文案都不变 | 拆成 `cross_wp`（仅 wp 不同）与 `cross_entry`（仅 entry 不同）两条 token，后者断言文案里出现越界的那个 entry | RED |
| **M30** | GREEN | **判据缺失 → 仍遮蔽（改了两轮）**：①首轮 `want="*"` 且无任何用例真的喂错 artifact；②补了「喂另一份 candidate 的字节」后**仍** GREEN —— 那样 relative_path 与 digest **同时**不符，短路任一条另一条都顶上来 | 造「**同字节、异路径**」的孪生 candidate（载荷必须复用同一份 bytes：`_ooxml` 用 `zipfile.writestr(str,…)`，ZipInfo 时间戳取 `time.localtime()`，同参数两次调用字节不同）+ 「真路径 + 伪 digest」的 `forged_digest`，并补配对变异 **M41**（`if False and (`，因为那个 `if` 是多行条件） | 双 RED |
| **M40** | WRONG-TEST | **判据粒度**：`content_mutation.py` 同时 import `merge` 与 `conflicts`，而消费方判据把两域 pattern 合成一张表 ⇒ 删掉 merge 的 import 仍命中 conflicts 那条 ⇒ 计数不变、「零消费方」这一侧不可 falsify | 把 pattern 表拆成 `_MERGE_CONSUMER_PATTERNS` / `_CONFLICTS_CONSUMER_PATTERNS`，并在边界判据里追加断言「登记的消费方必须命中 merge **本体**」（退役登记的 capability 写的就是 `merge_projections / MergeOutcome`） | RED（56 条新增失败） |

### 从这轮复盘提炼的三条通用规则

1. **collect ERROR 会把 GREEN 伪造出来。** 四态判定只看失败名差集，语法被破坏时差集为空
   ⇒ 判 GREEN ⇒ 读者以为「守卫没锁住」，实际是脚本把文件写坏了。凡 `delete`/整行
   `replace` 落在**多行**调用或复合语句上，一律改成语法安全的等价替换
   （`_ = (` / `if False and (`），或换锚点。
2. **合取项必须逐项可 falsify。** 一条 `if a or b or c` 的守卫，只造「a、b 同时违反」的
   场景时，短路 a 会被 b 顶上来 —— 表现为 GREEN，而人会误判成「代码没问题」。每个合取项
   都要有一个**只违反它自己**的场景。本任务踩了两次（M25 的 scope 三项、M30/M41 的
   path+digest 两项）。
3. **采集型 PG 守卫要 fail-closed 到「打红」，不是「报错」。** 模块级 fixture 抛异常时
   全部用例变 ERROR，而 ERROR 不进失败名集合 ⇒ 变异判定拿不到信号。把采集异常收进
   `snap["errors"]` 并留一条专门断言它为空的守卫，才能既不 fail-open 又能被差集看见。

## 五、实跑结果

```
# 三个守卫文件（变异基线）
.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task15_content_mutation.py \
    backend/tests/workpaper_sync/test_task15_content_mutation_pg.py \
    backend/tests/workpaper_sync/test_task14_merge_conflicts.py -q
=> 307 passed, 1 warning in 37.48s

# 辐射面：整个 workpaper_sync 域（Tasks 9~16）
.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync -q
=> 847 passed, 1 warning in 100.36s

# 全量变异
.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task15_commit_representation_guards.py --run all
=> RED 40 / GREEN 1（M24 声明式等价自检）/ WRONG-TEST 0 / ANCHOR-MISS 0
=> 锚点自检 41/41 OK，目标文件 md5 全部还原，无 .mutbak 残留
```

辐射面是按**引用关系反查**得到的：全仓只有 `test_task15_content_mutation.py`、
`test_task15_content_mutation_pg.py`、`test_task14_merge_conflicts.py` 与变异脚本引用这两个
新模块（`representations.py` 与 `content_mutation.py` 互引），故跑 `backend/tests/workpaper_sync`
即完整覆盖，不需要（也不允许）跑全量 `backend/tests`。

## 六、残留观察（不属本任务验收项，登记备查）

1. **`finalize_candidate` 里的 `assert_publish_order` 是冗余带。** 它的
   `approved_stages` 默认值是写死的四阶段全集，因此在真实调用路径上不可能失败。DAG 的
   **非空洞**执行落在更早、更严的两道门：Task 12 的 `assert_candidate_finalizable`
   （缺 approved per-entry contract / 缺 bundle / 非 ready 一律拒，M31 证明拒绝理由落在
   *正确的那一条*）与 `load_bundle_snapshot`（逐 child 校验 kind/state/digest + canonical
   digest 重算，M01–M05 证明可 falsify）。这里**没有**用「从快照推导阶段集合」去伪造
   非空洞性 —— 那样推导出的集合在该调用点必然完整，只是把装饰性换了个写法。
2. **`workpaper_sync/__init__.py` 的模块清单已过期**：仍写着「其余模块
   （content_mutation / representations / room_service / coordinator …）由后续任务加入」，
   而前两个已由本任务交付。未改动：该文件是包级共享文件，且 Task 14 的边界变异（M78）
   以它为注入靶点，改动前应先与并发会话对齐。
