"""Task 15 变异检验：唯一 `ContentMutationService.commit(...)` 与独立
`RepresentationService` 的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 15
Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.6, 6.18, 8.10, 8.12, 13.1
Properties: P4 / P5 / P10 / P61 / P65 / P67

═══ 变异改的是**生产代码**，不是守卫 ═══

落点四处：

* `workpaper_sync/content_mutation.py` —— 单事务见证、commit 计数、revision 域门面、
  authority 形态门、冲突门、roundtrip 等值、pending mutation 四条拒绝、内容寻址载荷、
  事件 payload
* `workpaper_sync/representations.py` —— bundle/slot 拒绝矩阵、finalize 的
  DAG/artifact 身份/generation 推算、纯表示不推 revision
* `workpaper_sync/resolution.py` —— finalize 前置的 approved contract 判据（Task 12
  的门，本任务的 finalize 直接消费它；短路它用来证明「未 ready 拒绝」这条判据落在
  **正确的原因**上而不是随便一条异常）
* `workpaper_sync/merge.py` —— 退役登记（Task 14 的边界判据在本任务翻转为「消费方
  恰一个」，退役登记是那条判据的期望值来源）

判定四态：打红=RED（守卫有效）；不红=GREEN（**守卫缺陷**，逐条归因修守卫，绝不降标）；
红了但不是预期项=WRONG-TEST（污染残留 / 锚点错行）；锚点未命中或命中多处=ANCHOR-MISS
（脚本缺陷）。

═══ 本任务的核心难点：原子性是**否定式承诺**，短路变异证明不了 ═══

「五张表同生共死」「绝不先提交 projection-only version 再补一次 revision」「失败后
pointer/revision 不变」这些承诺，源码里根本没有对应的语句可以短路 —— 删掉判据只会
让判据消失，不会让被禁行为出现。所以 M20~M24 全是**注入**（Task 12 的 M51、Task 14
的 M74~M78 是同一个方法论）：

* **M20 注入第二次 `session.commit()`**（content version 写完后立刻提交）
  ⇒ 后半段落到新事务 ⇒ 数据库 `xmin` 不再全等 + `after_commit` 计数变 2
  ⇒ 三条独立判据同时红。这正是被明令禁止的「projection-only commit 后再补」形态。
* **M21 往纯表示路径注入 revision bump** ⇒ `RevisionLockedRepository` 恒抛
  ⇒ finalize 失败 ⇒ 「纯表示升级不推 revision」这条可 falsify。
* **M22 注入 finalize 中途 commit** ⇒ finalize 的 xmin 分裂。
* **M23 注入 `set_current_content_version` 到纯表示路径** ⇒ 证明门面挡的不只是
  `bump_content_revision` 一个方法。
* **M24 注入「跳过 representation 写入」**（把 create_representation 结果丢弃前先
  记一次 outbox）—— 见该条 `why`。

═══ 已知的判据设计取舍（写在这里免得下一个人重踩）═══

1. **多行调用不可整行替换**：`await self._repo.create_representation(` 这类跨行调用
   替换首行会破坏语法 ⇒ 文件级 collect ERROR ⇒ 判定退化成 WRONG-TEST。本脚本一律
   改**单行条件**或用 `insert` 注入。
2. **`if False:` 短路某些校验会让下游抛同类型异常**：例如关掉 `assert_bundle_snapshot_
   finalizable` 的 approved 判据后，DB 的 `trg_wpcr_identity` 仍会拒绝 ⇒ 行为「看起来
   一样」。这类位置的 `want` 必须落在**单元**守卫（纯域、无 DB 兜底）上。
3. **PG 判据的 want 必须选那条真会变的用例**：例如 M20 的 `xmin` 判据在
   `TestSingleTransactionAtomicity`，而 `test_no_harness_errors` 也会跟着红
   （采集里的 commit 抛异常）—— 两者都列进 `wants`，避免被判 WRONG-TEST。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task15_commit_representation_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task15_commit_representation_guards.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task15_commit_representation_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task15-content-mutation/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CM = "backend/app/services/workpaper_sync/content_mutation.py"
REP = "backend/app/services/workpaper_sync/representations.py"
RESOLUTION = "backend/app/services/workpaper_sync/resolution.py"
MERGE = "backend/app/services/workpaper_sync/merge.py"

#: 覆盖面分母：Task 15 的三个守卫文件（含 Task 14 那个被翻转的边界文件）。
GUARD_FILES = {
    "test_task15_content_mutation.py":
        "Task 15 新建（纯域）：bundle/slot 拒绝矩阵、revision 域门面、单事务见证三态、"
        "plan/mutation 形态、authority 形态矩阵、冲突门、roundtrip 等值（含 Hypothesis）、"
        "真文件 stage/roundtrip、事件 payload、内容寻址载荷、Property 61 唯一入口、任务边界",
    "test_task15_content_mutation_pg.py":
        "Task 15 新建（真 PostgreSQL）：五张表 xmin 全等 + after_commit 计数、"
        "rollback 只留不可见 orphan、双 revision 形态不可能、Property 10 幂等与三类拒绝、"
        "candidate finalize additive-only、room 双基线、custom 权威路径",
    "test_task14_merge_conflicts.py":
        "Task 14 边界（本任务翻转）：merge 域消费方恰一个、ContentMutationService 定义恰一处、"
        "退役登记完整",
}

U = "test_task15_content_mutation"
PG = "test_task15_content_mutation_pg"
U14 = "test_task14_merge_conflicts"

MUTATIONS: list[Mutation] = [
    # ══ 一、bundle / typed slot 拒绝矩阵（Requirement 2.3 的四条禁令）════
    Mutation(
        id="M01", side="be", path=REP, kind="replace",
        anchor="    if bundle.state is not DefinitionState.approved:",
        new="    if False:",
        want=f"{U}.py::TestBundleRejectionMatrix::test_unapproved_bundle_rejected",
        why="unapproved bundle 竟可 finalize published representation ⇒ Requirement 2.3 的"
            "「只有 approved bundle」失效。判据必须落在**服务层**：DB 的 trg_wpcr_identity "
            "也会拒，但那条门管不住「服务层先用它算 identity 再写别处」",
    ),
    Mutation(
        id="M02", side="be", path=REP, kind="replace",
        anchor="    missing = [slot.value for slot in BundleSlot if slot not in bundle.slots]",
        new="    missing = []",
        want=f"{U}.py::TestBundleRejectionMatrix::test_slot_omission_rejected",
        why="slot omission（三 typed slot 少一个）被放过 ⇒ 「不得以缺字段代替版本化 typed "
            "null marker」失效。omission 与「slot 值非法」是两条独立禁令，各有各的变异",
    ),
    Mutation(
        id="M03", side="be", path=REP, kind="replace",
        anchor="        if not is_digest(spec.slot_digest):",
        new="        if False:",
        want=f"{U}.py::TestBundleRejectionMatrix::test_invalid_slot_digest_rejected",
        why="空串 / 全零 / 非小写 hex 的 slot digest 被放过 ⇒ Requirement 2.3 原文点名的"
            "四种非法空值全部失守（全零 hash 是最隐蔽的一种：它「看起来像 digest」）",
    ),
    Mutation(
        id="M04", side="be", path=REP, kind="replace",
        anchor="        if not contract_slot.is_definition:",
        new="        if False:",
        want=f"{U}.py::TestBundleRejectionMatrix::test_marker_cannot_impersonate_per_entry_contract",
        why="`projection_contract` 入口用 typed null marker 冒充 per-entry contract ⇒ "
            "结构化底稿退化成 contract-less 模式而 bundle 看起来「完整」（Requirement 6.19）",
    ),
    Mutation(
        id="M05", side="be", path=REP, kind="replace",
        anchor="    if not is_digest(bundle.authority_model_definition_sha256):",
        new="    if False:",
        want=f"{U}.py::TestBundleRejectionMatrix::test_all_zero_authority_digest_rejected",
        why="authority model digest 全零被放过 ⇒ representation 绑定的「权威模型」不可校验。"
            "与 M03（slot digest）分开是因为 authority 不是三个 slot 之一，短路一处不影响另一处",
    ),

    # ══ 二、单事务见证与 commit 计数（判定逻辑本身）════════════════════
    Mutation(
        id="M06", side="be", path=CM, kind="replace",
        anchor="        missing = [step for step in self._required if step not in seen_steps]",
        new="        missing = []",
        want=f"{U}.py::TestTransactionWitness::test_missing_step_is_its_own_error_type",
        why="缺步骤不再报错 ⇒ 「只提交 projection、不写 representation」这一半被禁形态"
            "在见证层失去判据。它与「事务分裂」是两个异常类型，短路一个不会被另一个遮蔽",
    ),
    Mutation(
        id="M07", side="be", path=CM, kind="replace",
        anchor="        if len(distinct) != 1:",
        new="        if False:",
        want=f"{U}.py::TestTransactionWitness::test_split_transaction_is_detected",
        wants=(
            f"{U}.py::TestTransactionWitness::test_property_witness_passes_iff_all_steps_share_one_xid",
        ),
        why="事务分裂不再报错 ⇒ 中途 commit/rollback 可以悄悄发生。这条与 M20（真注入第二次"
            " commit）是一对：前者证明判据存在，后者证明被禁行为真的会被它抓到",
    ),
    Mutation(
        id="M08", side="be", path=CM, kind="replace",
        anchor="        if self._count:",
        new="        if False:",
        want=f"{U}.py::TestTransactionWitness::test_commit_latch_allows_exactly_one_commit",
        why="commit 闩失效 ⇒ 一次业务 mutation 可以提交两次。判据同时断言「第二次在真正 "
            "commit **之前**被拦住」（session.commits 仍为 1），否则闩只是事后记账",
    ),

    # ══ 三、revision 域门面（Property 4 的构造式实现）═══════════════════
    Mutation(
        id="M09", side="be", path=CM, kind="replace",
        anchor="        if name in REVISION_DOMAIN_WRITE_METHODS:",
        new="        if False:",
        want=f"{U}.py::TestRevisionLockedRepository::test_revision_domain_methods_are_unreachable",
        wants=(
            f"{U}.py::TestRevisionLockedRepository::test_representation_service_wraps_even_a_bare_repository",
        ),
        why="门面变成透传 ⇒ 纯表示路径重新**碰得到** revision 域。这是 Property 4 从"
            "「构造上不可能」退回「注释里禁止」的那一步",
    ),
    Mutation(
        id="M10", side="be", path=CM, kind="replace",
        anchor='        "create_content_version",',
        new='        "create_content_version_DISABLED",',
        want=f"{U}.py::TestRevisionLockedRepository::test_forbidden_set_covers_the_three_revision_writers",
        wants=(
            f"{U}.py::TestRevisionLockedRepository::test_revision_domain_methods_are_unreachable",
        ),
        why="禁用名单漏掉 `create_content_version` ⇒ 纯表示升级可以自己造 content version。"
            "守卫反查 repository.py 里所有动 revision 域的方法并要求逐个进名单 ——"
            "「只声明名单不校验」等于名单可以被悄悄改空",
    ),

    # ══ 四、authority 形态门（Requirement 2.11 / 3.3 / 6.19）═══════════
    Mutation(
        id="M11", side="be", path=CM, kind="replace",
        anchor="            if mutation.projection is None:",
        new="            if False:",
        want=f"{U}.py::TestAuthorityShapeMatrix::test_projection_based_requires_projection",
        why="projection-based 入口收到 authoritative 字节也放行 ⇒ 结构化底稿被当成不透明"
            "文件提交，受管字段与 projection hash 全部失真",
    ),
    Mutation(
        id="M12", side="be", path=CM, kind="replace",
        anchor="            if plan.contract is None:",
        new="            if False:",
        want=f"{U}.py::TestAuthorityShapeMatrix::test_projection_based_requires_contract",
        why="缺 per-entry contract 仍放行 ⇒ Requirement 3.3 的「不得降级为 contract-less "
            "模式」失效。它与「缺 adapter」共用异常类型，故守卫断言各自的文案片段",
    ),
    Mutation(
        id="M13", side="be", path=CM, kind="replace",
        anchor="        if plan.contract is not None:",
        new="        if False:",
        want=f"{U}.py::TestAuthorityShapeMatrix::test_custom_authority_rejects_contract",
        why="custom/opaque 入口携带 per-entry contract 被放过 ⇒ 「contract slot 必须是"
            "版本化 typed null marker」与「custom 不被强制 instrumentation」两条同时失守",
    ),

    # ══ 五、冲突门（不自动选边）═══════════════════════════════════════
    Mutation(
        id="M14", side="be", path=CM, kind="replace",
        anchor="            if not mutation.resolution_choices:",
        new="            if False:",
        want=f"{U}.py::TestConflictGate::test_unresolved_conflicts_block_commit",
        why="有冲突却零裁决时直接提交 ⇒ merged 只是「hold 在 current」的快照，等于服务端"
            "替审计师选了 current 那一边（AC 8.1 明令不自动选边）",
    ),
    Mutation(
        id="M15", side="be", path=CM, kind="replace",
        anchor="            assert_all_conflicts_resolved(",
        new="            _ = (",
        why="删掉逐条覆盖检查、只留「裁决非空」⇒ 交一条裁决就能提交 N 条冲突。"
            "这条与 M14 是两个层次：前者是「有没有裁决」，本条是「裁决够不够」。"
            "🔴 不能用 `kind=delete`：该调用是**多行**的，删掉首行会让后两行成为悬空"
            "实参 ⇒ SyntaxError ⇒ 文件级 collect ERROR ⇒ pytest 的 `-rf` 摘要里没有任何"
            "failed 名 ⇒ 四态判定报 GREEN（首轮实测就是这个假象，真凶是脚本不是守卫）。"
            "改成把调用换成等价元组构造 `_ = (…)`：语法合法、两个实参照旧求值、"
            "唯一消失的就是覆盖检查本身",
        want=f"{U}.py::TestConflictGate::test_partial_resolution_is_still_rejected",
    ),

    # ══ 六、roundtrip 等值（Property 65）══════════════════════════════
    Mutation(
        id="M16", side="be", path=CM, kind="replace",
        anchor="            if not values_equal(mine.value, theirs.value, mine.value_type):",
        new="            if False:",
        want=f"{U}.py::TestRoundtripEquivalence::test_value_drift_is_rejected",
        wants=(
            f"{U}.py::TestRoundtripEquivalence::test_three_failure_reasons_have_distinct_messages",
        ),
        why="反读值漂移被放过 ⇒ Property 65「projection 与同 revision representation 等值」"
            "彻底失效：库里记的 projection hash 与 OOXML 里的实际值可以不同",
    ),
    Mutation(
        id="M17", side="be", path=CM, kind="replace",
        anchor="        missing = sorted(set(left) - set(right))",
        new="        missing = []",
        want=f"{U}.py::TestRoundtripEquivalence::test_missing_managed_field_is_rejected",
        wants=(
            f"{U}.py::TestStageAndVerifyWithRealFiles::test_roundtrip_gap_blocks_before_any_db_write",
        ),
        why="materialize 漏写受管字段被放过 ⇒ 「HTML 里填了、OO 里没有」而 commit 成功。"
            "第二个 want 走**真文件**路径，证明判据不只在纯函数层生效",
    ),
    Mutation(
        id="M18", side="be", path=CM, kind="delete",
        anchor="        unmanaged.assert_equivalent()",
        want=f"{U}.py::TestStageAndVerifyWithRealFiles::test_unmanaged_region_drift_blocks_commit",
        why="未管理区域漂移不再阻断 ⇒ 公式/样式/drawing/chart 被 materialize 重写后照样"
            "发布（Requirement 3.5 / 6.10）",
    ),
    Mutation(
        id="M19", side="be", path=CM, kind="replace",
        anchor='        return format(value, "f")',
        new="        return float(value)",
        want=f"{U}.py::TestProjectionPayload::test_decimal_is_serialized_without_float_error",
        why="金额用 float 序列化 ⇒ `Decimal('0.1')` 变 0.1 的二进制近似，同一份业务内容"
            "两次算出不同 digest ⇒ AC 3.6 的「相同 projection 幂等复用」永不成立",
    ),

    # ══ 七、注入式反例：否定式承诺只能靠注入证明 ════════════════════════
    Mutation(
        id="M20", side="be", path=CM, kind="insert",
        anchor='            await witness.stamp(self._session, "content_version")',
        new="            await self._session.commit()\n",
        want=f"{PG}.py::TestSingleTransactionAtomicity::test_all_five_writes_share_one_transaction_id",
        wants=(
            f"{PG}.py::TestSingleTransactionAtomicity::test_exactly_one_database_commit",
            f"{PG}.py::TestSingleTransactionAtomicity::test_service_witness_agrees_with_database",
            f"{PG}.py::TestHarness::test_no_harness_errors",
        ),
        why="🔴 **注入**：content version 写完立刻提交 —— 这正是 Requirement 3.1 明令禁止的"
            "「先提交 projection-only version，再补 artifact/revision」形态。"
            "「五张表同生共死」是否定式承诺，源码里没有语句可短路，只能注入反例"
            "（同 Task 12 的 M51 / Task 14 的 M74~M78）。三条独立判据同时红："
            "数据库 xmin 不再全等、after_commit 计数变 2、服务见证与 xmin 不符",
    ),
    Mutation(
        id="M21", side="be", path=REP, kind="insert",
        anchor='            await witness.stamp(self._session, "representation")',
        new="            await self._repo.bump_content_revision(cand_wp_id, 0)\n",
        want=f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_finalize_succeeded",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
            f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_revision_and_old_rows_untouched",
        ),
        why="🔴 **注入**：往纯表示 finalize 里塞一次 business revision 递增。"
            "Property 4 的「纯 template/instrumentation/contract/bundle/representation "
            "变化不得推进 content_revision」是否定式承诺 —— 本条一红即证明 "
            "`RevisionLockedRepository` 不是装饰性注释，而是真的把这条路堵死了",
    ),
    Mutation(
        id="M22", side="be", path=REP, kind="insert",
        anchor='            await witness.stamp(self._session, "entry_pointer")',
        new="            await self._session.commit()\n",
        want=f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_finalize_is_one_transaction",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
            f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_finalize_succeeded",
        ),
        why="🔴 **注入**：finalize 中途提交 ⇒ representation/pointer/candidate/outbox 分裂到"
            "两个事务。「失败时原 pointer 不变」依赖的正是「它们同生共死」——"
            "分裂之后一半提交一半回滚，pointer 会指向一个 candidate 仍是 staged 的世界",
    ),
    Mutation(
        id="M23", side="be", path=REP, kind="insert",
        anchor="            pointer_moved = False",
        new="            await self._repo.set_current_content_version(cand_wp_id, cand_version_id)\n",
        want=f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_finalize_succeeded",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
        ),
        why="🔴 **注入**：纯表示路径去动 `working_paper.current_content_version_id`。"
            "与 M21 分开是为了证明门面挡的**不只是** `bump_content_revision` 一个方法 ——"
            "禁用名单三个成员各自可 falsify（M10 管名单本身，M21/M23 管两个真实调用形态）",
    ),
    Mutation(
        id="M24", side="be", path=CM, kind="replace",
        anchor="            generation = await next_representation_generation(",
        new="            generation = 0 or await next_representation_generation(",
        want="*",
        why="等价变异（`0 or X` 恒等于 X）—— **刻意**放一条无行为差异的变异做**反向自检**："
            "它必须判 GREEN。若它意外打红，说明测试对源码文本敏感（例如某个守卫在数行数、"
            "比字符串），那种判据会随任何无害改动假红。"
            "本条是唯一允许 GREEN 的变异，其余任何 GREEN 都是守卫缺陷",
    ),

    # ══ 八、pending mutation 四条拒绝（Property 10）═══════════════════
    Mutation(
        id="M25", side="be", path=CM, kind="replace",
        anchor="            or row.entry_id != plan.entry_id",
        new="            or False",
        want=f"{PG}.py::TestProperty10Idempotency::test_each_rejection_has_its_own_type_and_message",
        why="pending mutation 的 entry scope 校验被短路 ⇒ 另一个 entry 的 token 可以用来"
            "提交本 entry 的内容（Property 10 的「token 跨 scope 必须拒绝」）。"
            "改**一个条件行**而不是整个多行 `if`：后者会破坏续行语法 ⇒ collect ERROR。"
            "🔴 判据靠 `cross_entry` 这条**仅 entry 不同**的 token：首轮只有一条 wp 与 "
            "entry 同时不同的 token，短路 entry 那一项后 wp 那一项照样拦下、异常类型与"
            "文案都不变 ⇒ 判 GREEN。拆成 cross_wp / cross_entry 两条后，entry 合取项"
            "被短路时拒绝理由退化成 `PendingMutationPayloadError`，参数化用例必红",
    ),
    Mutation(
        id="M26", side="be", path=CM, kind="replace",
        anchor="        if row.expires_at <= _now():",
        new="        if False:",
        want=f"{PG}.py::TestProperty10Idempotency::test_each_rejection_has_its_own_type_and_message",
        why="过期 token 仍可消费 ⇒ 短 TTL 形同虚设（Property 10 的「过期必须拒绝」）。"
            "守卫按**三条各自的异常类型 + 各自文案**断言，因此本条与 M25/M27 互不遮蔽",
    ),
    Mutation(
        id="M27", side="be", path=CM, kind="replace",
        anchor="        if int(row.expected_revision) != int(plan.expected_revision):",
        new="        if False:",
        want=f"{PG}.py::TestProperty10Idempotency::test_each_rejection_has_its_own_type_and_message",
        why="同 Idempotency-Key 不同 content base 被放过 ⇒ 旧 base 的 payload 可以盖掉"
            "新内容（Property 10 的「同 key 不同 payload 必须拒绝」）",
    ),
    Mutation(
        id="M28", side="be", path=CM, kind="replace",
        anchor="        if state is PendingMutationState.committed:",
        new="        if False:",
        want=f"{PG}.py::TestProperty10Idempotency::test_replay_returns_the_same_version_without_new_revision",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
            f"{PG}.py::TestProperty10Idempotency::test_first_commit_consumed_the_token",
        ),
        why="已 committed 的 token 不再走重放分支 ⇒ 重复请求会**再提交一次**并推进第二个"
            "revision。这是 Property 10 的核心：重复请求返回同 operation/version/room",
    ),

    # ══ 九、finalize 的 DAG / artifact 身份 / generation 推算 ══════════
    Mutation(
        id="M29", side="be", path=REP, kind="replace",
        anchor="    return int(current or 0) + 1",
        new="    return 1",
        want=f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_finalize_succeeded",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
            f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_new_generation_bound_to_the_same_content_version",
        ),
        why="generation 恒为 1 ⇒ 同一 content version 的第二代与第一代撞 "
            "`uq_wpcr_generation`。真实后果不是「报错」而是**升级永远做不成**，"
            "而 revision 相同 ⇒ 事后从数字上看不出这一代丢了",
    ),
    Mutation(
        id="M30", side="be", path=REP, kind="replace",
        anchor="        if staged_candidate.relative_path != staged_row[0]:",
        new="        if False:",
        want=f"{PG}.py::TestFinalizeGate::test_foreign_candidate_artifact_is_rejected",
        why="staged candidate 与 DB 登记 artifact 的**路径**不再比对 ⇒ 可以拿另一个"
            "candidate 目录里的 artifact finalize 本 candidate，representation 记的"
            "artifact 与等值报告对不上。🔴 两轮修正：首轮 want 写 `*` 判 GREEN（无任何"
            "用例真的喂错 artifact）；补了「喂另一份 candidate 字节」后仍 GREEN —— 因为"
            "那样路径与 digest **同时**不符，紧随其后的 digest 判据顶上来，异常类型与"
            "文案都不变。最终反例是「同字节、异路径」的孪生 candidate，只有路径这一条"
            "不符，短路它即 finalize 成功",
    ),
    Mutation(
        id="M41", side="be", path=REP, kind="replace",
        anchor="        if staged_candidate.sha256 != candidate.staged_artifact_sha256 or (",
        new="        if False and (",
        want=f"{PG}.py::TestFinalizeGate::test_foreign_candidate_artifact_is_rejected",
        why="artifact **digest** 不再比对 ⇒ 路径对但内容被换掉的 artifact 也能 finalize。"
            "与 M30 成对：那条管路径、本条管 digest，反例是「真路径 + 伪 digest」的 "
            "`forged_digest` 场景。写 `if False and (` 而不是 `if False:` —— 该 `if` 是"
            "**多行**条件，整行换成 `if False:` 会让第二行成为悬空表达式 ⇒ SyntaxError "
            "⇒ collect ERROR ⇒ 判定退化成 GREEN（M15 踩过同一个坑）；`False and (…)` 让"
            "两个合取项同时失效且语法合法",
    ),

    # ══ 十、finalize 前置原因的可分辨性（与 Task 12 的门联动）══════════
    Mutation(
        id="M31", side="be", path=RESOLUTION, kind="replace",
        anchor="        if cand.target_contract_definition_id is None:",
        new="        if False:",
        want=f"{PG}.py::TestFinalizeGate::test_not_ready_candidate_is_rejected",
        why="短路「缺 approved per-entry contract」这条前置 ⇒ 拒绝理由变成下一条"
            "（缺 bundle）。守卫断言拒绝**文案里含 contract**，因此本条打红即证明："
            "「未 ready 被拒」这条判据落在**正确的原因**上，而不是「随便抛了个异常」"
            "（Task 12 的 M34、Task 14 的 M71/M72 是同一个遮蔽形态）",
    ),

    # ══ 十一、事件 payload（Requirement 13.1 / 13.2 / AC 8.12）═════════
    Mutation(
        id="M32", side="be", path=CM, kind="replace",
        anchor='            "content_revision_advanced": True,',
        new='            "content_revision_advanced": False,',
        want=f"{U}.py::TestEventPayload::test_business_commit_payload_has_design_required_keys",
        wants=(
            f"{PG}.py::TestOutboxInSameTransaction::test_event_payload_binds_the_full_identity",
        ),
        why="业务 commit 的事件自报「revision 没变」⇒ 下游不会刷新真正变了的内容。"
            "这个标记是「同一个事件类型既来自业务应用又来自纯表示升级」的唯一区分手段",
    ),
    Mutation(
        id="M33", side="be", path=REP, kind="replace",
        anchor='            "content_revision_advanced": False,',
        new='            "content_revision_advanced": True,',
        want=f"{U}.py::TestEventPayload::test_definition_upgrade_payload_marks_revision_unchanged",
        wants=(
            f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_upgrade_event_declares_revision_unchanged",
        ),
        why="纯表示升级的事件自报「revision 变了」⇒ 下游把一次隐形模板升级当成业务改动"
            "推给审计师（并可能触发不必要的重载/重算）",
    ),
    Mutation(
        id="M34", side="be", path=CM, kind="replace",
        anchor='        "file_sha256",',
        new='        "file_sha256_DISABLED",',
        want=f"{U}.py::TestEventPayload::test_event_type_exists_and_matches_design",
        wants=(
            f"{U}.py::TestEventPayload::test_business_commit_payload_has_design_required_keys",
        ),
        why="必填键清单与 design §outbox 漂移 ⇒ 「payload 有哪些键」失去单一真源。"
            "守卫直接从 design.md 的 JSON 块解析键集合做双向比对，"
            "因此改代码常量或改 design 任一侧都会红",
    ),
    Mutation(
        id="M35", side="be", path=REP, kind="replace",
        anchor='                reason="definition_upgrade",',
        new='                reason="content_commit",',
        want=f"{PG}.py::TestRepresentationFinalizeIsAdditiveOnly::test_new_representation_is_recorded_as_definition_upgrade",
        why="纯表示升级被记成 `content_commit` ⇒ 审计轨迹里「这一代是业务改动还是隐形"
            "模板升级」永久分不开，而 revision 恰好相同、事后无法从数字上区分",
    ),

    # ══ 十二、room 双基线（AC 2.9 / 8.12）════════════════════════════
    Mutation(
        id="M36", side="be", path=CM, kind="replace",
        anchor="            room.refresh_reason = REFRESH_REASON_MERGED_NOT_EQUAL_INCOMING",
        new="            room.refresh_reason = None",
        want=f"{PG}.py::TestRoomBaselines::test_room_entered_refresh_required_with_a_reason",
        wants=(
            f"{PG}.py::TestHarness::test_no_harness_errors",
            f"{PG}.py::TestRoomBaselines::test_room_commit_succeeded",
        ),
        why="refresh 不留原因 ⇒ 审计师看到「要求重开编辑器」却查不到为什么。"
            "V151 的 `ck_wpoor_refresh_reason` 是第二道锁，本条同时验证服务层与 DB 层",
    ),
    Mutation(
        id="M37", side="be", path=CM, kind="replace",
        anchor="            requires_refresh = bool(mutation.merge.requires_client_refresh(mutation.incoming))",
        new="            requires_refresh = False",
        want=f"{PG}.py::TestRoomBaselines::test_room_commit_succeeded",
        wants=(
            f"{PG}.py::TestRoomBaselines::test_room_entered_refresh_required_with_a_reason",
        ),
        why="merged≠incoming 时不再要求重载 ⇒ live editor 仍持有旧 incoming，下一次 "
            "forcesave 会用旧基线把服务器合并结果**回退**（AC 2.9 的核心风险）",
    ),

    # ══ 十三、唯一入口与退役登记（Property 61 / Task 14 边界翻转）═══════
    Mutation(
        id="M38", side="be", path=CM, kind="insert",
        # 🔴 锚点是 `__all__` 列表的收尾 `]`（模块内唯一的裸 `]`，见下方 why）。
        anchor="]",
        new="\nclass ContentMutationServiceLegacy:  # noqa\n"
            "    async def commit(self, **kw):  # noqa\n"
            "        if False:\n"
            "            await self._repo.bump_content_revision(kw['wp'], 0)\n",
        want=f"{U}.py::TestProperty61SingleRevisionDomain::test_revision_bump_has_exactly_one_call_site",
        why="🔴 **注入**：在同一个模块里加第二条 revision 递增调用点。Property 61 的"
            "「所有 writer 进入唯一 revision 域」是否定式承诺 —— 判据是「`bump_content_"
            "revision(` 在 backend/app 里恰一处调用」，多一处即第二个 revision 域。"
            "刻意包在 `if False:` 里：真执行会报 AttributeError，"
            "判定会退化成 WRONG-TEST 而不是 RED（也顺带证明判据扫的是源码结构）。"
            "锚点**不能**是 `class ContentMutationService:` —— insert 落在类语句之后会让"
            "原类体前多出一个顶层 class，类体缺失 ⇒ IndentationError ⇒ 文件级 collect "
            "ERROR ⇒ 判定报 GREEN（首轮实测的假象）。改锚 `__all__` 的收尾 `]`：那里是"
            "模块顶层语句边界，注入的顶层 class 语法合法，`scope_check` 再断言它确实落在"
            "第 0 列",
        scope_check=lambda data: b"\nclass ContentMutationServiceLegacy:" in data,
    ),
    Mutation(
        id="M39", side="be", path=MERGE, kind="replace",
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/content_mutation.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/artifacts.py",',
        want=f"{U14}.py::TestTask14ScopeBoundary::test_merge_domain_has_exactly_one_production_consumer",
        wants=(
            f"{U}.py::TestTask15ScopeBoundary::test_merge_domain_deferral_is_retired",
        ),
        why="退役登记指向错误模块 ⇒ 「消费方恰一个且是唯一 commit 入口」这条翻转后的边界"
            "判据失去正确期望值。Task 14 的边界没有因为退役而被弱化：期望值来自登记表，"
            "登记表错了就红",
    ),
    Mutation(
        id="M40", side="be", path=CM, kind="delete",
        anchor="from app.services.workpaper_sync.merge import MergeOutcome, values_equal",
        want=f"{U14}.py::TestTask14ScopeBoundary::test_merge_domain_has_exactly_one_production_consumer",
        why="🔴 删掉唯一消费方的 import ⇒ merge 域退回**零生产消费方**（Task 14 交付时的"
            "假绿第①源：additive 死代码）。这条证明翻转后的判据两侧都可 falsify ——"
            "M39 管「换了模块」、M78（Task 14 脚本）管「多了一个」、本条管「零个」",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task15_content_mutation.py",
            "backend/tests/workpaper_sync/test_task15_content_mutation_pg.py",
            "backend/tests/workpaper_sync/test_task14_merge_conflicts.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider",
        ],
        # 冻结基线来源：2026-08-26 Task 15 收口实测（仓库根、`.venv\Scripts\python.exe`）
        #   test_task15_content_mutation.py       80 passed
        #   test_task15_content_mutation_pg.py    49 passed（真 PostgreSQL 16.14）
        #   test_task14_merge_conflicts.py       178 passed（本任务翻转边界后 177 → 178）
        #
        # 45 → 49：变异四态复盘补的直接反例 ——
        #   `TestFinalizeGate::test_foreign_candidate_artifact_is_rejected`（2 个参数化
        #     场景：foreign_path 给 M30、forged_digest 给 M41）
        #   `TestFinalizeGate::test_foreign_candidate_scenarios_are_isolated`（反向自检：
        #     孪生 candidate 必须同 digest 异路径，否则两条判据又互相遮蔽）
        #   `TestProperty10Idempotency` 的 `cross_entry` 参数化用例（M25 的独立合取项）
        baseline_backend_passed=307,
    ))
