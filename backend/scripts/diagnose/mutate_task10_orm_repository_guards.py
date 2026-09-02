"""Task 10 变异检验：证明 ORM/repository 守卫真的锁死（RED/GREEN/ANCHOR-MISS/WRONG-TEST）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 为什么变异改的是**生产代码**而不是守卫 ═══

Task 9 的变异改 `V151__*.sql`（schema 层）。Task 10 的被测物是 ORM 映射 + domain 状态机 +
repository 并发协议，因此变异一律改这三处生产文件：

  * `app/models/workpaper_sync_models.py` —— 改列名/nullable/加 application_key 列
  * `app/services/workpaper_sync/models.py` —— 放开状态边、把 fold 改成取小、把
    application key 的入参偷偷混进 status/sequence、放开 duplicate/delivery 不变式
  * `app/services/workpaper_sync/repository.py` —— 去掉 advisory lock、把乐观锁 CAS 改成
    无条件 UPDATE、把 409 换成返回旧 request、把 scope 复用放行、把 fold 改成 supersede、
    把 no-successor 改成永久 blocked

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷处理，不降标**。

═══ 变异必须保持语法合法 ═══

若变异让 Python 语法错误，两个守卫文件会整体 collect error ⇒ 判定退化成 WRONG-TEST，
证明不了「这一条不变式」被锁死。故一律用「整行替换成语义相反但合法的表达式」的手法。

用法（仓库根）:
    python backend/scripts/diagnose/mutate_task10_orm_repository_guards.py --list
    python backend/scripts/diagnose/mutate_task10_orm_repository_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task10_orm_repository_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task10-orm-repository/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

ORM = "backend/app/models/workpaper_sync_models.py"
DOMAIN = "backend/app/services/workpaper_sync/models.py"
REPOSITORY = "backend/app/services/workpaper_sync/repository.py"

#: 覆盖面分母：Task 10 新建的两个守卫文件。
GUARD_FILES = {
    "test_task10_orm_repository_contract.py": "Task 10 新建：ORM↔V151 DDL 双向 + 状态边 + identity 纯逻辑守卫",
    "test_task10_repository_pg.py": "Task 10 新建：真实 PG 多连接并发行为守卫",
}

PURE = "test_task10_orm_repository_contract"
PG = "test_task10_repository_pg"

MUTATIONS: list[Mutation] = [
    # ══ ORM ↔ DDL 双向比对 ═══════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=ORM, kind="replace",
        anchor="    application_key: Mapped[str] = mapped_column(_DIGEST, nullable=False)",
        new="    application_key_renamed: Mapped[str] = mapped_column(_DIGEST, nullable=False)",
        want=f"{PURE}.py::test_orm_columns_match_ddl_bidirectionally",
        wants=(f"{PURE}.py::test_application_key_lives_only_on_content_application",),
        why="把 application_key 列改名 ⇒ ORM 与 V151 DDL 出现 orm_extra + ddl_extra 双向漂移。"
            "不能只删这一行：删了 Property 64 的『只存在于 application 表』断言仍会绿，"
            "改名同时打红列比对与持有者断言，证明两条判据都真的在看列集合",
    ),
    Mutation(
        id="M02", side="be", path=ORM, kind="insert",
        anchor='    __tablename__ = "working_paper_sync_operation"',
        new="\n    application_key: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)",
        want=f"{PURE}.py::test_application_key_lives_only_on_content_application",
        wants=(f"{PURE}.py::test_orm_columns_match_ddl_bidirectionally",),
        why="给 operation ORM 加 application_key ⇒ 违反 Property 64『application identity 的"
            "唯一 owner 是 application 表』。这是最典型的幂等真源复制形态",
    ),
    Mutation(
        id="M03", side="be", path=ORM, kind="replace",
        anchor='        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True',
        scope="    duplicate_of_operation_id: Mapped[uuid.UUID | None] = mapped_column(",
        offset=1,
        new='        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=False',
        want=f"{PURE}.py::test_orm_columns_match_ddl_bidirectionally",
        wants=(
            f"{PURE}.py::test_operation_has_nullable_unique_application_and_direct_self_fk",
        ),
        why="把 duplicate 指针改成 NOT NULL ⇒ 与 DDL 的 nullable 不符，pre-correlation 合法态"
            "（application 与 duplicate 皆空）在 ORM 层变成不可表达。"
            "🔴 首轮把 `Mapped[uuid.UUID | None]` 改成 `Mapped[uuid.UUID]` 判 GREEN —— 那是"
            "**无效变异**：`mapped_column(..., nullable=True)` 的显式参数覆盖类型标注推导，"
            "改标注对 nullable 毫无影响。故必须改显式参数本身",
    ),
    Mutation(
        id="M04", side="be", path=ORM, kind="delete",
        anchor="        WorkpaperSyncOperationContributor,",
        want=f"{PURE}.py::test_orm_covers_exactly_the_v151_tables",
        why="从 WORKPAPER_SYNC_TABLES 清单里删掉一张表 ⇒ ORM 覆盖面与 V151 的 28 张表不再相等。"
            "该清单是守卫的分母，若守卫只断言『>=1 张表』这条变异不会红",
    ),

    # ══ 状态机闭包 ═══════════════════════════════════════════════════
    Mutation(
        id="M05", side="be", path=DOMAIN, kind="replace",
        anchor="    OperationState.duplicate: frozenset(),",
        new="    OperationState.duplicate: frozenset({OperationState.applied}),",
        want=f"{PURE}.py::test_duplicate_is_terminal_and_operation_terminals_are_closed",
        wants=(f"{PURE}.py::test_illegal_transition_raises",),
        why="给 duplicate 加出边 ⇒ loser shell 不再 terminal，可继续流转甚至走到 applied。"
            "Property 18 要求 N-1 个 duplicate 是 terminal 可轮询态",
    ),
    Mutation(
        id="M06", side="be", path=DOMAIN, kind="replace",
        anchor="    ArtifactState.quarantined: frozenset({ArtifactState.orphan, ArtifactState.deleted}),",
        new="    ArtifactState.quarantined: frozenset({ArtifactState.orphan, ArtifactState.deleted, ArtifactState.durable}),",
        want=f"{PURE}.py::test_quarantined_incoming_has_no_edge_to_durable",
        wants=(f"{PURE}.py::test_illegal_transition_raises",),
        why="给 quarantined 开一条到 durable 的边 ⇒ 隔离可被『解除』，quarantined incoming 能"
            "创建 application 并进入 engine（Requirement 5.6 明令禁止的两支互转）",
    ),
    Mutation(
        id="M07", side="be", path=DOMAIN, kind="replace",
        anchor="    CloseIntentState.promoted: frozenset({",
        new="    CloseIntentState.promoted: frozenset({CloseIntentState.successor_selected,",
        want=f"{PURE}.py::test_promoted_leader_cannot_pick_successor",
        why="允许已 promoted 的 leader 再选 successor ⇒ 违反 Requirement 10.10『promotion 后"
            "授权失效只能走 recovery，不得接任再造第二 capture』",
    ),
    Mutation(
        id="M08", side="be", path=DOMAIN, kind="replace",
        anchor='    if target not in edges[source]:',
        new="    if False:",
        want=f"{PURE}.py::test_illegal_transition_raises",
        why="关掉允许状态边的实际比对 ⇒ `assert_transition` 退化成『状态已登记即通过』，"
            "任何非法边都放行。这条变异专打『守卫只查状态存在、不查边』的假绿形态",
    ),

    # ══ operation 三态 / duplicate 链环 ═══════════════════════════════
    Mutation(
        id="M09", side="be", path=DOMAIN, kind="replace",
        anchor="    if application_id is not None and duplicate_of_operation_id is not None:",
        new="    if False:",
        want=f"{PURE}.py::test_operation_shape_rejects_illegal_combinations",
        why="放开『同时绑定 application 与 duplicate 指针』⇒ primary/duplicate 不再互斥，"
            "一个 shell 可同时是 winner 与 loser",
    ),
    Mutation(
        id="M10", side="be", path=DOMAIN, kind="replace",
        anchor="        target.duplicate_of_operation_id is not None",
        new="        False",
        want=f"{PURE}.py::test_direct_primary_rejects_self_chain_stranded_cross_scope",
        why="短路 direct-primary invariant 的『duplicate 指针非空』这一项。"
            "🔴 首轮把 chain 与 stranded 写成两条独立变异，两条都判 GREEN —— 因为拆开后"
            "彼此遮蔽（凡 duplicate 必 application 空，所以任一支被短路，另一支仍会拒）。"
            "生产代码已按 V151 的同名断言合并成一条 or 条件，本变异改其中一个 or 项，"
            "使『合并后的判据整体有效』可被证明",
    ),
    Mutation(
        id="M11", side="be", path=DOMAIN, kind="replace",
        anchor="        or target.state is OperationState.duplicate",
        new="        or False",
        want=f"{PURE}.py::test_direct_primary_rejects_self_chain_stranded_cross_scope",
        why="短路 direct-primary invariant 的『state=duplicate』这一项。"
            "与 M10 配对证明合并条件的两个 or 项都真的参与判定",
    ),
    Mutation(
        id="M12", side="be", path=DOMAIN, kind="replace",
        anchor="    return max(existing, incoming)",
        new="    return min(existing, incoming)",
        want=f"{PURE}.py::test_property_18_fold_is_greatest_and_monotonic",
        wants=(f"{PG}.py::test_property_18_sequential_fold_does_not_self_supersede",),
        why="把 GREATEST fold 改成取小 ⇒ effective_request_sequence 会回退，room durable "
            "fence 指向过期 sequence。纯逻辑与真实 PG 两侧都必须打红",
    ),
    Mutation(
        id="M13", side="be", path=DOMAIN, kind="replace",
        anchor="    if old_application_id == new_application_id:",
        new="    if False:",
        want=f"{PURE}.py::test_no_self_supersede_and_requires_higher_sequence",
        wants=(f"{PG}.py::test_self_supersede_rejected_by_repository_and_database",),
        why="放开 self-supersede ⇒ 同 canonical application 因自己的较高 sequence 把自己判 stale，"
            "形成 Property 36 明令禁止的 duplicate→primary→stale 循环",
    ),
    Mutation(
        id="M14", side="be", path=DOMAIN, kind="replace",
        anchor="        if (application_id is None) == (callback_recovery_case_id is None):",
        new="        if False:",
        want=f"{PURE}.py::test_delivery_ownership_by_durable_at_only",
        why="关掉『durable fact 存在 ⇒ 恰一个 owner』⇒ durable incoming 可成为无所有者死路"
            "（Requirement 5.4 明确禁止）",
    ),
    Mutation(
        id="M15", side="be", path=DOMAIN, kind="insert",
        anchor="    _ = forcesave_request_id",
        new="    if (forcesave_request_id is None) == (application_id is None):\n"
            "        raise DeliveryOwnershipError('request/application XOR')",
        want=f"{PURE}.py::test_delivery_ownership_by_durable_at_only",
        why="回归变异：给 request 与 application **加**一个错误的 XOR。Task 10 明文写"
            "『request 与 application 可同时被 delivery/operation 引用，不施加错误 XOR』——"
            "只断言『双 owner 被拒』的守卫看不见这条错误约束，必须有正控制才能抓到",
    ),

    # ══ identity ═══════════════════════════════════════════════════════
    Mutation(
        id="M16", side="be", path=DOMAIN, kind="replace",
        anchor="    incoming_sha256: str,\n    definition_bundle_sha256: str,",
        new="XXX",
        want=f"{PURE}.py::test_application_key_signature_excludes_status_and_sequence",
        why="占位（见 M17）：本条用多行锚点会在 CRLF 下 MISS，故改由 M17 用单行锚点实现",
        tags=("skip",),
    ),
    Mutation(
        id="M17", side="be", path=DOMAIN, kind="replace",
        anchor="    adapter_build_digest: str,\n) -> str:",
        new="XXX",
        want=f"{PURE}.py::test_application_key_signature_excludes_status_and_sequence",
        why="占位（见 M18）",
        tags=("skip",),
    ),
    Mutation(
        id="M18", side="be", path=DOMAIN, kind="insert",
        anchor="    adapter_build_digest: str,",
        line=0,
        scope='def compute_application_key(',
        offset=10,
        new="    callback_status: int = 6,",
        want=f"{PURE}.py::test_application_key_signature_excludes_status_and_sequence",
        why="给 application key 偷偷混进 callback_status 入参 ⇒ 直接违反 Property 64"
            "（key 不含 callback status）。默认值让签名变化但不破坏既有调用，"
            "正是真实代码里最容易溜进来的形态",
    ),
    Mutation(
        id="M19", side="be", path=DOMAIN, kind="replace",
        anchor="        str(generation),",
        scope="def compute_application_key(",
        offset=30,
        new="        '',",
        want=f"{PURE}.py::test_application_key_is_stable_and_identity_sensitive",
        why="把 generation 从 key 里抹掉 ⇒ 不同 generation 的相同 incoming 会折叠成同一 "
            "application，跨代际内容互相覆盖",
    ),
    Mutation(
        id="M20", side="be", path=DOMAIN, kind="replace",
        anchor="    if not v or v == _ALL_ZERO:",
        new="    if not v:",
        want=f"{PURE}.py::test_digest_single_source_of_truth",
        wants=(f"{PURE}.py::test_application_key_rejects_empty_and_zero_digests",),
        why="digest 单一真源放开全零 hash ⇒ 『忘了算 hash 就填 0』的伪身份可以进入 "
            "application key / bundle slot（与 V151 的 wpsync_is_digest 对称）",
    ),
    Mutation(
        id="M21", side="be", path=DOMAIN, kind="replace",
        anchor="        str(callback_status),",
        new="        '',",
        want=f"{PURE}.py::test_delivery_key_varies_by_status_and_discriminator",
        wants=(f"{PURE}.py::test_property_64_key_independent_of_status_sequence_room_pointer",),
        why="把 status 从 delivery key 里抹掉 ⇒ status 6 与 status 2 撞同一 delivery row，"
            "『每次 delivery 各留证据』失效（Requirement 4.3）",
    ),
    Mutation(
        id="M22", side="be", path=DOMAIN, kind="replace",
        anchor="        str(client_edit_epoch),",
        new="        '',",
        want=f"{PURE}.py::test_frozen_fingerprint_covers_every_frozen_field",
        why="把 client_edit_epoch 从 frozen fingerprint 里抹掉 ⇒ 不同 edit epoch 的重放会被"
            "当成逐项等值的 cache hit 而返回旧 request（Requirement 4.1）",
    ),
    Mutation(
        id="M23", side="be", path=DOMAIN, kind="replace",
        anchor="    return not bool(_DIGITS_ONLY.match(v))",
        new="    return True",
        want=f"{PURE}.py::test_property_59_numeric_revision_is_never_a_scope_key",
        wants=(f"{PG}.py::test_numeric_revision_never_collides_across_workpapers",),
        why="放开 numeric revision 作 scope resource_id ⇒ 两个不同 wp 的 revision 1 在"
            "authorization 索引里碰撞成同一行（Requirement 8.7 / 10.6）",
    ),

    # ══ bundle typed slots ═══════════════════════════════════════════
    Mutation(
        id="M24", side="be", path=DOMAIN, kind="replace",
        anchor="    if am is AuthorityModel.projection_contract:",
        new="    if False:",
        want=f"{PURE}.py::test_projection_contract_requires_three_approved_definition_children",
        why="关掉『projection_contract 三 child 必须全 approved definition』⇒ typed null marker"
            "可冒充 per-entry contract（Requirement 2.3 / 3.3）",
    ),
    Mutation(
        id="M25", side="be", path=DOMAIN, kind="replace",
        anchor="    missing = [s.value for s in BundleSlot if s not in slots]",
        new="    missing = []",
        want=f"{PURE}.py::test_slot_omission_null_empty_zero_and_illegal_marker_all_rejected",
        why="关掉 slot omission 检测 ⇒ 缺 slot 的 bundle 可以通过 canonicalization，"
            "而 canonical bytes 里少一个 slot 会让 definition identity 静默漂移",
    ),
    Mutation(
        id="M26", side="be", path=DOMAIN, kind="replace",
        anchor="    if not spec.slot_type.startswith(f\"{name}:none:v\"):",
        new="    if False:",
        want=f"{PURE}.py::test_slot_omission_null_empty_zero_and_illegal_marker_all_rejected",
        why="放开『用别的 slot 的 marker』⇒ contract slot 可以放 template 的 typed null marker，"
            "bundle 的 typed 语义失效",
    ),

    # ══ repository：锁与乐观锁 ════════════════════════════════════════
    Mutation(
        id="M27", side="be", path=REPOSITORY, kind="replace",
        anchor='            sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),',
        new='            sa.text("SELECT 1"),',
        want=f"{PG}.py::test_property_59_same_wp_serial_cross_wp_parallel",
        wants=(f"{PURE}.py::test_repository_uses_database_locks_not_process_locks",),
        why="去掉 per-wp advisory lock ⇒ 同 wp 不再串行（第二个事务能立刻拿到锁）。"
            "Property 59 要求正确性由数据库锁决定，不是进程锁",
    ),
    Mutation(
        id="M28", side="be", path=REPOSITORY, kind="replace",
        anchor='                    "WHERE id = :wp AND content_revision = :expected "',
        new='                    "WHERE id = :wp "',
        want=f"{PG}.py::test_property_59_revision_optimistic_lock_has_single_winner",
        why="把 business revision 的 CAS 条件删掉 ⇒ 乐观锁退化成无条件 UPDATE，"
            "并发两个 worker 各 +1（丢更新），最终 revision 会变成 before+2",
    ),
    Mutation(
        id="M29", side="be", path=REPOSITORY, kind="replace",
        anchor="                .with_for_update()\n            )",
        new="XXX",
        want=f"{PG}.py::test_property_18_n_shells_one_primary_rest_direct_duplicates",
        why="占位：多行锚点在 CRLF 下必 MISS，改由 M30 用单行锚点实现",
        tags=("skip",),
    ),
    Mutation(
        id="M30", side="be", path=REPOSITORY, kind="replace",
        anchor='                .on_conflict_do_nothing(index_elements=["application_key"])',
        new='                .on_conflict_do_nothing(index_elements=["id"])',
        want=f"{PG}.py::test_property_18_n_shells_one_primary_rest_direct_duplicates",
        why="把 create-or-hit 的冲突键从 application_key 换成 id ⇒ 并发 shell 各自 INSERT 都"
            "『不冲突』，随后撞 application_key 唯一约束整事务失败 ⇒ 1 primary + N-1 duplicates "
            "的收敛不再成立",
    ),

    # ══ repository：幂等 409 ═════════════════════════════════════════
    Mutation(
        id="M31", side="be", path=REPOSITORY, kind="replace",
        anchor="            if not same_slot:",
        new="            if False:",
        want=f"{PG}.py::test_property_64_forcesave_composite_idempotency",
        why="关掉『跨 participant/kind 复用同 key ⇒ 409』⇒ 另一个 participant 用同 key 会"
            "拿到别人的 request/operation（Requirement 4.1 明确要求 409 且不返回旧标识）",
    ),
    Mutation(
        id="M32", side="be", path=REPOSITORY, kind="replace",
        anchor="            if prior.frozen_request_fingerprint.strip() != frozen_request_fingerprint.strip():",
        new="            if False:",
        want=f"{PG}.py::test_property_64_forcesave_composite_idempotency",
        why="关掉 fingerprint 逐项等值比对 ⇒ 同 key 但不同 base/bundle/fence 的 payload 会被"
            "当 cache hit 返回旧 request，冻结语义失效",
    ),
    Mutation(
        id="M33", side="be", path=REPOSITORY, kind="replace",
        anchor='                    "Idempotency-Key 被另一个 participant 或另一种 kind 复用 —— "',
        new='                    f"Idempotency-Key 冲突，既有 request={prior.id} operation 见该 request —— "',
        want=f"{PG}.py::test_property_64_forcesave_composite_idempotency",
        why="让 409 的错误消息把旧 request id 带出去 ⇒ 违反『不得返回旧标识』。"
            "只断言『抛了 409』的守卫看不见泄露，必须有 leaks_old_id 判据",
    ),

    # ══ repository：scope index ══════════════════════════════════════
    Mutation(
        id="M34", side="be", path=REPOSITORY, kind="replace",
        anchor="        if existing is not None:",
        new="        if False:",
        want=f"{PG}.py::test_scope_tombstone_is_immortal_and_never_reused",
        why="关掉 scope id 复用检测 ⇒ retired tombstone 的 (kind,id) 可被重新登记，"
            "authorization 索引会把新 child 指到旧归属（Requirement 10.6）",
    ),
    Mutation(
        id="M35", side="be", path=REPOSITORY, kind="replace",
        anchor='        raise ScopeIntegrityError(\n            "scope index tombstone 永不物理删除 —— 退役请用 retire_scope() 设置 retired_at"',
        new="XXX",
        want=f"{PG}.py::test_scope_tombstone_is_immortal_and_never_reused",
        why="占位：多行锚点在 CRLF 下必 MISS，改由 M36 用单行锚点实现",
        tags=("skip",),
    ),
    Mutation(
        id="M36", side="be", path=REPOSITORY, kind="replace",
        anchor="        if not is_opaque_resource_id(rid):",
        new="        if False:",
        want=f"{PG}.py::test_numeric_revision_never_collides_across_workpapers",
        why="关掉 opaque resource_id 校验 ⇒ numeric revision 可作 scope key。"
            "repository 与 DB CHECK 是双向的，这条只打 repository 侧",
    ),

    # ══ repository：quarantined / delivery ═══════════════════════════
    Mutation(
        id="M37", side="be", path=REPOSITORY, kind="replace",
        anchor="        if art.state == ArtifactState.quarantined.value:",
        new="        if False:",
        want=f"{PG}.py::test_quarantined_incoming_cannot_create_application_or_be_released",
        why="关掉 quarantined incoming 的 fail-closed ⇒ 隔离文件能被 extract/merge 消费。"
            "🔴 首轮判 GREEN：当时暂态分支与隔离分支共用 QuarantinedIncomingError，"
            "短路本分支后暂态分支抛同类异常把判据遮蔽。生产代码已拆出 "
            "IncomingNotDurableError，守卫改断言**异常类型** ⇒ 本变异现在可被抓到",
    ),
    Mutation(
        id="M38", side="be", path=REPOSITORY, kind="replace",
        anchor="        row.operation_id = None\n        row.response_error = response_error",
        new="XXX",
        want=f"{PG}.py::test_delivery_ownership_pre_and_post_durable",
        why="占位：多行锚点在 CRLF 下必 MISS，改由 M39 实现",
        tags=("skip",),
    ),
    Mutation(
        id="M39", side="be", path=REPOSITORY, kind="replace",
        anchor='                "delivery 已有 durable fact —— 请用 mark_delivery_post_durable_error() 保留 owner"',
        new='                "unused"',
        want="*",
        why="占位型语义变异：把错误文案换成无意义字符串**不改行为**，用来自证"
            "『判定不是靠错误文案字符串匹配』—— 若这条也判 RED，说明有守卫在断言文案，"
            "属于 grep 式假绿，必须改判据。预期 GREEN 由 --check-anchors 记录",
        tags=("selfcheck", "skip"),
    ),
    Mutation(
        id="M40", side="be", path=REPOSITORY, kind="replace",
        anchor="        if row.durable_at is not None:",
        scope="    async def bind_delivery_to_recovery(",
        offset=11,
        new="        if False:",
        want=f"{PG}.py::test_recovery_claim_is_concurrent_idempotent",
        wants=(f"{PG}.py::test_download_only_creates_zero_three_entities",),
        why="关掉『durable_at 已存在则拒绝改归属』⇒ 已归 recovery 的 delivery 可被重新 sealing，"
            "durable fact 不再 immutable（V151 的 durable_at immutable 是第二道锁）",
    ),

    # ══ repository：close leader / successor ═════════════════════════
    Mutation(
        id="M41", side="be", path=REPOSITORY, kind="replace",
        anchor="        if already_promoted is not None:",
        new="        if False:",
        want=f"{PG}.py::test_property_63_reconciler_is_idempotent",
        wants=(f"{PG}.py::test_property_63_close_capture_exactly_one",),
        why="去掉『已 promoted 即幂等返回』⇒ reconciler 重入会尝试再造 capture；"
            "partial unique 只能挡住『同时 open』，挡不住 leader 状态被再次改写",
    ),
    Mutation(
        id="M43", side="be", path=REPOSITORY, kind="replace",
        anchor="        leader = max(eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))",
        new="        leader = min(eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))",
        want=f"{PG}.py::test_property_63_leader_revoked_selects_successor",
        why="把 deterministic comparator 从『最高 (intent_sequence,id)』改成最低 ⇒ leader 选择"
            "与 Requirement 4.10 规定的规则不一致，successor 也会选错",
    ),
    Mutation(
        id="M44", side="be", path=REPOSITORY, kind="replace",
        anchor="        if not eligible_intents:",
        new="        if False:",
        want=f"{PG}.py::test_property_63_no_successor_zero_capture_but_explicit_terminal",
        why="关掉 no-successor 分支 ⇒ 无合法 successor 时既不 supersede generation 也不落"
            "recovery_required，intents 永久停在 waiting/created（Requirement 4.10 禁止的"
            "『永久 retryable_blocked / 静默关闭』）",
    ),
    Mutation(
        id="M45", side="be", path=REPOSITORY, kind="replace",
        anchor="        if active_count > 0 or int(predecessors_open) > 0:",
        new="        if False:",
        want=f"{PG}.py::test_property_63_ordinary_forcesave_barrier",
        why="去掉 close barrier ⇒ active 未归零、前置普通 forcesave 未终结时就提升 leader，"
            "会丢失尚未耐久的贡献",
    ),
    Mutation(
        id="M46", side="be", path=REPOSITORY, kind="replace",
        anchor="        if current_leader is not None and not eligible(current_leader):",
        new="        if False:",
        want=f"{PG}.py::test_property_63_leader_revoked_selects_successor",
        why="关掉『leader 失去资格则审计为 authorization_stale 并推进 eligibility epoch』⇒"
            "被撤销的 leader 仍被当合法 leader，撤权用户的贡献会被提交",
    ),

    # ══ repository：correlation / 事务边界 ═══════════════════════════
    Mutation(
        id="M47", side="be", path=REPOSITORY, kind="replace",
        anchor="        if shape is not OperationShape.pre_correlation:",
        new="        if False:",
        want=f"{PG}.py::test_property_18_n_shells_one_primary_rest_direct_duplicates",
        wants=(f"{PG}.py::test_property_18_sequential_fold_does_not_self_supersede",),
        why="允许对已 primary/已 duplicate 的 shell 再次 correlate ⇒ 重复 callback 会二次绑定，"
            "产生第二 primary 或把 duplicate 重定向",
    ),
    Mutation(
        id="M48", side="be", path=REPOSITORY, kind="replace",
        anchor="        await self._session.flush()",
        new="        await self._session.commit()",
        want=f"{PURE}.py::test_repository_never_commits",
        wants=(f"{PG}.py::test_property_5_repository_only_flushes",),
        why="把 repository 的 flush 换成 commit ⇒ 直接违反『只 flush 不 commit』。"
            "AST 守卫与真实 PG 的 rollback 行为守卫必须同时打红：前者证明结构，"
            "后者证明行为（只有 AST 守卫时，绕过 `_flush()` 的 commit 仍可能溜进来）",
    ),
    Mutation(
        id="M49", side="be", path=REPOSITORY, kind="replace",
        anchor="        room.latest_durable_application_id = application_id",
        new="        room.latest_durable_application_id = room.latest_durable_application_id",
        want=f"{PG}.py::test_property_18_n_shells_one_primary_rest_direct_duplicates",
        wants=(f"{PG}.py::test_property_18_sequential_fold_does_not_self_supersede",),
        why="不再把 room durable fence 指向 canonical application ⇒ Requirement 10.11 要求的"
            "『same-application fold 与 room latest-durable 在同一事务原子决定』失效",
    ),
    Mutation(
        id="M50", side="be", path=REPOSITORY, kind="replace",
        anchor="        if int(confirmation.write_fence_epoch) != int(room.write_fence_epoch):",
        new="        if False:",
        want=f"{PG}.py::test_property_43_final_authorization_fence_blocks_claim",
        why="关掉 recovery claim 的最终 write fence 重验 ⇒ 陈旧 fence 的 prior confirmation 也能"
            "创建三实体（Property 43 要求 commit 前失败且零实体）",
    ),
    Mutation(
        id="M51", side="be", path=REPOSITORY, kind="replace",
        anchor="        if case.state == RecoveryCaseState.application_created.value:",
        new="        if False:",
        want=f"{PG}.py::test_recovery_claim_is_concurrent_idempotent",
        why="关掉 claim 的幂等命中分支 ⇒ 并发同 Idempotency-Key 的第二次 claim 会再造"
            "request/operation，违反『最多创建一个』",
    ),
    Mutation(
        id="M52", side="be", path=REPOSITORY, kind="replace",
        anchor="        if has_any_entity:",
        new="        if False:",
        want=f"{PG}.py::test_download_only_creates_zero_three_entities",
        why="放开 download-only 的『三实体恒空』前置校验 ⇒ 已 claim 的 case 也能转 "
            "download-only，Requirement 5.8 的零三实体判据失效。"
            "🔴 首轮锚点只短路三段 or 里的一段，被另两段遮蔽判 GREEN；生产代码已把三段"
            "收敛成单一布尔 `has_any_entity`，本变异短路它整体",
    ),
    Mutation(
        id="M53", side="be", path=REPOSITORY, kind="replace",
        anchor="        if v_artifact_state <> 'published' THEN",
        new="        if False:",
        want="*",
        why="占位：该锚点属于 V151（SQL），不在本脚本作用域 —— 保留为 ANCHOR-MISS 自检样本",
        tags=("skip",),
    ),
    Mutation(
        id="M54", side="be", path=REPOSITORY, kind="replace",
        anchor="        if bundle.state != \"approved\":",
        new="        if False:",
        want=f"{PG}.py::test_candidate_cannot_finalize_or_become_current",
        wants=(f"{PG}.py::test_property_63_close_capture_exactly_one",),
        why="放开『只有 approved bundle 可用于 finalize/room』⇒ candidate bundle 能 finalize "
            "representation 并被 room/resolver 使用（Requirement 3.3 / 9.8）",
    ),
    Mutation(
        id="M55", side="be", path=REPOSITORY, kind="replace",
        anchor="        if cand.target_definition_bundle_id is None or cand.target_contract_definition_id is None:",
        new="        if False:",
        want=f"{PG}.py::test_candidate_cannot_finalize_or_become_current",
        why="关掉『finalize 前必须补齐 approved contract + bundle』⇒ candidate 可在无 per-entry "
            "contract 时 finalize（Requirement 3.4 / 9.10）",
    ),
]

#: 占位/自检条目（多行锚点或不在作用域），`--run all` 时跳过。
MUTATIONS = [m for m in MUTATIONS if "skip" not in m.tags]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 10 ORM/repository 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task10_orm_repository_contract.py",
                "backend/tests/workpaper_sync/test_task10_repository_pg.py",
                # 🔴 必须 `-rfE`：harness（module fixture）异常在 pytest 里是 ERROR 而不是
                # FAILED，只给 `-rf` 时短摘要不含 `ERROR ...` 行，runner 收不到失败名 ⇒
                # 整轮判 GREEN。首轮实测 5 条（M30/M34/M41/M44/M49）因此被误判。
                "-q", "--tb=no", "-rfE", "-p", "no:randomly",
            ],
            baseline_backend_passed=59,
        )
    )
