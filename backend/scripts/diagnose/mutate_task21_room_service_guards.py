# -*- coding: utf-8 -*-
"""Task 21 变异检验：room 资格门 / doc_key 解耦 / 双基线 / 撤销旋转 / 真值表消费的
守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 21
Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10
Properties: P6 / P15 / P43 / P44 / P62 / P63

═══ 变异改的是**生产代码**，不是守卫 ═══

落点三处：

* `workpaper_sync/rooms.py` —— doc_key 派生（注入 mtime / 去掉 generation / 掏空 AST
  入口清单）、九条资格判据逐条短路、双基线两侧混同、撤销不提升 fence / 不取消
  outstanding / 把 view 当 writer、open-or-reuse 退化成总是新建、confirm 不写基线 /
  不比 bundle、lease token 明文落库
* `workpaper_sync/models.py` —— 两个新 canonical digest：typed-slot 清单按 dict 序、
  slot 缺席静默跳过、contributor 按到达序
* `workpaper_sync/oo_contract.py` —— 真值表 fail-closed 六条：版本漂移、重定向放开、
  participant-bound 授权、grace 吞掉超时、status 表清空、允许 application 但不下载、
  未知 status 用 `int()` 强转猜测

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 本任务实测到的判据设计教训 ═══

1. **vacuous truth 是最不起眼的失效**：`_doc_key_source_is_mtime_free()` 里
   `len(pending) != len(entries)` 在入口清单被清空时是 `0 != 0`，循环一次都不进 ⇒
   恒返回 True。M03 就是清空那个常量元组；为它专门补了「清单非空」判据。
2. **「事实由探针产出」必须真能被 falsify**：M01 往 `derive_doc_key` 注入一次 mtime
   读取，探针的 `doc_key_source_is_mtime_free` 必须转 False 并连带让 registry 的
   RG-17 门打红 —— 否则「room service 已摘掉 mtime」只是文档声明。
3. **双基线混同要双向可 falsify**：只测「server 会推进」的话，M14（推进 server 时顺手
   把 client 也改掉）不会被任何守卫发现。故 PG 守卫对 `client_unchanged` 有独立断言。
4. **契约数值的单一真源判据需要正向半段**：M31~M36 改的是 fail-closed 分支；若守卫只
   断言「别处没有字面量」，把数值全删也会通过。故 offline 守卫先断言真的读到了
   `{10,120,30,209715200,72}`。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task21_room_service_guards.py --list
    python backend/scripts/diagnose/mutate_task21_room_service_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task21_room_service_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task21-room-service/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

ROOMS = "backend/app/services/workpaper_sync/rooms.py"
MODELS = "backend/app/services/workpaper_sync/models.py"
CONTRACT = "backend/app/services/workpaper_sync/oo_contract.py"
#: Task 21 的**生产接线** seam 与两个 `onlyoffice-config` 路由。
#: 没有这三处的变异，「room service 已接线」只是一句声明 —— 而 additive 死代码正是
#: 本 spec 反复付过代价的假绿第①源。
SEAM = "backend/app/services/onlyoffice_room_identity.py"
OO_ROUTER = "backend/app/routers/wp_onlyoffice_router.py"
EDITOR_ROUTER = "backend/app/routers/wp_editor_router.py"
#: Task 10 的仓储层。M29 落在这里而不是 rooms.py：`set_room_client_confirmed_baseline`
#: 的调用在 rooms.py 里是三行，跨行锚点在 CRLF 工作树下必然 MISS；改为直接短路仓储侧
#: 的首个赋值，观察面完全相同（confirm-descriptor 后 client 基线没写上）。
REPOSITORY = "backend/app/services/workpaper_sync/repository.py"

#: 覆盖面分母：Task 21 新建的两个守卫文件。
GUARD_FILES = {
    "test_task21_room_service.py":
        "Task 21 新建：doc_key/mtime 解耦行为探针 + RG-17 门交叉校验（含真实 manifest 上"
        "零红与反向自检）、生产接线的 AST 调用点判据、seam 的视图分离与 file_version 禁用、"
        "Task 4 真值表生产侧唯一消费方与六条 fail-closed、typed-slot/contributor canonical "
        "digest、route credential 三成分绑定、contributor 封闭域与 V151 CHECK 双向锁死、"
        "双基线纯投影判据、服务层不重写 repository 原子写的结构判据",
    "test_task21_room_service_pg.py":
        "Task 21 新建：真实 PG 的 room 落库 doc_key、逐人 lease、九条资格拒绝路径各自"
        "专属 error 类型、representation 准入三道门（published / candidate / alias 漂移，"
        "外加「DB 自己就拒绝行漂移」的执法点）、route credential 取自 room 行、"
        "canonical fence 与 server 指针同事务、same-application 只 fold 不 self-supersede、"
        "freeze base 跟随已确认快照、initiator/route/contributor 三处分离、"
        "Property 62 双基线不对称推进、refresh-required 立刻阻断下一次 forcesave、"
        "撤销 writer 提升 fence + 取消 outstanding、view 撤销不旋转、"
        "同代际复用与超代际拒绝、flush-only",
}

U = "test_task21_room_service"
PG = "test_task21_room_service_pg"

MUTATIONS: list[Mutation] = [
    # ══ 一、Property 6：doc_key 与 mtime / generation ════════════════════
    Mutation(
        id="M01", side="be", path=ROOMS, kind="insert",
        anchor='    digest = hashlib.sha256(f"{wp_id}|{normalized_entry}".encode("utf-8")).hexdigest()',
        new="    from pathlib import Path as _P\n"
            "    _ = _P(__file__).stat().st_mtime_ns",
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_probe_reports_mtime_free_and_really_changed_mtime",
        wants=(
            f"{U}.py::TestDocKeyIsMtimeFree::test_probe_facts_pass_registry_room_gate",
            f"{U}.py::TestDocKeyIsMtimeFree::test_entry_function_list_is_not_empty",
        ),
        why="往 doc_key 派生链路注入一次 mtime 读取 ⇒ 退回生产实况（`hash(wp_code + "
            "st_mtime_ns)`）的形态：一次写盘就轮转 doc_key、切断进行中的协同会话。"
            "「与 mtime 解耦」是否定式承诺，只能靠注入反例 falsify",
    ),
    Mutation(
        id="M02", side="be", path=ROOMS, kind="replace",
        anchor='    return f"{DOC_KEY_PREFIX}-{digest[:_DOC_KEY_DIGEST_CHARS]}-g{generation}"',
        new='    return f"{DOC_KEY_PREFIX}-{digest[:_DOC_KEY_DIGEST_CHARS]}-g1"',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_generation_rotation_rotates_doc_key",
        wants=(
            f"{U}.py::TestDocKeyIsMtimeFree::test_doc_key_shape_and_roundtrip",
            f"{PG}.py::test_ac_2_8_supersede_rotates_doc_key_for_new_generation",
        ),
        why="doc_key 不再随 generation 轮转 ⇒ AC 2.8「发布新 generation 显式 supersede "
            "旧 room」失效：OO 会把新旧代际当同一文档，旧会话继续往新代际里写",
    ),
    Mutation(
        id="M03", side="be", path=ROOMS, kind="replace",
        anchor='_DOC_KEY_ENTRY_FUNCTIONS: Final[tuple[str, ...]] = (',
        new='_DOC_KEY_ENTRY_FUNCTIONS: Final[tuple[str, ...]] = ()  # noqa\nif False: (',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_entry_function_list_is_not_empty",
        why="掏空 AST 入口清单 ⇒ `len(pending) != len(entries)` 变成 `0 != 0`，循环一次"
            "都不进，`_doc_key_source_is_mtime_free()` 恒返回 True。这是 vacuous truth "
            "型失效：结构、调用点、日志全都正常，只有判据没了",
    ),
    Mutation(
        id="M04", side="be", path=ROOMS, kind="replace",
        anchor="    if not _DOC_KEY_ENTRY_FUNCTIONS:",
        new="    if False:",
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_empty_entry_list_makes_the_check_fail_not_pass",
        why="去掉「清单非空」这道防线本身 ⇒ M03 那类改动重新变得不可见。"
            "专门检验防线不是装饰性的",
    ),

    # ══ 二、Property 15：九条资格判据逐条短路 ═════════════════════════════
    Mutation(
        id="M05", side="be", path=ROOMS, kind="replace",
        anchor="    {RoomState.active, RoomState.close_barrier}",
        new="    {RoomState.active, RoomState.close_barrier, RoomState.refresh_required}",
        want=f"{PG}.py::test_ac_2_9_unequal_merge_forces_refresh_required_and_blocks_next_request",
        wants=(
            f"{U}.py::TestServiceDoesNotDuplicateRepository::test_allowed_states_include_barrier_and_closing",
        ),
        why="把 refresh_required 放进允许集 ⇒ live OO 可以拿旧 incoming 继续 forcesave，"
            "把服务器已合并的值回退掉（AC 2.9 / 4.11 要防的正是这个）",
    ),
    Mutation(
        id="M06", side="be", path=ROOMS, kind="replace",
        anchor="    {ParticipantState.active, ParticipantState.closing}",
        new="    {ParticipantState.active, ParticipantState.closing, ParticipantState.revoked}",
        want=f"{U}.py::TestServiceDoesNotDuplicateRepository::test_allowed_states_include_barrier_and_closing",
        why="被撤销的 participant 仍可发起 request ⇒ Property 44「只读/被撤销 contributor "
            "零内容版本」失效",
    ),
    Mutation(
        id="M07", side="be", path=ROOMS, kind="replace",
        anchor="        if ParticipantMode(participant.mode) is not ParticipantMode.edit:",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[view_mode-ParticipantNotWritableError]",
        why="只读会话可以发起写请求 ⇒ view participant 也能产生内容版本（Property 44）",
    ),
    Mutation(
        id="M08", side="be", path=ROOMS, kind="replace",
        anchor="        if int(participant.joined_write_fence_epoch) != current_fence:",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[participant_joined_at_older_fence-WriteFenceStaleError]",
        why="participant 加入时的 fence 不再比对 ⇒ 有人被撤销后旧会话照样能写，"
            "聚合 artifact 会继续带上被撤销用户的贡献（AC 4.7 / Property 63）。"
            "判据必须用「只有这一条能生效」的场景（room/confirmation fence 都不变、"
            "只调低 participant 的 joined fence）—— 否则第 ⑥ 条 confirmation-fence "
            "会先打红把它遮蔽",
    ),
    Mutation(
        id="M09", side="be", path=ROOMS, kind="replace",
        anchor="            and int(expected_write_fence_epoch) != current_fence",
        new="            and False",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[stale_descriptor_fence-WriteFenceStaleError]",
        why="descriptor 携带的 fence 不再校验 ⇒ 陈旧 descriptor 可以发起 forcesave"
            "（AC 3.7 明确要求拒绝 stale generation/representation/bundle/fence）",
    ),
    Mutation(
        id="M10", side="be", path=ROOMS, kind="delete",
        anchor="                    WorkpaperOoClientConfirmation.invalidated_at.is_(None),",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[invalidated_confirmation-DescriptorNotConfirmedError]",
        why="已作废的 confirmation 仍被当成有效 ⇒ fence 提升后作废的确认可以继续用来"
            "冻结 base，绕过 generation 轮转",
    ),
    Mutation(
        id="M11", side="be", path=ROOMS, kind="replace",
        anchor="        if request_kind is RequestKind.close_capture:",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[close_capture_from_client-RoomPolicyError]",
        why="客户端可以直接创建 kind=close_capture ⇒ 绕过 `reconcile_close_intents()` 的"
            "exactly-one CAS，一个 generation 可能出现多条 close-capture"
            "（契约 clean_close.forbidden[0]）",
    ),
    Mutation(
        id="M12", side="be", path=ROOMS, kind="replace",
        anchor="        if participant.room_id != room_id:",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[cross_room_participant-ParticipantNotWritableError]",
        wants=(f"{PG}.py::test_foreign_participant_does_not_leak_object_existence",),
        why="跨 room 复用 participant id 不再被拒 ⇒ 横向越权（Property 45），"
            "且能用别的 room 的 lease 冻结本 room 的 request",
    ),
    Mutation(
        id="M13", side="be", path=ROOMS, kind="replace",
        anchor="        if participant.expires_at is not None and participant.expires_at <= _now():",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[expired_lease-ParticipantNotWritableError]",
        why="过期 lease 仍可写 ⇒ TTL 形同虚设，长期挂着的浏览器标签页能在授权早已失效后"
            "继续回写",
    ),
    Mutation(
        id="M14", side="be", path=ROOMS, kind="replace",
        anchor="        if state is RoomState.opening:",
        new="        if False:",
        want=f"{PG}.py::test_ac_3_7_forcesave_blocked_before_descriptor_confirmation",
        why="room 仍 opening 时不再给出「去 confirm-descriptor」这个可操作诊断 ⇒ 退化成"
            "笼统的 room_not_writable，前端无从下手（AC 3.7）",
    ),
    Mutation(
        id="M15", side="be", path=ROOMS, kind="replace",
        anchor="        if room.close_leader_intent_id is not None or int(room.close_barrier_epoch) > 0:",
        new="        if False:",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[new_editor_after_barrier-RoomNotWritableError]",
        why="close barrier 冻结后仍允许新 editor 加入该 generation ⇒ active 数刚归零又被"
            "拉起来，close-capture 的 leader 仲裁永远等不到条件成立（AC 4.10）",
    ),

    # ══ 三、Property 62：双基线不得混同 ══════════════════════════════════
    Mutation(
        id="M16", side="be", path=ROOMS, kind="insert",
        anchor="        room.last_applied_version_id = content_version_id",
        new="        room.client_confirmed_base_version_id = content_version_id",
        want=f"{PG}.py::test_property_62_server_last_applied_advances_unconditionally",
        why="推进 server last-applied 时顺手把 client 基线也改掉 ⇒ 第二次 forcesave 的"
            "三方 merge 会以服务器合并结果为 base，编辑器里真实存在的旧值被当成「用户"
            "没改过」而静默丢弃。这是 Property 62 存在的唯一理由",
    ),
    Mutation(
        id="M17", side="be", path=ROOMS, kind="replace",
        anchor="        if merged_projection_sha256.strip() != incoming_projection_sha256.strip():",
        new="        if False:",
        want=f"{PG}.py::test_ac_2_9_unequal_merge_forces_refresh_required_and_blocks_next_request",
        wants=(f"{PG}.py::test_property_62_client_baseline_advances_only_on_equivalence",),
        why="merged≠incoming 时也推进 client 基线 ⇒ 把服务器结果冒充成「客户端已确认"
            "基线」，AC 4.11 明令禁止",
    ),
    Mutation(
        id="M18", side="be", path=ROOMS, kind="replace",
        anchor="            room.state = RoomState.refresh_required.value",
        new="            pass",
        want=f"{PG}.py::test_ac_2_9_unequal_merge_forces_refresh_required_and_blocks_next_request",
        why="只写 `refresh_required_at` 而不推进 room state ⇒ room 停在 active、"
            "`refresh_required` 在状态机与 UI 上都不可见（前端状态条与 close 仲裁都读 "
            "state）。这条专门检验判据看的是**状态**而不是「某个时间戳非空」",
    ),
    Mutation(
        id="M19", side="be", path=ROOMS, kind="replace",
        anchor="        if not is_digest(merged_projection_sha256) or not is_digest(",
        new="        if False and not is_digest(",
        want=f"{PG}.py::test_property_15_every_rejection_branch_has_its_own_error_type"
             "[settle_with_blank_digest-RoomPolicyError]",
        wants=(f"{PG}.py::test_property_62_client_baseline_advances_only_on_equivalence",),
        why="缺一侧 digest 时不再 fail closed ⇒ 空串 == 空串 会被判成「等值」并推进基线"
            "（缺 incoming 就默认等值，是最典型的 fail-open）",
    ),
    Mutation(
        id="M20", side="be", path=ROOMS, kind="replace",
        anchor="            and bool(self.client_confirmed_projection_sha256)",
        new="            and True",
        want=f"{U}.py::TestRoomBaselinesProjection::test_half_missing_snapshot_is_not_established",
        why="半缺快照被当成已建立 ⇒ forcesave 会冻结出一个没有 projection digest 的 "
            "client base，三方 merge 的 base 侧直接失真",
    ),

    # ══ 四、Property 63：撤销必须提升 fence 并旋转 generation ═════════════
    Mutation(
        id="M21", side="be", path=ROOMS, kind="replace",
        anchor="        room.write_fence_epoch = int(room.write_fence_epoch) + 1",
        new="        pass",
        want=f"{PG}.py::test_property_63_writer_revocation_bumps_fence_and_cancels_requests",
        why="撤销 writer 不提升 write fence ⇒ 其余用户的旧会话仍然合法，聚合文档继续"
            "接收可能含被撤销贡献的内容（Task 4 实证 drop 不证明内容已移除）",
    ),
    Mutation(
        id="M22", side="be", path=ROOMS, kind="replace",
        anchor="        cancelled = await self._cancel_outstanding_requests_locked(room)",
        new="        cancelled = ()",
        want=f"{PG}.py::test_property_63_writer_revocation_bumps_fence_and_cancels_requests",
        why="不取消 outstanding request ⇒ 撤销后仍在飞的 forcesave 的 callback 回来时会被"
            "正常 correlate 并应用（AC 4.7 要求撤销时取消 outstanding）",
    ),
    Mutation(
        id="M23", side="be", path=ROOMS, kind="replace",
        anchor="        was_writer = ParticipantMode(participant.mode) is ParticipantMode.edit",
        new="        was_writer = True",
        want=f"{PG}.py::test_view_participant_revocation_does_not_rotate_generation",
        why="把只读会话撤销也当成 writer 撤销 ⇒ 每次踢掉一个旁观者都要旋转 generation、"
            "让所有人重开编辑器（过度反应，且会被误当成「同步一直在断」）",
    ),
    Mutation(
        id="M24", side="be", path=ROOMS, kind="replace",
        anchor="    return load_callback_contract().multi_user.revocation",
        new='    return RevocationPolicy(decision="write_fence_plus_generation_rotation", '
            'oo_drop_proves=("hardcoded",), oo_drop_does_not_prove=("hardcoded",))',
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_service_reads_the_revocation_decision_from_the_contract",
        why="撤销裁决在代码里写死而不再读契约 ⇒ 契约被改回 participant-bound 时生产行为"
            "不变、也不再 fail closed，真值表退回「只有守卫在读」的死代码状态",
    ),
    Mutation(
        id="M25", side="be", path=ROOMS, kind="replace",
        anchor="        if oo_drop_confirmed:",
        new="        if False:",
        want=f"{PG}.py::test_property_63_writer_revocation_bumps_fence_and_cancels_requests",
        why="不记录 OO drop 取证时间 ⇒ 「会话确实被逐出」这条唯一可用证据在审计里消失"
            "（契约 status=1 的 actions 是唯一 drop 取证来源）",
    ),

    # ══ 五、AC 2.8 / 3.7：open-or-reuse 与 descriptor 确认 ════════════════
    Mutation(
        id="M26", side="be", path=ROOMS, kind="replace",
        anchor="        if existing is not None:",
        new="        if False:",
        want=f"{PG}.py::test_ac_2_8_same_generation_reuses_room_instead_of_creating_second",
        wants=(f"{PG}.py::test_superseded_generation_cannot_be_reopened",),
        why="退化成「总是新建 room」⇒ 第二个用户进来时撞 uq_wpoor_generation，"
            "AC 2.8「同一 generation 的协同用户可进入同一 active room」直接 500",
    ),
    Mutation(
        id="M27", side="be", path=ROOMS, kind="replace",
        anchor="            if state not in {RoomState.opening, RoomState.active, RoomState.close_barrier}:",
        new="            if False:",
        want=f"{PG}.py::test_superseded_generation_cannot_be_reopened",
        why="已 superseded 的代际被当成可复用 ⇒ 撤销后重开会拿到那个已作废的 room，"
            "fence/refresh 状态全部带过来，用户看到「打开成功但永远存不上」",
    ),
    Mutation(
        id="M28", side="be", path=ROOMS, kind="replace",
        anchor="        if str(representation.entry_id) != str(scope.entry_id):",
        new="        if False:",
        want=f"{PG}.py::test_room_cannot_reuse_representation_of_another_entry",
        why="room 可以拿别的 entry 的 representation ⇒ doc_key 指向的入口与实际打开的"
            "文件不是一回事，回写会落到错误入口",
    ),
    Mutation(
        id="M29", side="be", path=REPOSITORY, kind="replace",
        anchor="        room.client_confirmed_base_version_id = confirmation.content_version_id",
        new="        pass",
        want=f"{PG}.py::test_confirm_descriptor_activates_room_and_sets_client_baseline",
        wants=(f"{PG}.py::test_ac_4_1_request_freeze_uses_confirmed_base_and_stable_fingerprint",),
        why="confirm-descriptor 不再写 client-confirmed 基线 ⇒ 后续 forcesave 因"
            "「基线未建立」被永久拒绝，或（更糟）退回用 room.opened_base 当客户端基线",
    ),
    Mutation(
        id="M30", side="be", path=ROOMS, kind="replace",
        anchor="            expected_bundle.assert_same_as(actual_bundle, where=\"confirm-descriptor\")",
        new="            pass",
        want=f"{PG}.py::test_stale_descriptor_bundle_identity_is_rejected",
        why="descriptor 回传的 bundle identity 不再逐项比对 ⇒ 只比 representation_id 的话，"
            "同 representation 上被 alias 换掉的 bundle 不会被发现（AC 3.7 / P28）",
    ),
    Mutation(
        id="M31", side="be", path=ROOMS, kind="replace",
        anchor="            lease_token_hash=hashlib.sha256(lease_token.encode(\"utf-8\")).hexdigest(),",
        new="            lease_token_hash=hashlib.sha256(b\"fixed\").hexdigest(),",
        want=f"{PG}.py::test_ac_2_6_participant_lease_is_per_user_in_shared_room",
        why="所有人的 lease token hash 相同 ⇒ 逐人 lease 退化成共享凭证，"
            "「同 room 用户的 forcesave 发起权限逐人校验」失去载体（AC 2.6）",
    ),
    Mutation(
        id="M32", side="be", path=ROOMS, kind="replace",
        anchor="            contributor_user_ids=contributor_user_ids,",
        new="            contributor_user_ids=(),",
        want=f"{PG}.py::test_ac_4_1_request_freeze_uses_confirmed_base_and_stable_fingerprint",
        why="contributor 集合不进 fingerprint ⇒ 不同贡献者集合的两次请求被判成同一次"
            "重放并返回旧 request（Requirement 4.1 要求 contributor digest 参与等值比对）",
    ),

    # ══ 六、canonical digest（models.py 的两个新函数）════════════════════
    Mutation(
        id="M33", side="be", path=MODELS, kind="replace",
        anchor="    for slot in BundleSlot:",
        scope="        \"bundle-slots-inventory:v1\",",
        offset=6,
        new="    for slot in list(slots):",
        want=f"{U}.py::TestBundleSlotsDigest::test_digest_is_deterministic_and_order_independent",
        why="按 dict 插入序算 typed-slot digest ⇒ 同一 bundle 在 repository 构造与 "
            "descriptor 构造两条路径上算出不同值，表现为「明明同一个 bundle 却报 identity "
            "漂移」，而两边都没错",
    ),
    Mutation(
        id="M34", side="be", path=MODELS, kind="replace",
        anchor="        if spec is None:",
        new="        if spec is None and False:",
        want=f"{U}.py::TestBundleSlotsDigest::test_slot_omission_fails_closed",
        why="slot 缺席被静默跳过 ⇒ 「缺 instrumentation」与「有 instrumentation」算出"
            "同一个 digest，slot omission 不再 fail closed（Requirement 2.3）",
    ),
    Mutation(
        id="M35", side="be", path=MODELS, kind="replace",
        anchor="    normalized = sorted({str(item).strip().lower() for item in contributor_user_ids if str(item).strip()})",
        new="    normalized = [str(item).strip().lower() for item in contributor_user_ids if str(item).strip()]",
        want=f"{U}.py::TestContributorSnapshotDigest::test_order_and_case_insensitive_but_membership_sensitive",
        wants=(f"{PG}.py::test_ac_4_1_request_freeze_uses_confirmed_base_and_stable_fingerprint",),
        why="contributor 按到达序入 digest ⇒ OO 的 history.changes 顺序随编辑时序变化，"
            "同一批贡献者算出不同 digest，合法重放被误判 409",
    ),

    # ══ 七、真值表 fail-closed（oo_contract.py）══════════════════════════
    Mutation(
        id="M36", side="be", path=CONTRACT, kind="replace",
        anchor="    if schema_version != SUPPORTED_SCHEMA_VERSION:",
        new="    if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_drifted_schema_version",
        why="真值表版本漂移不再 fail closed ⇒ 按已知字段「尽力解析」一个未知版本的契约，"
            "未定义语义被静默当成旧语义处理",
    ),
    Mutation(
        id="M37", side="be", path=CONTRACT, kind="replace",
        anchor="    if policy.follow_redirects or policy.max_redirects != 0:",
        new="    if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_redirect_following",
        why="下载策略允许跟随 3xx ⇒ allowlist 与已校验 IP 全部被绕过（SSRF 面重开，"
            "Requirement 5.6）",
    ),
    Mutation(
        id="M38", side="be", path=CONTRACT, kind="replace",
        anchor="    if allowed:",
        new="    if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_participant_bound_authorization",
        why="participant-bound callback 授权不再被拒 ⇒ 把 route participant 当成聚合 "
            "artifact 的唯一作者，Task 4 已实证三者不同一（Property 63）",
    ),
    Mutation(
        id="M39", side="be", path=CONTRACT, kind="replace",
        anchor="    if parsed.in_flight_grace_seconds >= parsed.forcesave_callback_wait_timeout_seconds:",
        new="    if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_grace_swallowing_timeout",
        why="grace 可以大于等于 callback 等待超时 ⇒ grace 永远吃掉超时判定，"
            "operation 不可能落可重试 timeout，前端永久 loading（Requirement 4.4）",
    ),
    Mutation(
        id="M40", side="be", path=CONTRACT, kind="replace",
        anchor="    if not rows:",
        new="    if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_emptied_status_table",
        why="status 真值表被削空也能加载 ⇒ 所有 status 都变成「未知」，全部 callback "
            "落 error；或（若 unknown 分支也被放宽）静默 error=0 不留痕",
    ),
    Mutation(
        id="M41", side="be", path=CONTRACT, kind="replace",
        anchor="        if rule.application_allowed and not rule.download_required:",
        new="        if False:",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_loader_rejects_application_without_download",
        why="允许「不下载却能建 application」⇒ application 可以建在不存在的 substrate 上，"
            "违反「只能以 durable incoming 为 substrate」",
    ),
    Mutation(
        id="M42", side="be", path=CONTRACT, kind="replace",
        # 🔴 落点必须是**严格性判据本身**，不是末尾 `return raw_status`。
        # 首轮把它改成 `return int(raw_status)` 时判 GREEN，原因是那一行只在「已确认是
        # 严格 int」之后才执行 ⇒ `int(6)` 是恒等变换，语义完全没变（无效变异）。
        anchor="    if isinstance(raw_status, bool) or not isinstance(raw_status, int):",
        new="    if isinstance(raw_status, bool):",
        want=f"{U}.py::TestCallbackContractHasProductionConsumer::test_normalize_callback_status_never_coerces",
        wants=(f"{U}.py::TestCallbackContractHasProductionConsumer::test_unknown_status_fails_visible",),
        why="用 `int()` 强转不可信 JSON 的 status ⇒ `int(\"6\")`/`int(6.0)` 会把未知形态"
            "猜成已知 status，正是契约 unknown_status_policy.forbidden[1]「按最近似 status "
            "猜测处理」禁止的行为",
    ),

    # ══ 八、生产接线（RG-17 的两侧：mtime 与 participant lease）═══════════
    #
    # 这一组是本轮新增的核心：Task 73 明写「Task 21 room service 未接线，故
    # `room_service_state=pending_room_service`、`participant_lease=False`、RG-17 全量必红」。
    # 接线之后那道门才可能绿，所以必须有变异证明「拆掉接线就重新变红」——
    # 否则「已接线」和之前的「未接线」一样只是一句声明。
    Mutation(
        id="M43", side="be", path=OO_ROUTER, kind="replace",
        anchor="    doc_key = await _room_identity.resolve_room_doc_key(db, wp_id=wp_id, entry_id=_room_entry_id)",
        new='    doc_key = f"{_sheet_wp_code}:{file_path.stat().st_mtime_ns}"',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_production_routers_no_longer_derive_doc_key_from_mtime",
        wants=(
            f"{U}.py::TestDocKeyIsMtimeFree::test_rg17_is_clear_on_the_real_manifest",
        ),
        why="把 sheet 端点的 doc_key 退回 mtime 形态 ⇒ 一次写盘就轮转 doc_key、切断进行中"
            "的协同会话，且两个用户在不同时刻打开同一底稿会各自进一间房、最后保存的人"
            "静默覆盖另一个人的改动。RG-17 的 mtime 门必须立刻在**真实 manifest** 上打红",
    ),
    Mutation(
        # 🔴 首轮这条写成「在 import 行后加一个别名赋值」，判 GREEN —— 那是**无效变异**：
        # 直接调用点一个字节都没动，AST 判据当然照旧命中。落点必须是**调用本身**。
        id="M44", side="be", path=OO_ROUTER, kind="replace",
        anchor="    doc_key = await _room_identity.resolve_room_doc_key(db, wp_id=wp_id, entry_id=_room_entry_id)",
        new='    doc_key = f"{_sheet_wp_code}-{_room_entry_id}"',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_room_service_is_wired_into_production_outside_the_package",
        why="sheet 端点不再调 room service，改成本地拼一个 key ⇒ room 身份退回「路由各自"
            "发明」的状态。这条与 M43 分工不同：M43 检验「mtime 是否回来了」，本条检验"
            "「接线判据看的是**真实调用点**而不是 import 存在」—— 只 import 不调用就是"
            "additive 死代码（假绿第①源），而本地拼 key 恰好不含 mtime，故 M43 的判据"
            "对它完全不敏感，只有接线判据能抓到",
    ),
    Mutation(
        id="M45", side="be", path=EDITOR_ROUTER, kind="replace",
        anchor="    doc_key = await _room_identity.resolve_room_doc_key(db, wp_id=wp_id, entry_id=_room_entry_id)",
        new='    doc_key = f"wp-{wp_id}-{wp.file_version}-raw"',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_seam_does_not_use_file_version_or_prefill_state",
        why="Word 端点退回用 `file_version` 当文档身份 ⇒ Requirement 2.1 明文禁止它充当"
            "跨通道同步版本；且 `file_version` 由文件生命周期驱动，会在与内容无关的时刻"
            "轮转 doc_key",
    ),
    Mutation(
        id="M46", side="be", path=SEAM, kind="replace",
        anchor="    slot = WHOLE_WORKBOOK_SLOT if whole_workbook else _slug(sheet_name)",
        new='    slot = "shared"',
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_seam_entry_id_separates_sheet_whole_workbook_and_word",
        why="所有 sheet 与整册视图共享一个 entry_id ⇒ 整册视图会拿到缓存的单 sheet 副本"
            "（其余 sheet 已被 openpyxl 隐藏），用户看到的「完整 Excel」只有一张表。"
            "旧实现正是靠 mtime 轮转掩盖这一点",
    ),
    Mutation(
        id="M47", side="be", path=SEAM, kind="replace",
        anchor="        raise ValueError(\"sheet_name 不得为空 —— 单 sheet 视图必须能定位到具体 sheet\")",
        new="        slot = \"unnamed\"",
        want=f"{U}.py::TestDocKeyIsMtimeFree::test_seam_entry_id_separates_sheet_whole_workbook_and_word",
        why="空 sheet 名不再 fail closed ⇒ 所有「拿不到 sheet 名」的请求撞进同一个 room"
            "身份，回写会落到错误入口",
    ),

    # ══ 九、AC 2.5 / 2.10：representation 准入三道门（各自独立 error_code）═
    Mutation(
        id="M48", side="be", path=ROOMS, kind="replace",
        anchor="        if pointer is None:",
        new="        if False:",
        want=f"{PG}.py::test_only_published_non_candidate_drift_free_representation_enters_room"
             "[no_pointer-representation_not_published]",
        why="没有 current pointer 也能开 room ⇒ 「有 representation 行」被当成「已发布」，"
            "AC 2.5 要求的是 published representation",
    ),
    Mutation(
        id="M49", side="be", path=ROOMS, kind="replace",
        anchor="        if pointer.current_representation_id != representation.id:",
        new="        if False:",
        want=f"{PG}.py::test_historical_generation_is_rejected_by_the_publication_gate",
        why="历史代际（已被新代际取代）仍可开 room ⇒ 旧 generation 的 room 被重新挂给 OO，"
            "旧会话继续往已作废代际里写",
    ),
    Mutation(
        id="M50", side="be", path=ROOMS, kind="replace",
        anchor="        if staged is not None:",
        new="        if False:",
        want=f"{PG}.py::test_only_published_non_candidate_drift_free_representation_enters_room"
             "[staged_candidate-representation_not_published]",
        why="未 finalize 的 upgrade candidate 的 staged 产物可以进 room ⇒ 违反"
            "「candidate 的 resolver/room/current pointer 均不得读取」，编辑器会打开一份"
            "尚未验收的升级产物",
    ),
    Mutation(
        id="M51", side="be", path=ROOMS, kind="replace",
        anchor="            if frozen_value != live_value:",
        new="            if False:",
        want=f"{PG}.py::test_only_published_non_candidate_drift_free_representation_enters_room"
             "[alias_drift-bundle_alias_drift]",
        why="representation 冻结的 bundle digest 不再与 bundle 行比对 ⇒ bundle 被 registry "
            "alias 换过内容时，descriptor 会冻结一份「id 相同、内容已换」的假身份"
            "（AC 2.10「历史读取不得按当前 registry alias 重组 bundle」）",
    ),
    Mutation(
        id="M52", side="be", path=ROOMS, kind="replace",
        anchor="        if representation.authority_model_definition_id != (",
        new="        if False and representation.authority_model_definition_id != (",
        want=f"{PG}.py::test_only_published_non_candidate_drift_free_representation_enters_room"
             "[authority_drift-bundle_alias_drift]",
        why="authority model definition 被换成另一份也不再被发现 ⇒ 权威模型漂移"
            "（projection_contract ↔ custom_authoritative_ooxml）会静默改变整条回写语义",
    ),

    # ══ 十、AC 2.6 末句：route credential 与 contributor 三分 ═════════════
    Mutation(
        id="M53", side="be", path=ROOMS, kind="replace",
        anchor='            _ROUTE_CREDENTIAL_NAMESPACE, f"{room_id}|{generation}|{normalized_key}"',
        new='            _ROUTE_CREDENTIAL_NAMESPACE, f"{room_id}"',
        want=f"{U}.py::TestRouteCredentialIsRoomScoped::test_deterministic_and_bound_to_all_three_components",
        why="凭证只绑 room ⇒ generation 旋转后旧 callback 仍然合法，AC 2.8 的 supersede "
            "形同虚设；doc_key 相同而 room 被重建的情形也无法区分",
    ),
    Mutation(
        id="M54", side="be", path=ROOMS, kind="replace",
        anchor="    if credential_id != expected.credential_id:",
        new="    if False:",
        want=f"{U}.py::TestRouteCredentialIsRoomScoped::test_assert_route_credential_rejects_foreign_credential",
        wants=(f"{PG}.py::test_route_credential_of_another_generation_is_rejected",),
        why="任何 credential 都被接受 ⇒ callback 的 room/generation 绑定失效，"
            "攻击者可自选凭证（Requirement 5.1）",
    ),
    Mutation(
        id="M55", side="be", path=ROOMS, kind="replace",
        anchor="            room_id=room.id, generation=int(room.generation), doc_key=room.doc_key",
        new="            room_id=room.id, generation=1, doc_key=room.doc_key",
        want=f"{PG}.py::test_route_credential_is_minted_from_the_room_row_not_the_caller",
        why="凭证的 generation 不再取自 room 行 ⇒ 所有代际共用一个凭证，旧代际 callback "
            "永久合法",
    ),
    Mutation(
        id="M56", side="be", path=ROOMS, kind="replace",
        anchor="        contract = load_callback_contract().multi_user",
        new='        contract = type("C", (), {"contributor_snapshot_source": "users"})()',
        want=f"{U}.py::TestContributorDomainMatchesSchemaAndContract::test_room_service_reads_contributor_source_from_the_contract",
        wants=(f"{PG}.py::test_initiator_route_and_contributor_land_in_three_separate_places",),
        why="contributor 来源不再从 Task 4 契约读 ⇒ 退回「只有守卫在读真值表」的死代码"
            "状态；且 `users` 在 status 6 只含最后编辑者一人，审计快照会丢掉全部并发贡献者",
    ),
    Mutation(
        id="M57", side="be", path=ROOMS, kind="replace",
        anchor="                    confidence=confidence,",
        new="                    confidence=ContributorConfidence.exact,",
        want=f"{PG}.py::test_contributor_rows_carry_source_and_confidence_per_task4_evidence",
        why="OO 派生的 contributor 被标成 `exact` ⇒ 把审计快照当授权凭据用。Task 4 §4 实证"
            "`history.changes` 在用户被 `c=drop` 之后**仍然列出该用户**，所以它永远达不到 "
            "exact（契约 contributor_snapshot_caveat）",
    ),
    Mutation(
        id="M58", side="be", path=ROOMS, kind="replace",
        anchor="            if ParticipantMode(participant.mode) is not ParticipantMode.edit:",
        new="            if False:",
        want=f"{PG}.py::test_view_participant_is_never_recorded_as_contributor",
        why="只读会话被记成 contributor ⇒ Property 44「只读或被撤销 contributor 零内容"
            "版本」失效，审计上会出现「旁观者贡献了内容」",
    ),
    Mutation(
        id="M59", side="be", path=ROOMS, kind="replace",
        anchor="        if ParticipantMode(initiator.mode) is not ParticipantMode.edit:",
        new="        if False:",
        want=f"{PG}.py::test_view_participant_cannot_be_the_initiator",
        why="只读 participant 可以当 forcesave initiator ⇒ view 会话间接产生内容版本",
    ),
    Mutation(
        id="M60", side="be", path=MODELS, kind="replace",
        anchor='    active_writer_snapshot = "active_writer_snapshot"',
        new='    active_writer_snapshot = "active_writer_snapshot"\n    guessed = "guessed"',
        want=f"{U}.py::TestContributorDomainMatchesSchemaAndContract::test_source_and_confidence_enums_equal_the_v151_check_domains",
        why="Python 侧封闭域多出一个值而 V151 的 CHECK 不认 ⇒ 写库在生产才炸；"
            "两处真源必须双向锁死",
    ),

    # ══ 十一、AC 2.9 / 10.11：canonical fence 与 same-application fold ════
    Mutation(
        id="M61", side="be", path=ROOMS, kind="replace",
        anchor="            folded = fold_effective_sequence(previous_effective, incoming_request_sequence)",
        new="            folded = incoming_request_sequence",
        want=f"{PG}.py::test_lower_request_sequence_never_regresses_effective_sequence",
        why="不再取 GREATEST ⇒ 迟到的**较低** sequence 会把 effective 拉回去，"
            "Task 27 的 resolve 于是把更新的裁决判成 stale",
    ),
    Mutation(
        id="M62", side="be", path=ROOMS, kind="replace",
        anchor="                app.effective_request_sequence = folded",
        new="                pass",
        want=f"{PG}.py::test_same_application_higher_request_only_folds_effective_sequence",
        why="同 application key 的较高 request 不再抬高 `effective_request_sequence` ⇒ "
            "fold 语义整条丢失，后续 request 会被当成「更旧」而被 supersede",
    ),
    Mutation(
        id="M63", side="be", path=ROOMS, kind="replace",
        anchor="        if app.room_id != room.id:",
        new="        if False:",
        want=f"{PG}.py::test_fence_refuses_application_outside_this_room"
             "[cross_room_error]",
        wants=(
            f"{PG}.py::test_fence_refuses_application_outside_this_room"
            "[cross_generation_error]",
        ),
        why="别的 room 的 application 可以推进本 room 的 fence ⇒ 等价于「用别的文档的 "
            "durable 事实给本房间放行」。判据必须用**同 generation** 的另一个 room，"
            "否则 generation 判据会先命中并遮蔽本条",
    ),
    # M64 已撤销（原为「删掉 `app.generation == room.generation` 检查」）。
    #
    # 首轮判 GREEN，逐条归因后结论是**生产代码缺陷**而不是守卫缺陷：那道检查 provably
    # 不可达 —— V151 把 room 的 `generation`、application 的 `room_id` 与 `generation`
    # 三者全锁成 immutable，而 application 的 generation 是在 room row lock 内从该 room
    # 复制来的，所以 `app.room_id == room.id` 成立时 generation 必然相等。
    #
    # 处置：删掉那段死代码（留着它会让「删掉它」永远判 GREEN，下一个人会以为守卫有缺陷
    # 而去放宽判据），并把依据正面钉成
    # `test_application_room_and_generation_are_db_immutable` —— DB 哪天解锁任一条，
    # 那条守卫打红，检查就必须补回来。
    Mutation(
        id="M64", side="be", path=ROOMS, kind="replace",
        anchor="            raise CanonicalFenceError(f\"application 不存在: {application_id}\")",
        new="            return None  # type: ignore[return-value]",
        want=f"{PG}.py::test_fence_refuses_application_outside_this_room"
             "[missing_application_error]",
        why="不存在的 application 静默通过 ⇒ room 的 `latest_durable_application_id` 会被"
            "指向一个悬空 FK（或直接 AttributeError 500）。原 M64 的落点已被证明是死代码，"
            "见上方注释",
    ),
    Mutation(
        id="M65", side="be", path=ROOMS, kind="replace",
        anchor="            room=room, application_id=app.id, effective_request_sequence=folded",
        new="            room=room, application_id=app.id, effective_request_sequence=0",
        want=f"{PG}.py::test_server_advance_also_points_room_canonical_fence_at_that_application",
        wants=(f"{PG}.py::test_same_application_higher_request_only_folds_effective_sequence",),
        why="传 0 给 room fence ⇒ 仓储侧的单调守卫直接 return，room 的 "
            "`latest_durable_application_id/latest_durable_sequence` 永不推进。于是出现"
            "「server 已推进、canonical fence 还指着上一个 application」的中间态，"
            "Task 27 的 resolve 读到它会把一次合法 resolve 判成 stale（AC 10.11 要求"
            "二者在同一 room lock 事务内原子决定）",
    ),

    # ══ 十二、AC 4.11：后续 request 从**已确认快照**冻结 base ══════════════
    Mutation(
        id="M66", side="be", path=ROOMS, kind="replace",
        anchor="        base_version_id = baselines.client_confirmed_base_version_id",
        new="        base_version_id = confirmation.content_version_id",
        want=f"{PG}.py::test_freeze_base_follows_the_settled_snapshot_not_the_confirmation_row",
        why="退回从 immutable 的 confirmation 行取 base ⇒ `settle_client_baseline` 推进过"
            "快照之后，第二次 forcesave 的三方 merge 仍以「打开时那一版」为 base，"
            "第一次已合并进去的改动会被当成本次新改动**再合一遍**；若第一次做过冲突裁决，"
            "裁决结果会被这次重放覆盖（AC 4.11「后续 request 从该确认快照冻结 bundle/base」）",
    ),
    Mutation(
        id="M67", side="be", path=ROOMS, kind="replace",
        anchor="        base_projection_sha256 = str(baselines.client_confirmed_projection_sha256 or \"\")",
        new="        base_projection_sha256 = confirmation.projection_sha256",
        want=f"{PG}.py::test_freeze_base_follows_the_settled_snapshot_not_the_confirmation_row",
        why="projection digest 仍取旧 confirmation ⇒ base 版本对了但 projection 摘要没跟上，"
            "三方 merge 的 base 侧失真（比整体不跟进更难查：版本号看着是对的）",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task21_room_service.py",
            "backend/tests/workpaper_sync/test_task21_room_service_pg.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider", "-p", "no:randomly",
        ],
        # 冻结基线来源：Task 21 收口实测（仓库根执行）
        #   test_task21_room_service.py      98 passed（离线纯判据 + 接线判据 + 契约 fail-closed + 反向自检）
        #   test_task21_room_service_pg.py   56 passed（真库 room 行为 + 准入/fence/contributor + 去遮蔽场景 + DB 不变量）
        baseline_backend_passed=154,
    ))
