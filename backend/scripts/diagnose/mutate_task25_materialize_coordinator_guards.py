# -*- coding: utf-8 -*-
"""Task 25 变异检验：HTML→OO coordinator、pending token 与唯一 launch descriptor 守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 25
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.18
Properties: P8 / P9 / P10 / P11 / P67

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task25_materialize_coordinator_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task25_materialize_coordinator_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task25_materialize_coordinator_guards.py --run all --out report.json

═══ 七类落点 ═══

1. **token 逐项比对**（五类拒绝各一条）—— 短路任一条，离线守卫必红。这批必须逐条，
   因为真库路径只会走到第一个失败的那条，剩下四条会被遮蔽成不可达分支。
2. **descriptor 构造期判据** —— UUID 全零、digest 形态、下界、typed slot 齐备、
   空 config 各一条。它们是 Property 11「字段完整后才 mount」的全部落点。
3. **preflight 顺序与映射** —— capability 门位置、四条 except 映射、contract 门。
   顺序被改动时（capability 门挪到 resolver 之后）离线守卫有专门断言 `calls == 0`。
4. **单次 commit / 单事务 / 单 revision 自证** —— 把三条自证改成恒真，真库侧必红。
5. **幂等复用谓词** —— 三个比较项逐条放宽（projection digest / bundle digest /
   substrate representation），每条都让 AC 3.6 变成「把不同内容判成同一件事」或
   「永远命中不了」。
6. **room/participant/operation 记账** —— room 创建位置（挪到 commit 之前 ⇒ P8 的
   「零 room」失效）、lease 复用（去掉 ⇒ 重放撞唯一约束）、operation 终态记账。
7. **authorization-before-idempotency** —— 授权阶段 scope-index 唯一性、阶段链强制、
   AST 判据的覆盖范围。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 不在判据作用域内；
* 绝对 `line=` 定位 —— 行号随上游补类/补注释漂移（Task 22 M02 实测 ANCHOR-MISS）；
  需要消歧的一律 `scope` + `offset`；
* 锚在 `try:` 行 —— 该行没有语义，替换它只会造 SyntaxError（判 ERROR 而非 RED）；
* 短路 `assert_descriptor_mountable` 的**整体**调用 —— 那会让 22 条子判据一起红，
  分辨不出哪一条在起作用。因此逐类判据各有一条独立变异。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

MC = "backend/app/services/workpaper_sync/materialize_coordinator.py"

OFF = "test_task25_materialize_coordinator"
PG = "test_task25_materialize_coordinator_pg"

MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、token 逐项比对（Property 10 的五类拒绝）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=MC, kind="replace",
        anchor="        if token.idempotency_key != request.idempotency_key:",
        new="        if False:",
        want=f"{OFF}.py::test_token_request_mismatch_has_its_own_refusal_type",
        why="不再比对 Idempotency-Key ⇒ A 次 flush 的 token 可以配上 B 次请求的 key，"
            "「同 key + 同 payload 才返回同结果」的语义断裂（Requirement 3.1）",
    ),
    Mutation(
        id="M02", side="be", path=MC, kind="replace",
        anchor="        if token.expires_at <= _now():",
        new="        if False:",
        want=f"{OFF}.py::test_expired_token_is_refused_with_its_own_type",
        why="过期 token 仍可消费 ⇒ Requirement 3.1 的「短 TTL」形同虚设。"
            "TTL 与 payload/revision/scope 各自一个异常类型，故本条不会被其余遮蔽",
    ),
    Mutation(
        id="M03", side="be", path=MC, kind="replace",
        anchor="        if int(token.expected_revision) != int(request.expected_revision):",
        new="        if False:",
        want=f"{OFF}.py::test_token_request_mismatch_has_its_own_refusal_type",
        why="不再比对 expected revision ⇒ 别人在 flush 之后提交过，本次仍按旧 base "
            "materialize（Property 10「同 key 不同 content base 必须拒绝」）",
    ),
    Mutation(
        id="M04", side="be", path=MC, kind="replace",
        anchor="        if actual != token.payload_sha256:",
        new="        if False:",
        want=f"{OFF}.py::test_token_request_mismatch_has_its_own_refusal_type",
        why="不再比对 payload digest ⇒ 用户 flush 后又改了内容，materialize 却把**新**"
            "内容按**旧** token 提交（Property 10「同 key 不同 payload 必须拒绝」）",
    ),
    Mutation(
        id="M05", side="be", path=MC, kind="replace",
        anchor="            or token.user_id != request.user_id",
        new="            or False",
        want=f"{OFF}.py::test_token_request_mismatch_has_its_own_refusal_type",
        why="token 可跨 user 使用 ⇒ 甲的 flush 能被乙消费。scope 五项逐条变异，"
            "合成一条 `or` 链时删掉任一项都会被其余项遮蔽",
    ),
    Mutation(
        id="M06", side="be", path=MC, kind="replace",
        anchor="            or str(token.sheet_key) != str(request.sheet_key)",
        new="            or False",
        want=f"{OFF}.py::test_token_request_mismatch_has_its_own_refusal_type",
        why="token 可跨 sheet 使用 ⇒ 一个 sheet 的 flush 写进另一个 sheet。"
            "与 M05 分开：两项共用一条判据时互相遮蔽",
    ),
    Mutation(
        id="M07", side="be", path=MC, kind="replace",
        anchor="        if not hmac.compare_digest(signature, self._mac(body)):",
        new="        if False:",
        want=f"{OFF}.py::test_tampered_token_fails_closed_before_any_db_read",
        why="不再验签 ⇒ 任何人都能伪造 token 跨 scope 消费 pending mutation。"
            "真库侧 `foreign_secret` 场景一并打红",
        wants=(
            f"{OFF}.py::test_token_signed_by_another_secret_is_refused",
            f"{PG}.py::test_no_valid_token_means_zero_room_zero_operation_zero_descriptor[foreign_secret]",
        ),
    ),
    Mutation(
        id="M08", side="be", path=MC, kind="replace",
        anchor="            raise PendingTokenRequiredError(",
        new="            raise PendingTokenSignatureError(",
        want=f"{OFF}.py::test_missing_token_is_refused_before_anything_else",
        why="把「压根没 flush」并进「token 坏了」⇒ P8 的判据（Requirement 3.2 的"
            "「模式切换停留在 HTML」）变成不可达分支，其定向变异永久 GREEN。"
            "真库侧「两类拒绝必须可分辨」一并打红",
        wants=(
            f"{PG}.py::test_missing_token_and_tampered_token_are_different_refusals",
        ),
    ),
    Mutation(
        id="M09", side="be", path=MC, kind="replace",
        anchor="class PendingTokenRevisionError(MaterializeCoordinatorError):",
        new="class PendingTokenRevisionError(PendingTokenPayloadError):",
        want=f"{OFF}.py::test_refusals_are_pairwise_disjoint_except_the_declared_preflight_group",
        why="让 revision 拒绝成为 payload 拒绝的子类 ⇒ `pytest.raises(PayloadError)` "
            "顺手吃掉 revision，「别人提交过」与「你改了内容」永久不可分辨。"
            "本 spec 已为这个形态付过三次代价",
        wants=(f"{OFF}.py::test_every_refusal_has_a_distinct_error_code",),
        tags=("regression",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、descriptor 构造期判据（Property 11）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M10", side="be", path=MC, kind="replace",
        anchor="        if not isinstance(value, uuid.UUID) or value.int == 0:",
        new="        if not isinstance(value, uuid.UUID):",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="放过全零 UUID ⇒ `uuid.UUID(int=0)`（Task 15 用它当事务前占位）会被当成"
            "有效 room/representation id 下发，前端拿着它去挂载",
        wants=(
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[zero_bundle_uuid]",
        ),
    ),
    Mutation(
        id="M11", side="be", path=MC, kind="replace",
        anchor="        if not is_digest(value):",
        scope="        \"artifact_sha256\", \"authority_model_definition_sha256\", \"definition_bundle_sha256\",",
        offset=3,
        new="        if False:",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="不再校验 descriptor 的三个 digest ⇒ 空串/全零/大写 hex 都能下发，"
            "而 confirm-descriptor 的逐项比对就建立在这些值上（Requirement 2.3 明确"
            "禁止空串与全零 hash）",
        wants=(
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[short_bundle_digest]",
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[uppercase_authority_digest]",
        ),
    ),
    Mutation(
        id="M12", side="be", path=MC, kind="replace",
        anchor="        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:",
        new="        if not isinstance(value, int):",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="放过 0/负数 generation、revision 与 fence ⇒ 「还没取到」的默认值被当成"
            "有效 identity。room generation 从 1 起（`derive_doc_key` 的前提）",
        wants=(
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[fence_zero]",
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[revision_zero]",
        ),
    ),
    Mutation(
        id="M13", side="be", path=MC, kind="replace",
        anchor="    absent = [key for key in _REQUIRED_SLOT_KEYS if key not in slots]",
        new="    absent = []",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="typed slot 缺失（omission）不再 fail closed ⇒ Requirement 2.3 的"
            "「每个 slot 必须出现，可选 child 只能用版本化 typed null marker」被绕过",
        wants=(
            f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[missing_instrumentation_slot]",
        ),
    ),
    Mutation(
        id="M14", side="be", path=MC, kind="replace",
        anchor="        if not is_digest(spec.get(\"sha256\")):",
        new="        if False:",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="slot digest 全零/空串被放过 ⇒ 「非空 typed slots」这条承诺只剩注释。"
            "与 M13 分开：前者判 slot **在不在**，后者判 slot **内容合不合法**",
    ),
    Mutation(
        id="M15", side="be", path=MC, kind="replace",
        anchor="    if not isinstance(config, Mapping) or not config:",
        new="    if not isinstance(config, Mapping):",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="空 config 被放过 ⇒ 组件仍需自行请求一次 config，正是 Property 11 明令"
            "禁止的「组件不得再次请求 config」",
    ),
    Mutation(
        id="M16", side="be", path=MC, kind="replace",
        anchor="        assert_descriptor_mountable(self)",
        new="        pass",
        want=f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed",
        why="descriptor 不再有构造期判据 ⇒ 「字段完整后才 mount」退化成前端自觉，"
            "半个 descriptor 可以被下发。这条与 M10~M15 的关系是「整体 vs 逐类」，"
            "两者都必须可 falsify",
        wants=(f"{OFF}.py::test_incomplete_descriptor_cannot_be_constructed[empty_config]",),
    ),
    Mutation(
        id="M17", side="be", path=MC, kind="replace",
        anchor='                    "forcesave": False,',
        new='                    "forcesave": True,',
        want=f"{OFF}.py::test_onlyoffice_config_never_enables_editor_side_forcesave",
        why="打开编辑器侧自动 forcesave ⇒ 产生**无 frozen request** 的孤儿 callback，"
            "只能进 recovery case（AC 4.1 明确「不得把 `customization.forcesave=true` "
            "当成保存完成」）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、preflight 顺序与映射（Requirement 3.3 / 3.9）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=MC, kind="replace",
        anchor="        if request.capability in _NON_MATERIALIZABLE:",
        new="        if False:",
        want=f"{OFF}.py::test_preflight_refuses_non_materializable_capability_before_resolving",
        why="`single_html` / `unreachable` 可以 materialize ⇒ Requirement 3.9 的"
            "「不得创建空白 OO artifact」被绕过。真库侧同名场景一并打红",
        wants=(
            f"{PG}.py::test_preflight_rejections_are_422_with_zero_room_and_zero_operation[capability_single_html]",
        ),
    ),
    Mutation(
        id="M19", side="be", path=MC, kind="replace",
        anchor="    {Capability.single_html, Capability.unreachable}",
        new="    {Capability.unreachable}",
        want=f"{OFF}.py::test_non_materializable_capabilities_are_exactly_single_html_and_unreachable",
        why="把 `single_html` 从禁用集合里摘掉 ⇒ 纯 HTML 入口会被造出一个空白 OO "
            "artifact。集合两侧都断言，所以「多一个」也会红",
    ),
    Mutation(
        id="M20", side="be", path=MC, kind="replace",
        anchor="        except EntryPointerMissingError as exc:",
        new="        except _NeverRaised as exc:",
        want=f"{OFF}.py::test_preflight_maps_missing_entry_pointer_to_substrate_not_published",
        why="不再把「entry 没有 published representation」映射成 422 ⇒ 它会以 500 "
            "冒出来，用户看不出该跑 template upgrader（Requirement 6.18）",
    ),
    Mutation(
        id="M21", side="be", path=MC, kind="replace",
        anchor="        except CandidateNotFinalizableError as exc:",
        new="        except _NeverRaised as exc:",
        want=f"{OFF}.py::test_preflight_maps_candidate_resolution_to_representation_still_candidate",
        why="candidate 不再被映射成 422 ⇒ P67 的「candidate 不得成为 resolver/room "
            "substrate」在 coordinator 层没有可操作诊断",
    ),
    Mutation(
        id="M22", side="be", path=MC, kind="replace",
        anchor="        except RepresentationSlotError as exc:",
        new="        except _NeverRaised as exc:",
        want=f"{OFF}.py::test_preflight_rejects_a_bundle_with_a_missing_typed_slot",
        why="typed slot 形态失败不再映射 ⇒ 与 M23（bundle 未 approved）分开是必需的："
            "两条 except 共用一个映射时，删掉任一条会被另一条接住",
    ),
    Mutation(
        id="M23", side="be", path=MC, kind="replace",
        anchor="        except RepresentationBundleError as exc:",
        new="        except _NeverRaised as exc:",
        want=f"{OFF}.py::test_preflight_rejects_a_bundle_that_is_not_approved",
        why="bundle 未 approved 不再映射成 422 ⇒ router 拿不到「批准 bundle」这个"
            "可操作原因。与 M22 各自可 falsify",
    ),
    Mutation(
        id="M24", side="be", path=MC, kind="replace",
        anchor="        if bundle.authority_model is AuthorityModel.projection_contract and (",
        new="        if False and (",
        want=f"{OFF}.py::test_preflight_refuses_projection_entry_without_a_contract",
        why="`projection_contract` 入口缺 contract 时不再拒绝 ⇒ 会降级成 contract-less "
            "模式（Requirement 3.3 明令禁止）。真库侧同名场景一并打红",
        wants=(
            f"{PG}.py::test_preflight_rejections_are_422_with_zero_room_and_zero_operation[missing_contract]",
        ),
    ),
    Mutation(
        id="M25", side="be", path=MC, kind="replace",
        anchor="class SubstrateNotPublishedError(MaterializePreflightError):",
        new="class SubstrateNotPublishedError(RepresentationStillCandidateError):",
        want=f"{OFF}.py::test_refusals_are_pairwise_disjoint_except_the_declared_preflight_group",
        why="「一个 representation 都没有」与「有但还没 finalize」共用继承关系 ⇒ "
            "用户要做的事（跑 upgrader 首次迁移 vs 批准 contract 后 finalize）不可分辨",
        wants=(f"{OFF}.py::test_every_refusal_has_a_distinct_error_code",),
    ),
    Mutation(
        id="M26", side="be", path=MC, kind="replace",
        anchor="    RepresentationStillCandidateError: 422,",
        new="    RepresentationStillCandidateError: 400,",
        want=f"{OFF}.py::test_preflight_group_is_exactly_the_422_family",
        why="422 家族与 preflight 分组基类的成员集合脱钩 ⇒ router 用 "
            "`except MaterializePreflightError` 捕获时会给出错误状态码。两侧互锁",
    ),
    Mutation(
        id="M27", side="be", path=MC, kind="replace",
        anchor="    return MATERIALIZE_REJECTION_STATUS.get(type(exc), 500)",
        new="    return MATERIALIZE_REJECTION_STATUS.get(type(exc), 400)",
        want=f"{OFF}.py::test_unknown_exception_classifies_as_500_not_400",
        why="未登记的失败被静默降级成 400 ⇒ 「协议缺一条」看起来像「用户输入错了」，"
            "fail-visible 变成 fail-silent",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、单次 commit / 单事务 / 单 revision 自证（Property 10）
    # ═══════════════════════════════════════════════════════════════════
    # 🔴 这四条的落点是**模块级纯函数**，不是内联 `if`。首轮实测五条（M28~M31 + M51）
    #    全 GREEN —— 因为内联形态在正确实现下恒不触发，短路它在任何真实场景里都观察
    #    不到差异。抽成纯函数并用合成输入喂之后才可证伪（Task 24 同一决定）。
    Mutation(
        id="M28", side="be", path=MC, kind="replace",
        anchor="    expected = 0 if (replayed or business_identity_reused) else 1",
        new="    expected = int(delta)",
        want=f"{OFF}.py::test_wrong_revision_delta_is_refused",
        why="把期望值改成实测值 ⇒ revision delta 自证退化成恒真（守卫把错值当基线锁死"
            "的形态）。这条专门证明 delta 判据不是「拿实测当期望」",
    ),
    Mutation(
        id="M29", side="be", path=MC, kind="replace",
        anchor="    if int(commit_count) != 1 or len(tuple(transaction_ids)) != 1:",
        new="    if False:",
        want=f"{OFF}.py::test_non_single_business_commit_is_refused",
        why="不再自证「恰一次 commit、恰一个事务」⇒ Task 15 的单事务见证结果被丢弃，"
            "projection 与 representation 分两个事务提交时 coordinator 不再报警",
    ),
    Mutation(
        id="M30", side="be", path=MC, kind="replace",
        anchor="    if int(actual) != int(base_revision) + 1:",
        new="    if False:",
        want=f"{OFF}.py::test_revision_target_other_than_base_plus_one_is_refused",
        why="不再自证「commit 后 revision == base+1」⇒ artifact 文件名里的 revision "
            "与数据库错位时无人发现（历史读取会取到别的版本）。与 M29 分开：一个判"
            "「提交了几次」，一个判「提交到了哪个版本」",
    ),
    Mutation(
        id="M31", side="be", path=MC, kind="replace",
        anchor="    if int(delta) != expected:",
        new="    if False:",
        want=f"{OFF}.py::test_wrong_revision_delta_is_refused",
        why="去掉 revision delta 自证 ⇒ 「一次 materialize 只推进一次 revision」这条"
            "承诺没有判据。与 M28 分开：M28 改期望值（判据仍在但恒真），"
            "M31 直接摘掉判据 —— 两种退化形态都必须可 falsify",
    ),
    Mutation(
        id="M31b", side="be", path=MC, kind="replace",
        anchor="        assert_revision_delta(",
        new="        _ = (lambda **k: None)(",
        want=f"{OFF}.py::test_coordinator_delegates_to_the_pure_accounting_functions",
        why="coordinator 不再调用纯判据 ⇒ 判据存在但没有消费方（假绿第①源：additive "
            "注入即死代码）。纯函数被抽出来之后，「它真的被调用了吗」必须单独有判据",
        wants=(
            f"{PG}.py::test_happy_path_commits_exactly_once_in_exactly_one_transaction",
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、幂等复用谓词（AC 3.6 的三个比较项）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M32", side="be", path=MC, kind="replace",
        anchor="                    WorkpaperContentVersion.projection_sha256 == payload_sha256,",
        new="                    sa.true(),",
        want=f"{PG}.py::test_changed_business_content_still_produces_a_new_revision",
        why="不再比对 projection digest ⇒ **内容真变了也复用**，用户的修改静默丢失。"
            "这是比「命中不了」更严重的方向，必须有独立判据",
    ),
    Mutation(
        id="M33", side="be", path=MC, kind="replace",
        anchor="                    WorkpaperContentRepresentation.id == pre.resolution.representation_id,",
        new="                    WorkpaperContentRepresentation.generation == 1,",
        want=f"{PG}.py::test_reuse_on_a_multi_generation_version_picks_the_current_pointer",
        why="把「substrate identity = current representation id」这个 pin 放宽成「同 "
            "content version 的第一代」⇒ 定义升级后复用会返回 gen1（未 instrumented 的"
            "旧载体），审计师打开它之后 extract 找不到 identity 载体。"
            "🔴 首轮这条落在一个**恒真**的 bundle digest 自比较上，判 GREEN —— "
            "那个比较的两侧都来自同一行（`pre.bundle` 就是从这一行解析出来的），"
            "永不可能失败。已删掉恒真判据，改锚在真正承载「substrate + bundle」身份的 pin 上",
        tags=("regression",),
    ),
    Mutation(
        id="M34", side="be", path=MC, kind="replace",
        anchor="                    WorkpaperContentVersion.id == pre.base_content_version_id,",
        new="                    WorkpaperContentVersion.parent_version_id == pre.base_content_version_id,",
        want=f"{PG}.py::test_same_business_identity_with_a_new_token_reuses_the_existing_version",
        why="回归：把「当前 version 的 projection 是否已等于本次内容」错写成「找一个 "
            "parent 是 base 的历史 version」⇒ 上次 commit 的结果与这次的基线错配一层，"
            "幂等复用**永远命中不了**（2026-08-27 真库实测过这个缺陷）",
        tags=("regression",),
    ),
    Mutation(
        id="M34b", side="be", path=MC, kind="replace",
        anchor="        if representation.id != pre.resolution.representation_id:",
        new="        if False:",
        want=f"{PG}.py::test_replay_after_the_world_moved_on_refuses_to_hand_out_a_stale_descriptor",
        why="回归：重放不再校验「记录的 representation 是否仍是 published 代际」⇒ 世界"
            "前进后老 token 会挂载一份**旧** artifact，随后的 forcesave 基线全错；"
            "修复前该路径还会把 `RoomPolicyError` 原样漏出去（router 记成 500）。"
            "🔴 首轮实测判 GREEN：短路它之后流程会往下走到 room 打开侧、抛出**同一个**"
            "异常类型把它遮蔽 ⇒ 守卫改为断言消息里的 `STALE_ON_REPLAY_MARKER`，"
            "让「哪一条判据在起作用」可分辨。2026-08-27 真库实测过这个缺陷",
        tags=("regression",),
    ),
    Mutation(
        id="M34c", side="be", path=MC, kind="replace",
        anchor='STALE_ON_REPLAY_MARKER: Final[str] = "stale-substrate/replay"',
        new='STALE_ON_REPLAY_MARKER: Final[str] = "stale-substrate/room-open"',
        want=f"{OFF}.py::test_stale_substrate_has_two_distinguishable_raise_sites",
        why="两个 raise 点标记变成同一个串 ⇒ 「哪一条判据在起作用」重新不可分辨，"
            "M34b 会退回 GREEN。标记的**可区分性**本身必须有判据",
        wants=(
            f"{PG}.py::test_replay_after_the_world_moved_on_refuses_to_hand_out_a_stale_descriptor",
        ),
    ),
    Mutation(
        id="M35", side="be", path=MC, kind="replace",
        anchor="            reuse = await self._find_business_identity_reuse(",
        new="            reuse = None if True else await self._find_business_identity_reuse(",
        want=f"{PG}.py::test_same_business_identity_with_a_new_token_reuses_the_existing_version",
        why="彻底关掉第二条幂等路径 ⇒ 同内容二次 flush 会再提交一个 revision"
            "（AC 3.6「不产生重复 content revision 或 representation」）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 六、room / participant / operation 记账（P8 / P9 / Requirement 3.8）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M36", side="be", path=MC, kind="replace",
        anchor="        live = (",
        new="        live = None if True else (",
        want=f"{PG}.py::test_token_replay_returns_the_same_result_without_a_second_revision",
        why="回归：去掉 participant lease 复用 ⇒ 同 token 重放撞 "
            "`uq_wpoop_active_lease`（room_id, user_id）唯一约束，AC 3.6 要求成功的"
            "重放变成莫名 500（2026-08-27 真库实测过这个缺陷）",
        tags=("regression",),
    ),
    Mutation(
        id="M37", side="be", path=MC, kind="replace",
        anchor="        if int(live.joined_write_fence_epoch) != int(room.write_fence_epoch):",
        new="        if False:",
        want=f"{PG}.py::test_stale_lease_after_a_fence_bump_cannot_get_a_descriptor",
        why="复用 lease 时不再比对 write fence ⇒ 期间有 participant 被撤销（fence 提升）"
            "后旧会话仍能拿到 descriptor 并继续写（AC 2.8 / 4.7）。真库侧专门有一条"
            "「提升 room fence 后重放 materialize」的场景",
    ),
    Mutation(
        id="M39", side="be", path=MC, kind="replace",
        anchor="            await self._fail_operation(operation_id, exc, stage=\"content_commit\")",
        new="            pass",
        want=f"{PG}.py::test_failed_materialize_leaves_a_terminal_operation_with_events",
        why="commit 失败不再记 operation 终态 ⇒ operation 永远停在 `created`，"
            "Requirement 3.8 的「任一失败都产生终态明确的 operation 与 transition "
            "events，不得用 warning 后继续打开旧文件」失效",
        wants=(
            f"{PG}.py::test_failed_materialize_leaves_a_terminal_operation_with_events[unmanaged_drift]",
        ),
    ),
    Mutation(
        id="M41", side="be", path=MC, kind="replace",
        anchor="            direction=OperationDirection.html_to_oo.value,",
        new="            direction=OperationDirection.oo_to_html.value,",
        want=f"{PG}.py::test_every_html_to_oo_operation_keeps_the_pre_correlation_shape",
        why="方向记错 ⇒ HTML→OO 的 operation 混进 OO→HTML 的 timeline 与指标分桶，"
            "两个方向的 application 语义完全不同（Property 64）",
        wants=(f"{PG}.py::test_html_to_oo_operation_never_binds_an_application",),
    ),
    Mutation(
        id="M42", side="be", path=MC, kind="replace",
        anchor="            definition_bundle_sha256=pre.bundle.bundle_sha256,",
        scope="            direction=OperationDirection.html_to_oo.value,",
        offset=3,
        new="            definition_bundle_sha256=\"0\" * 64,",
        want="*",
        why="operation 冻结一个全零 bundle digest ⇒ 历史 operation 无法复现 identity。"
            "V151 的 `ck_wpso_bundle_digest` 用 `wpsync_is_digest` 拒绝全零，"
            "所以这条会在数据库层打红（真库判据优于源码判据）",
    ),
    Mutation(
        id="M43", side="be", path=MC, kind="replace",
        anchor="        await self._repo.append_operation_event(",
        scope='            stage="materialize_frozen",',
        offset=-4,
        new="        _ = (lambda *a, **k: None)(",
        want=f"{PG}.py::test_every_html_to_oo_operation_keeps_the_pre_correlation_shape",
        why="operation 创建时不写 append-only event ⇒ Requirement 3.8 的 transition "
            "events 缺首条，「current state 只是 timeline 投影」不成立",
        wants=(f"{PG}.py::test_html_to_oo_operation_never_binds_an_application",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 七、authorization-before-idempotency
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M44", side="be", path=MC, kind="insert",
        anchor="        token = self._tokens.decode(request.pending_mutation_token)",
        # 两处同文本（`authorize` 与 `materialize` 各一次）⇒ 用 `authorize` 里紧随其后
        # 的唯一行做相对定位。绝对 `line=` 会随上游补注释漂移。
        scope="        self._assert_token_matches_request(token, request)",
        offset=-1,
        new="        await self._session.execute(sa.select(WorkpaperPendingMutation))",
        want=f"{OFF}.py::test_authorization_phase_reads_only_the_scope_index",
        why="在授权阶段读业务表 ⇒ 「严禁先查 pending mutation/room/operation 反推 scope "
            "或先命中幂等缓存」（AC 10.5）。AST 判据必须能抓到这一形态 —— 行为测试抓不到"
            "（结果一样）",
    ),
    Mutation(
        id="M45", side="be", path=MC, kind="replace",
        anchor='    "_assert_token_matches_request",',
        new='    "authorize",  # noqa: ERA001',
        want=f"{OFF}.py::test_authorization_phase_covers_more_than_the_entry_method",
        why="把 AST 判据的覆盖范围缩回只有入口方法 ⇒ 把业务读挪进 helper 就能绕过"
            "（本模块的 token 逐项比对正是在 helper 里）",
    ),
    Mutation(
        id="M46", side="be", path=MC, kind="replace",
        anchor="        if MaterializeStage.token_verified not in self.stages:",
        new="        if False:",
        want=f"{OFF}.py::test_create_path_product_cannot_consume_a_pending_mutation",
        why="`authorize_create()` 的产物可以直接喂给 `materialize` ⇒ 未验签 token 就能"
            "消费 pending mutation，authorization-before-idempotency 的第二半失效",
        wants=(
            f"{OFF}.py::test_unauthorized_request_cannot_reach_idempotency[token_only]",
        ),
    ),
    Mutation(
        id="M47", side="be", path=MC, kind="replace",
        anchor="            if required not in self.stages:",
        new="            if False:",
        want=f"{OFF}.py::test_unauthorized_request_cannot_reach_idempotency",
        why="阶段链不再强制 ⇒ 任何手工构造的 `AuthorizedMaterializeRequest` 都能进"
            "materialize，「顺序由类型强制」退化成注释",
    ),
    Mutation(
        id="M49", side="be", path=MC, kind="replace",
        anchor='_SCOPE_ONLY_REPO_CALLS: Final[frozenset[str]] = frozenset({"resolve_scope"})',
        new='_SCOPE_ONLY_REPO_CALLS: Final[frozenset[str]] = frozenset({"resolve_scope", "lock_room"})',
        want=f"{OFF}.py::test_scope_only_repo_call_whitelist_is_exactly_resolve_scope",
        why="把 `lock_room` 放进授权阶段白名单 ⇒ 「只读非敏感 scope index」被放宽成"
            "「也可以先锁业务行」。🔴 只断言 `assert_authorization_first_shape() == "
            "('resolve_scope',)` 抓不到它（那看的是**实际调用**，白名单变宽不改变实际"
            "调用；首轮实测 GREEN），故白名单本身另有一条集合等值判据",
    ),
    Mutation(
        id="M49b", side="be", path=MC, kind="replace",
        anchor='    "WorkpaperPendingMutation",',
        new='    "NotATable",',
        want=f"{OFF}.py::test_business_table_denylist_covers_every_sync_business_table",
        why="从禁用名单里摘掉 `WorkpaperPendingMutation` ⇒ 在授权阶段 "
            "`sa.select(WorkpaperPendingMutation)` 不再被 AST 判据抓到，"
            "而那正是 M44 要防的形态。名单本身必须有判据",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 八、flush 的 revision 中立性（Requirement 3.1）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M50", side="be", path=MC, kind="replace",
        anchor="        locked = RevisionLockedRepository(self._repo)",
        new="        locked = self._repo",
        want=f"{OFF}.py::test_flush_never_touches_the_revision_domain",
        why="flush 重新拿到 revision 域写入面 ⇒ 「flush 只创建 pending mutation」从"
            "「构造上碰不到」退化成「我没写那三行」（Property 4 同一机制）",
    ),
    Mutation(
        id="M51", side="be", path=MC, kind="replace",
        anchor="    if int(after) != int(before):",
        new="    if False:",
        want=f"{OFF}.py::test_flush_that_moved_the_revision_is_refused",
        why="去掉 flush 的 revision 前后相等自证 ⇒ 即便有人绕过门面走裸 SQL 也无人报警。"
            "与 M50 分开：M50 是构造判据（门面摘掉写入面），本条是行为判据，"
            "两者少任一个都留缺口",
    ),
    Mutation(
        id="M51b", side="be", path=MC, kind="replace",
        anchor="        assert_flush_revision_neutral(revision_before, revision_after)",
        new="        pass",
        want=f"{OFF}.py::test_coordinator_delegates_to_the_pure_accounting_functions",
        why="flush 不再调用 revision 中立性判据 ⇒ 判据存在但没有消费方"
            "（假绿第①源）。与 M51 分开：一个摘判据、一个摘调用",
    ),
    Mutation(
        id="M52", side="be", path=MC, kind="replace",
        anchor="            return self._receipt_of(existing, replayed=True)",
        new="            pass",
        want=f"{PG}.py::test_flush_is_idempotent_on_the_same_key_and_payload",
        why="同 key 重复 flush 不再复用既有行 ⇒ 撞 `uq_wppm_scope_key` 唯一约束或造出"
            "第二行 pending mutation，「单次逻辑消费」的前提破裂",
    ),
    Mutation(
        id="M53", side="be", path=MC, kind="replace",
        anchor='            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),',
        # 同文本在 `canonical_mapping` 里也出现一次 ⇒ 用 `as_dict` 独有的上一行定位。
        scope='            "payload_sha256": self.payload_sha256,',
        offset=1,
        new='            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(), "revision": 1,',
        want=f"{OFF}.py::test_pending_mutation_receipt_returns_exactly_the_four_documented_fields",
        why="flush 响应体多返回一个 revision 字段 ⇒ 诱使前端把 flush 当成提交"
            "（Requirement 3.1：flush 只创建 pending mutation，不产生业务版本）",
        wants=(
            f"{PG}.py::test_flush_receipt_exposes_exactly_the_four_documented_fields",
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 九、Property 67：definitions-only 升级
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M54", side="be", path=MC, kind="replace",
        anchor="        if not outcome.revision_unchanged:",
        new="        if False:",
        want=f"{OFF}.py::test_definition_upgrade_that_moved_revision_is_refused",
        why="纯定义升级递增 business revision 时不再拒绝 ⇒ 隐形载体升级会伪造业务 "
            "revision（Property 67 / Requirement 3.6「revision 保持不变」）",
    ),
    Mutation(
        id="M55", side="be", path=MC, kind="replace",
        anchor="        if self._representations is None:",
        new="        if False:",
        want=f"{OFF}.py::test_materialize_path_cannot_publish_representations_by_itself",
        why="未装配 `RepresentationService` 时静默继续 ⇒ `AttributeError` 而不是"
            "可操作诊断；「唯一出口」这条承诺没有落点",
    ),
    Mutation(
        id="M56", side="be", path=MC, kind="replace",
        anchor="        outcome = await self._representations.finalize_candidate(**kwargs)",
        new="        outcome = None",
        want=f"{OFF}.py::test_definition_upgrade_with_unchanged_revision_is_returned_as_is",
        why="不再委派 Task 15 的 finalize ⇒ Property 67 的发布 DAG"
            "（`template → instrumentation → contract → bundle → representation`）"
            "被绕过。反向自检测的正是「真的调用了它」",
        wants=(f"{OFF}.py::test_definition_upgrade_that_moved_revision_is_refused",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 十、confirm-descriptor 的逐项比对（Property 11 后半）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M57", side="be", path=MC, kind="replace",
        anchor="            if not same:",
        new="            if False:",
        want=f"{PG}.py::test_every_tampered_identity_item_is_refused_with_409",
        why="confirm-descriptor 不再逐项比对 identity ⇒ 篡改或陈旧 "
            "generation/doc_key/artifact/bundle/fence 全部放行，room 会被一个错误基线"
            "推进到 active 并允许 forcesave（AC 3.7）",
        wants=(
            f"{PG}.py::test_every_tampered_identity_item_is_refused_with_409[doc_key]",
            f"{PG}.py::test_every_tampered_identity_item_is_refused_with_409[write_fence_epoch]",
        ),
    ),
    Mutation(
        id="M58", side="be", path=MC, kind="replace",
        anchor="        if echoed_revision is None or int(echoed_revision) != int(actual_revision or -1):",
        new="        if False:",
        want=f"{PG}.py::test_every_tampered_identity_item_is_refused_with_409",
        why="不再比对回传的 content revision ⇒ 编辑器实际加载的是旧 revision 却被记为"
            "已确认新基线，AC 2.9 的 client-confirmed 指针失真。"
            "与 M57 分开：revision 的比较对象是 content version 行而不是 room/representation",
    ),
    Mutation(
        id="M59", side="be", path=MC, kind="replace",
        anchor="        scope_row = await self._repo.resolve_scope(",
        new="        scope_row = None if True else await self._repo.resolve_scope(",
        want=f"{PG}.py::test_unknown_resource_yields_the_unified_404_envelope",
        why="confirm-descriptor 不再先查 scope index ⇒ authorization-before-resource "
            "失效，`room 不存在` 与 `room 属于别人` 会暴露成两种不同时序（AC 10.5）。"
            "🔴 这里刻意用 `None if True else`（而非删掉整行）来保留函数调用的语法形态，"
            "确保变异只改**行为**不改结构",
        wants=(
            f"{PG}.py::test_confirmation_unlocks_forcesave_without_touching_revision",
        ),
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files={
                f"{OFF}.py": "Task 25 离线守卫：token 逐项比对 / descriptor 构造期判据 / "
                             "preflight 映射 / 授权阶段形态 / P67 委派",
                f"{PG}.py": "Task 25 真库守卫：revision delta / room 行数 / operation 终态 / "
                            "单事务见证 / confirm 状态迁移 / candidate 阻断",
            },
            repo=REPO,
            description="Task 25 HTML→OO coordinator 与唯一 launch descriptor 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task25_materialize_coordinator.py",
                "backend/tests/workpaper_sync/test_task25_materialize_coordinator_pg.py",
                "-p", "no:randomly", "--no-header", "-q",
            ],
            # 冻结基线：2026-08-27 实测 106（离线）+ 51（真库）= 157 passed。
            baseline_backend_passed=157,
        )
    )
